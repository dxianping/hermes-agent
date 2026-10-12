"""Contract tests for persistent remote MCP skill trust (tools/mcp_skills_trust.py + consent gates).

Regression for GAP-SEP2640-skills-consent-not-configurable: ``mcp_servers.<server>.skills.trust:
auto`` plus an exact ``hermes skills trust-mcp`` record may pre-authorize activation and host
execution; everything else — cross-origin reads, Skills Guard, eligibility, default deny — stays.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _entry(name="remote-demo"):
    from tools.mcp_skills_protocol import SkillEntry
    body = f"---\nname: {name}\ndescription: Remote demo\n---\n\n# Demo\n".encode()
    uri = f"skill://fixture/{name}/SKILL.md"
    return SkillEntry.model_validate({
        "uri": uri,
        "frontmatter": {"name": name, "description": "Remote demo"},
        "resources": [
            {"uri": uri, "digest": "sha256:" + hashlib.sha256(body).hexdigest(), "size": len(body)},
            {"uri": uri.replace("SKILL.md", "references/run.md"),
             "digest": "sha256:" + hashlib.sha256(b"Run B guidance").hexdigest(), "size": 14},
        ],
    })


def _write_config(home: Path, *, trust: str | None = None, enabled: bool = True,
                  server: str = "fixture") -> None:
    lines = ["mcp_servers:", f"  {server}:", "    url: http://127.0.0.1:1/mcp", "    skills:",
             f"      enabled: {'true' if enabled else 'false'}"]
    if trust is not None:
        lines.append(f"      trust: {trust}")
    (home / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture()
def held(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    from tools import mcp_skills_registry as registry
    registry.clear_runtime_state()
    registry.publish_live_catalog(home, "fixture", "config-a", [_entry()])
    record = registry.pin_session(home, "session-a")[0]
    yield home, record
    registry.clear_runtime_state()


def _record(record, home):
    from tools.mcp_skills_trust import record_trust
    return record_trust(record["server"], record["uri"], home=home,
                        name=record["frontmatter"]["name"],
                        manifest_fingerprint=record["manifest_fingerprint"])


def test_trust_policy_reads_only_recognized_values_from_user_config(held):
    home, _record_row = held
    from tools.mcp_skills_trust import trust_policy
    assert trust_policy("fixture") == "prompt"  # no config.yaml key
    _write_config(home, trust="auto")
    assert trust_policy("fixture") == "auto"
    _write_config(home, trust="yes")
    assert trust_policy("fixture") == "prompt"
    assert trust_policy("not-configured") == "prompt"


def test_trust_store_roundtrip_remove_and_profile_isolation(held, tmp_path):
    home, record = held
    from tools.mcp_skills_trust import is_origin_trusted, list_trusted, record_trust, remove_trust
    assert not is_origin_trusted(record["server"], record["uri"], home)
    row = _record(record, home)
    assert row["manifest_fingerprint"] == record["manifest_fingerprint"]
    assert is_origin_trusted(record["server"], record["uri"], home)
    assert [r["uri"] for r in list_trusted(home)] == [record["uri"]]
    other_home = tmp_path / "other-home"
    other_home.mkdir()
    assert not is_origin_trusted(record["server"], record["uri"], other_home)
    assert list_trusted(other_home) == []
    assert remove_trust(record["server"], record["uri"], home=home) is True
    assert not is_origin_trusted(record["server"], record["uri"], home)
    assert remove_trust(record["server"], record["uri"], home=home) is False
    assert record_trust("fixture", "skill://fixture/x/SKILL.md", home=home)["uri"].endswith("SKILL.md")


def test_corrupt_trust_store_fails_closed(held, monkeypatch):
    home, record = held
    from tools import approval_prompt
    from tools.mcp_skills_consent import enforce_skill_activation_gate
    from tools.mcp_skills_trust import is_origin_trusted
    _write_config(home, trust="auto")
    store = home / "cache" / "mcp-skills" / "trusted-origins.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("{not json", encoding="utf-8")
    assert not is_origin_trusted(record["server"], record["uri"], home)
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent", lambda *a, **k: "decline")
    blocked = enforce_skill_activation_gate(record, home=home, session_id="session-a")
    assert blocked is not None and "activation was not approved" in blocked


def test_activation_gate_auto_approves_with_policy_and_record_only(held, monkeypatch):
    home, record = held
    from tools import approval_prompt
    from tools.mcp_skills_consent import enforce_skill_activation_gate
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent",
                        lambda *a, **k: pytest.fail("consent must not be prompted for a trusted origin"))

    # Record alone (policy still prompt) must not auto-approve.
    _record(record, home)
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent", lambda *a, **k: "decline")
    assert enforce_skill_activation_gate(record, home=home, session_id="session-a") is not None

    # Policy alone (no record) must not auto-approve either.
    from tools.mcp_skills_trust import remove_trust
    remove_trust(record["server"], record["uri"], home=home)
    _write_config(home, trust="auto")
    assert enforce_skill_activation_gate(record, home=home, session_id="session-a") is not None

    # Both together: no prompt, straight through (the unattended path).
    _record(record, home)
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent",
                        lambda *a, **k: pytest.fail("consent must not be prompted for a trusted origin"))
    assert enforce_skill_activation_gate(record, home=home, session_id="session-a") is None


def test_activation_auto_falls_back_while_an_untrusted_origin_is_active(held, monkeypatch):
    home, _first = held
    from tools import approval_prompt
    from tools import mcp_skills_registry as registry
    from tools.mcp_skills_consent import enforce_skill_activation_gate

    registry.publish_live_catalog(home, "fixture", "config-a", [_entry("skill-a"), _entry("skill-b")])
    by_name = {row["frontmatter"]["name"]: row for row in registry.pin_session(home, "session-x")}
    registry.mark_active(by_name["skill-a"], home, "session-x")
    _write_config(home, trust="auto")
    _record(by_name["skill-b"], home)

    # b is trusted but a (the other active origin) is not: the activation decision also covers
    # this first cross-origin body read, so it must stay human-answered.
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent", lambda *a, **k: "decline")
    blocked = enforce_skill_activation_gate(by_name["skill-b"], home=home, session_id="session-x")
    assert blocked is not None and "activation was not approved" in blocked

    # Trusting every active origin too lets the combined decision auto-approve.
    _record(by_name["skill-a"], home)
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent",
                        lambda *a, **k: pytest.fail("all origins trusted: no prompt expected"))
    assert enforce_skill_activation_gate(by_name["skill-b"], home=home, session_id="session-x") is None


def test_execution_gate_auto_approves_without_persisting_session_consent(held, monkeypatch):
    home, record = held
    from tools import approval_prompt
    from tools import mcp_skills_registry as registry
    from tools.mcp_skills_consent import enforce_remote_skill_gate
    from tools.mcp_skills_trust import remove_trust

    registry.mark_active(record, home, "session-a")
    _write_config(home, trust="auto")
    _record(record, home)
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent",
                        lambda *a, **k: pytest.fail("consent must not be prompted for a trusted origin"))
    assert enforce_remote_skill_gate("terminal", {"command": "printf ok"}, session_id="session-a") is None
    # Auto approval is a live check, never a session grant: revoking it re-blocks immediately.
    assert not registry.has_execution_consent(record, home, "session-a")
    remove_trust(record["server"], record["uri"], home=home)
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent", lambda *a, **k: "decline")
    blocked = enforce_remote_skill_gate("execute_code", {"code": "print(1)"}, session_id="session-a")
    assert blocked is not None and "host execution was not approved" in blocked


def test_cross_origin_reads_stay_prompted_for_trusted_origins(held, monkeypatch):
    home, _first = held
    from tools import approval_prompt
    from tools import mcp_skills_registry as registry
    from tools import mcp_tool
    from tools.mcp_skills_consent import enforce_native_skill_read_gate, enforce_remote_skill_gate

    registry.publish_live_catalog(home, "fixture", "config-a", [_entry("skill-a"), _entry("skill-b")])
    by_name = {row["frontmatter"]["name"]: row for row in registry.pin_session(home, "session-x")}
    registry.mark_active(by_name["skill-a"], home, "session-x")
    _write_config(home, trust="auto")
    _record(by_name["skill-a"], home)
    _record(by_name["skill-b"], home)
    monkeypatch.setattr(approval_prompt, "request_elicitation_consent", lambda *a, **k: "deny")

    resource = by_name["skill-b"]["resources"][1]
    blocked = enforce_native_skill_read_gate(by_name["skill-b"], resource, session_id="session-x")
    assert blocked is not None and "cross-origin native" in blocked

    tool_name = "mcp__fixture__read_resource"
    monkeypatch.setitem(mcp_tool._mcp_tool_server_names, tool_name, "fixture")
    blocked = enforce_remote_skill_gate(
        tool_name, {"uri": "skill://fixture/elsewhere/SKILL.md"}, session_id="session-x")
    assert blocked is not None and "cross-origin" in blocked
