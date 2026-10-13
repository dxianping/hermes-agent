"""Behaviour contracts for switching remote skills on and off by name.

``skills.disabled`` / ``skills.platform_disabled`` is the whole authorization story
for a remote skill: it is managed by the same config, read through the same
normalizing reader, and answers the same way on every surface. These tests drive a
real ``config.yaml`` under a temp ``HERMES_HOME`` rather than patching the reader,
because the reader's normalization (``hermes config set`` writes lists as quoted
JSON strings) is exactly what a patched test would skip past.
"""

import asyncio
import json

import pytest

from agent.skill_utils import _raw_config_cache_clear
from tests.fakes.fake_mcp_skills import FakeSkill, FakeSkillsServer, FakeSkillsSender
from tools import skills_tool
from tools.mcp_skills_manager import SkillsOverMcpManager, set_manager

SERVER = "acme"
OTHER = "other"
SCOPE = ""


def _home():
    from hermes_constants import get_hermes_home
    return get_hermes_home()


def _write_config(*, disabled=None, platform_disabled=None) -> None:
    """Write the profile's skills config as plain text (no YAML writer in tests)."""
    lines = ["skills:"]
    if disabled is not None:
        lines.append(f"  disabled: {disabled}")
    if platform_disabled is not None:
        lines.append("  platform_disabled:")
        for platform, names in platform_disabled.items():
            lines.append(f"    {platform}: {names}")
    (_home() / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _raw_config_cache_clear()
    skills_tool.clear_skills_cache()


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """A live manager over a fake server, with the profile's own skills dir available."""
    (_home() / "skills").mkdir(parents=True, exist_ok=True)
    _write_config()

    server = FakeSkillsServer([
        FakeSkill(uri="skill://team/deploy/SKILL.md", name="deploy", description="ship it",
                  files={"SKILL.md": "---\nname: deploy\n---\nrun the deploy\n"}),
        FakeSkill(uri="skill://team/rollback/SKILL.md", name="rollback", description="undo it",
                  files={"SKILL.md": "---\nname: rollback\n---\nundo\n"}),
    ])
    manager = SkillsOverMcpManager(sender=FakeSkillsSender(server))
    manager.observe_connection(SERVER, SCOPE, initialize_result=server.initialize_result(), session=object())
    asyncio.run(manager.discover(SERVER, SCOPE))

    from tools import skills_tool_mcp
    set_manager(manager)
    monkeypatch.setattr(skills_tool_mcp, "known_server_labels", lambda: {SERVER, OTHER})
    try:
        yield server, manager
    finally:
        set_manager(None)
        _raw_config_cache_clear()


def _view(**kwargs) -> dict:
    kwargs.setdefault("task_id", "task-disabled")
    return json.loads(skills_tool.skill_view(**kwargs))


def _remote_names() -> set[str]:
    listing = json.loads(skills_tool.skills_list())
    return {s["name"] for s in listing["skills"] if s.get("source", {}).get("remote")}


# ── the name is the unit ────────────────────────────────────────────────────

def test_a_remote_skill_is_on_by_default(remote):
    assert _view(name=f"{SERVER}::deploy")["success"] is True
    assert _remote_names() == {f"{SERVER}::deploy", f"{SERVER}::rollback"}


def test_disabling_the_qualified_name_refuses_the_load_on_every_locator(remote):
    _write_config(disabled=["acme::deploy"])
    for kwargs in ({"name": f"{SERVER}::deploy"},
                   {"server": SERVER, "uri": "skill://team/deploy/SKILL.md"}):
        result = _view(**kwargs)
        assert result["success"] is False
        assert "disabled" in result["error"]
        assert f"{SERVER}::deploy" in result["error"]


def test_a_switched_off_skill_costs_no_read(remote):
    server, _manager = remote
    _write_config(disabled=["acme::deploy"])
    before = server.calls.count("resources/read")
    _view(name=f"{SERVER}::deploy")
    assert server.calls.count("resources/read") == before


def test_a_switched_off_skill_leaves_the_listing_and_the_index(remote):
    _write_config(disabled=["acme::deploy"])
    assert _remote_names() == {f"{SERVER}::rollback"}

    # The projection consumes the same set the prompt builder resolves, so it is read
    # the same way here rather than handed a hand-made one.
    from agent.skill_utils import get_disabled_skill_names
    from agent.skills_prompt_mcp import mcp_skill_rows
    rows, _token = mcp_skill_rows(get_disabled_skill_names(), None, None, None)
    assert {r[1] for r in rows} == {f"{SERVER}::rollback"}


def test_the_bare_name_never_reaches_a_remote_skill(remote):
    """An entry written for a local skill must not switch off a remote namesake."""
    _write_config(disabled=["deploy"])
    assert _view(name=f"{SERVER}::deploy")["success"] is True
    assert _remote_names() == {f"{SERVER}::deploy", f"{SERVER}::rollback"}


def test_the_bare_name_still_disables_the_local_skill_of_that_name(remote):
    """The local contract is unchanged by any of this — same config, opposite outcome."""
    local = _home() / "skills" / "deploy"
    local.mkdir(parents=True)
    (local / "SKILL.md").write_text("---\nname: deploy\n---\nlocal body\n", encoding="utf-8")
    skills_tool.clear_skills_cache()
    assert json.loads(skills_tool.skill_view("deploy"))["success"] is True

    _write_config(disabled=["deploy"])
    assert json.loads(skills_tool.skill_view("deploy"))["success"] is False
    assert _view(name=f"{SERVER}::deploy")["success"] is True


def test_one_server_being_switched_off_does_not_touch_another(remote):
    _write_config(disabled=["other::deploy"])
    assert _view(name=f"{SERVER}::deploy")["success"] is True


# ── the config spellings the reader has to normalize ────────────────────────

def test_a_json_array_string_from_config_set_is_honoured(remote):
    """``hermes config set skills.disabled '["acme::deploy"]'`` must work, not be ignored."""
    _write_config(disabled='\'["acme::deploy"]\'')
    assert _view(name=f"{SERVER}::deploy")["success"] is False
    assert _remote_names() == {f"{SERVER}::rollback"}


def test_a_scalar_string_is_one_name(remote):
    _write_config(disabled="'acme::deploy'")
    assert _view(name=f"{SERVER}::deploy")["success"] is False


def test_platform_disabled_switches_off_for_one_platform(monkeypatch, remote):
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    _write_config(platform_disabled={"telegram": ["acme::rollback"]})
    assert _view(name=f"{SERVER}::rollback")["success"] is False
    assert _view(name=f"{SERVER}::deploy")["success"] is True


def test_platform_disabled_for_another_platform_leaves_the_skill_on(monkeypatch, remote):
    monkeypatch.setenv("HERMES_PLATFORM", "telegram")
    _write_config(platform_disabled={"discord": ["acme::rollback"]})
    assert _view(name=f"{SERVER}::rollback")["success"] is True


# ── the name survives everything that is not the name ───────────────────────

def test_a_republished_catalog_does_not_restore_a_disabled_skill(remote):
    """Authorization is by name: new content on the server changes nothing about it."""
    server, manager = remote
    _write_config(disabled=["acme::deploy"])
    assert _view(name=f"{SERVER}::deploy")["success"] is False

    server.skills[0].files["SKILL.md"] = "---\nname: deploy\n---\nreworked body\n"
    asyncio.run(manager.discover(SERVER, SCOPE, reason="republication"))
    assert _view(name=f"{SERVER}::deploy")["success"] is False


def test_a_name_no_longer_published_is_not_provided_not_disabled(remote):
    """Disabling and disappearing are different answers, and the model needs to tell them apart."""
    server, manager = remote
    server.unlisted.add("skill://team/deploy/SKILL.md")
    asyncio.run(manager.discover(SERVER, SCOPE, reason="unpublish"))
    result = _view(server=SERVER, uri="skill://team/deploy/SKILL.md")
    assert "disabled" not in (result.get("error") or "")


# ── the router still refuses to guess ───────────────────────────────────────

def test_two_uri_same_name_are_both_covered_by_the_one_name_entry(remote):
    """Disabling is name-level, so one entry covers both; loading still refuses to guess."""
    server, manager = remote
    server.skills.append(FakeSkill(uri="skill://team/v2/deploy/SKILL.md", name="deploy",
                                   files={"SKILL.md": "---\nname: deploy\n---\nv2\n"}))
    asyncio.run(manager.discover(SERVER, SCOPE, reason="duplicate-name"))

    ambiguous = _view(name="deploy")
    assert ambiguous["error_code"] == "ambiguous_identity"

    _write_config(disabled=["acme::deploy"])
    assert _view(server=SERVER, uri="skill://team/deploy/SKILL.md")["success"] is False
    assert _view(server=SERVER, uri="skill://team/v2/deploy/SKILL.md")["success"] is False
    assert _view(server=SERVER, uri="skill://team/rollback/SKILL.md")["success"] is True
