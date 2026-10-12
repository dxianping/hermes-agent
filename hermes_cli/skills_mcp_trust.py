"""``hermes skills trust-mcp|untrust-mcp|trusted-mcp`` — persistent trust for remote MCP skills.

``trust-mcp`` connects to the named server once, point-fetches the exact skill URI through the
runtime path (``register_skill_uri`` — same manifest validation and Skills Guard scan the agent
uses, no body read and no activation), records the trust, and flips the per-server
``mcp_servers.<server>.skills.trust`` opt-in to ``auto``. Without that config key a record alone
never auto-approves anything, and a Skills-Guard-blocked manifest is never recorded.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger("hermes_cli.skills_mcp_trust")

# Stable (not per-PID) so the command's session snapshot under cache/mcp-skills is overwritten
# instead of accumulating; nothing reads this session's active-origins or consent state.
_TRUST_SESSION_ID = "mcp-trust-cli"


def cmd_skills_trust_mcp(args) -> None:
    action = getattr(args, "skills_action", None)
    if action == "untrust-mcp":
        return _untrust(args)
    if action == "trusted-mcp":
        return _list_trusted()
    return _trust(args)


def _trust(args) -> None:
    from hermes_cli.config import load_config, save_config
    from tools.mcp_skills_protocol import skills_opted_in, validate_skill_uri

    server, uri = args.server, args.uri
    try:
        validate_skill_uri(uri)
    except (TypeError, ValueError) as exc:
        print(f"Not a valid skill URI: {exc}")
        sys.exit(1)
    config = load_config()
    entry = (config.get("mcp_servers") or {}).get(server)
    if not isinstance(entry, dict):
        print(f"MCP server {server!r} is not configured in this profile (mcp_servers).")
        sys.exit(1)
    if not skills_opted_in(entry):
        print(f"MCP server {server!r} has not opted into the skills extension: set "
              f"mcp_servers.{server}.skills.enabled: true first.")
        sys.exit(1)

    from tools.mcp_skills_cache import register_skill_uri
    from tools.mcp_skills_scan import RemoteSkillSecurityError
    from tools.mcp_tool_discovery import discover_mcp_tools
    from tools.mcp_tool_lifecycle import _stop_mcp_loop_if_idle

    print(f"Connecting to MCP server {server!r} …")
    try:
        discover_mcp_tools([server])
        record = register_skill_uri(server, uri, session_id=_TRUST_SESSION_ID)
    except RemoteSkillSecurityError as exc:
        print(f"Refused: {uri} was blocked by Skills Guard ({exc}). Trust not recorded.")
        sys.exit(1)
    except Exception as exc:  # CLI boundary: transport/scan errors are open-ended
        logger.debug("MCP skill trust fetch failed for %s from %r", uri, server, exc_info=True)
        print(f"Could not fetch {uri} from {server!r}: {exc}")
        print("If this server signs in interactively, run `hermes mcp login "
              f"{server}` first, then retry.")
        sys.exit(1)
    finally:
        _stop_mcp_loop_if_idle()

    from tools.mcp_skills_trust import record_trust, trust_policy

    name = (record.get("frontmatter") or {}).get("name") or ""
    row = record_trust(server, uri, name=name,
                       manifest_fingerprint=record.get("manifest_fingerprint") or "",
                       config_fingerprint=record.get("config_fingerprint") or "")
    if trust_policy(server) != "auto":
        skills_cfg = config.setdefault("mcp_servers", {}).setdefault(server, {}).setdefault("skills", {})
        skills_cfg["trust"] = "auto"
        save_config(config)
        print(f"Enabled mcp_servers.{server}.skills.trust: auto in this profile's config.yaml.")
    print(f"Trusted: {server}  {uri}")
    print(f"  name: {name or '—'}   manifest: {(row['manifest_fingerprint'] or '—')[:16]}")
    print("  Activation and host execution for this exact skill now auto-approve in this profile")
    print("  (including unattended runs). Cross-origin reads, Skills Guard scans, and ordinary")
    print("  command/tool approvals are unchanged.")
    print(f"  Revoke with: hermes skills untrust-mcp {server} {uri}")


def _untrust(args) -> None:
    from tools.mcp_skills_trust import remove_trust

    if remove_trust(args.server, args.uri):
        print(f"Untrusted: {args.server}  {args.uri}")
        print("Consent gates for this skill require a human answer again (the "
              "skills.trust config key is left as-is).")
    else:
        print(f"Not trusted: {args.server}  {args.uri}")


def _list_trusted() -> None:
    from tools.mcp_skills_trust import list_trusted, trust_policy

    rows = list_trusted()
    if not rows:
        print("No trusted remote MCP skills for this profile.")
        print("Grant one with: hermes skills trust-mcp <server> <skill://…/SKILL.md>")
        return
    for row in rows:
        policy = trust_policy(row["server"])
        state = "auto" if policy == "auto" else (
            f"inactive — set mcp_servers.{row['server']}.skills.trust: auto to apply")
        print(f"{row['server']}  {row['uri']}")
        print(f"    name: {row.get('name') or '—'}   "
              f"manifest: {(row.get('manifest_fingerprint') or '—')[:16]}   "
              f"trusted_at: {row.get('trusted_at') or '—'}")
        print(f"    policy: {state}")
