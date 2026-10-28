"""T18 hardening: O4 (pitch answer on "is it safe to auto-fix?") must match what the code actually does."""
from __future__ import annotations

import re

from app.core.config import REPO_ROOT

SCRIPT = (REPO_ROOT / "docs" / "DEMO_SCRIPT.md").read_text()
APP = REPO_ROOT / "backend" / "app"


def _o4_section() -> str:
    m = re.search(r"## If a judge asks.*?\(RISKS O4\)(.*)", SCRIPT, re.S)
    assert m, "DEMO_SCRIPT.md needs the O4 safety answer"
    return m.group(1)


def test_o4_answer_covers_all_four_points():
    text = _o4_section().lower()
    for phrase in ("never auto-merged", "tests must pass", "s6", "jira", "compliance"):
        assert phrase in text, phrase


def test_o4_claim_holds_in_code_no_auto_merge():
    for path in APP.rglob("*.py"):
        src = path.read_text()
        assert not re.search(r"\.merge\(\s*(commit_message|merge_method)|pulls?/\d+/merge|enable_auto_merge", src), path


def test_o4_claim_holds_in_code_patch_fence():
    from app.services import fixer

    assert fixer.MAX_PATCH_CHANGED_LINES == 200
    assert {"tests", ".github"} <= fixer._TEST_DIRS
    for name in ("conftest.py", "setup.py", "test_x.py"):
        assert fixer._TEST_FILE.match(name)
