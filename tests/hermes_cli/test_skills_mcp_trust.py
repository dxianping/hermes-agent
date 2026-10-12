"""``hermes skills trust-mcp|untrust-mcp|trusted-mcp`` wiring and behavior contracts."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

_URI = "skill://fixture/remote-demo/SKILL.md"


def _parser():
    from hermes_cli.subcommands.skills import build_skills_parser
    parser = argparse.ArgumentParser(prog="hermes")
    subparsers = parser.add_subparsers(dest="command")
    build_skills_parser(subparsers, cmd_skills=lambda args: None)
    return parser


def _args(*argv):
    args = _parser().parse_args(["skills", *argv])
    from hermes_cli.main_agent_cmds import cmd_skills
    return args, cmd_skills


@pytest.fixture()
def cli_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    (home / "config.yaml").write_text(
        "mcp_servers:\n  fixture:\n    url: http://127.0.0.1:1/mcp\n"
        "    skills:\n      enabled: true\n", encoding="utf-8")
    return home


def test_parser_wires_the_three_mcp_trust_actions():
    args, _ = _args("trust-mcp", "fixture", _URI)
    assert (args.skills_action, args.server, args.uri) == ("trust-mcp", "fixture", _URI)
    args, _ = _args("untrust-mcp", "fixture", _URI)
    assert (args.skills_action, args.server, args.uri) == ("untrust-mcp", "fixture", _URI)
    args, _ = _args("trusted-mcp")
    assert args.skills_action == "trusted-mcp"


def test_trust_mcp_fetches_records_and_enables_policy(cli_home, monkeypatch, capsys):
    calls = []
    record = {"frontmatter": {"name": "remote-demo"}, "manifest_fingerprint": "f" * 64,
              "config_fingerprint": "config-a"}
    monkeypatch.setattr("tools.mcp_tool_discovery.discover_mcp_tools",
                        lambda names=None: calls.append(("discover", names)) or ["mcp__fixture__x"])
    monkeypatch.setattr("tools.mcp_skills_cache.register_skill_uri",
                        lambda server, uri, session_id=None, **kw: (
                            calls.append(("fetch", server, uri)) or record))
    monkeypatch.setattr("tools.mcp_tool_lifecycle._stop_mcp_loop_if_idle", lambda: None)

    args, cmd_skills = _args("trust-mcp", "fixture", _URI)
    cmd_skills(args)
    out = capsys.readouterr().out
    assert ("discover", ["fixture"]) in calls and ("fetch", "fixture", _URI) in calls
    assert "Trusted: fixture" in out and "untrust-mcp" in out

    from tools.mcp_skills_trust import is_origin_trusted
    assert is_origin_trusted("fixture", _URI, cli_home)
    raw = (cli_home / "config.yaml").read_text(encoding="utf-8")
    assert "trust: auto" in raw and "enabled: true" in raw


def test_trust_mcp_refuses_when_skills_guard_blocks(cli_home, monkeypatch, capsys):
    from tools.mcp_skills_scan import RemoteSkillSecurityError

    monkeypatch.setattr("tools.mcp_tool_discovery.discover_mcp_tools", lambda names=None: [])
    def _blocked(server, uri, session_id=None, **kw):
        raise RemoteSkillSecurityError("catalog metadata")
    monkeypatch.setattr("tools.mcp_skills_cache.register_skill_uri", _blocked)
    monkeypatch.setattr("tools.mcp_tool_lifecycle._stop_mcp_loop_if_idle", lambda: None)

    args, cmd_skills = _args("trust-mcp", "fixture", _URI)
    with pytest.raises(SystemExit) as excinfo:
        cmd_skills(args)
    assert excinfo.value.code == 1
    assert "blocked by Skills Guard" in capsys.readouterr().out
    from tools.mcp_skills_trust import is_origin_trusted, list_trusted
    assert not is_origin_trusted("fixture", _URI, cli_home)
    assert list_trusted(cli_home) == []
    assert "trust: auto" not in (cli_home / "config.yaml").read_text(encoding="utf-8")


def test_trust_mcp_rejects_unknown_server_disabled_skills_and_malformed_uri(cli_home, monkeypatch, capsys):
    args, cmd_skills = _args("trust-mcp", "missing", _URI)
    with pytest.raises(SystemExit):
        cmd_skills(args)
    assert "not configured" in capsys.readouterr().out

    (cli_home / "config.yaml").write_text(
        "mcp_servers:\n  fixture:\n    url: http://127.0.0.1:1/mcp\n"
        "    skills:\n      enabled: false\n", encoding="utf-8")
    args, cmd_skills = _args("trust-mcp", "fixture", _URI)
    with pytest.raises(SystemExit):
        cmd_skills(args)
    assert "has not opted into" in capsys.readouterr().out

    monkeypatch.setattr("tools.mcp_tool_discovery.discover_mcp_tools",
                        lambda names=None: pytest.fail("must not connect for a malformed URI"))
    args, cmd_skills = _args("trust-mcp", "fixture", "skill://fixture/demo/README.md")
    with pytest.raises(SystemExit):
        cmd_skills(args)
    assert "Not a valid skill URI" in capsys.readouterr().out


def test_untrust_and_list_roundtrip(cli_home, capsys):
    from tools.mcp_skills_trust import list_trusted, record_trust

    record_trust("fixture", _URI, home=cli_home, name="remote-demo", manifest_fingerprint="a" * 64)
    args, cmd_skills = _args("trusted-mcp")
    cmd_skills(args)
    out = capsys.readouterr().out
    assert _URI in out and "remote-demo" in out

    args, cmd_skills = _args("untrust-mcp", "fixture", _URI)
    cmd_skills(args)
    assert "Untrusted: fixture" in capsys.readouterr().out
    assert list_trusted(cli_home) == []

    args, cmd_skills = _args("untrust-mcp", "fixture", _URI)
    cmd_skills(args)
    assert "Not trusted" in capsys.readouterr().out

    args, cmd_skills = _args("trusted-mcp")
    cmd_skills(args)
    assert "No trusted remote MCP skills" in capsys.readouterr().out
