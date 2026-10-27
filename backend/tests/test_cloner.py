"""T02 cloner + subprocess helper. Hardening: S2, S3, N2, E7, E13 (no network: `run` is faked)."""
from __future__ import annotations

import asyncio
import os
import stat
import sys

import pytest

from app.core import subproc
from app.core.config import get_settings
from app.core.subproc import CommandResult, CommandTimeout
from app.services import cloner
from app.services.cloner import CloneError

URL = "https://github.com/BommepalliRoop/demo-target"


class FakeGit:
    def __init__(self, monkeypatch, *, code=0, stderr="", raises=None, create_repo=True):
        self.cmd: list[str] = []
        self.env: dict[str, str] = {}
        self.timeout = None
        self.code, self.stderr, self.raises, self.create_repo = code, stderr, raises, create_repo
        monkeypatch.setattr(cloner, "run", self.run)

    async def run(self, cmd, *, env=None, timeout, **kw):
        self.cmd, self.env, self.timeout = list(cmd), dict(env or {}), timeout
        dest = cmd[-1]
        if self.create_repo:  # git creates the dir (and read-only object files) before failing/hanging
            os.makedirs(os.path.join(dest, ".git", "objects"))
            obj = os.path.join(dest, ".git", "objects", "pack")
            open(obj, "w").close()
            os.chmod(obj, stat.S_IREAD)
        if self.raises:
            raise self.raises
        return CommandResult(self.code, "", self.stderr)


async def test_clone_command_is_shallow_single_branch_with_double_dash(monkeypatch):
    git = FakeGit(monkeypatch)
    path = await cloner.clone(URL, "main", "scn_abc123")
    assert path == get_settings().work_path / "scn_abc123" / "repo" and path.exists()
    cmd = git.cmd
    assert cmd[:2] == ["git", "clone"] and "--depth" in cmd and cmd[cmd.index("--depth") + 1] == "1"  # N2
    assert "--single-branch" in cmd and git.timeout == 60
    assert cmd[cmd.index("--") + 1] == URL and cmd.index("--") < cmd.index(URL)  # S3
    assert cmd[cmd.index("--branch") + 1] == "main"


@pytest.mark.parametrize("branch", ["--upload-pack=evil", "-x", "a b", "a;rm", "", "x" * 101, "a\nb"])
async def test_s3_bad_branch_rejected_without_running_git(monkeypatch, branch):
    git = FakeGit(monkeypatch)
    with pytest.raises(CloneError):
        await cloner.clone(URL, branch, "scn_abc123")
    assert git.cmd == []


@pytest.mark.parametrize("url", ["http://github.com/x/y", "git@github.com:x/y.git", "file:///etc", "https://a b/c",
                                 "--upload-pack=x", "ext::sh -c id"])
async def test_s3_bad_url_rejected(monkeypatch, url):
    git = FakeGit(monkeypatch)
    with pytest.raises(CloneError):
        await cloner.clone(url, "main", "scn_abc123")
    assert git.cmd == []


@pytest.mark.parametrize("scan_id", ["../x", "a/b", "a\\b", "", "x" * 65])
def test_scan_id_cannot_escape_work_dir(scan_id):
    with pytest.raises(ValueError):
        cloner.scan_dir(scan_id)


async def test_token_goes_via_env_header_never_argv_or_error(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secrettoken1234567890")
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    git = FakeGit(monkeypatch)
    await cloner.clone(URL, "main", "scn_a")
    assert "ghp_secrettoken1234567890" not in " ".join(git.cmd)
    assert git.env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert git.env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")
    assert git.env["GIT_TERMINAL_PROMPT"] == "0"
    # a failing clone whose stderr leaks the token is redacted
    FakeGit(monkeypatch, code=128, stderr="fatal: could not read from https://x:ghp_secrettoken1234567890@github.com/x")
    with pytest.raises(CloneError) as exc:
        await cloner.clone(URL, "main", "scn_b")
    assert "ghp_secrettoken1234567890" not in str(exc.value)
    # never sent to another host
    git = FakeGit(monkeypatch)
    await cloner.clone("https://gitlab.com/x/y", "main", "scn_c")
    assert "GIT_CONFIG_VALUE_0" not in git.env


async def test_s2_clone_env_is_clean(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-supersecretvalue123")
    monkeypatch.setenv("PATCHPILOT_API_KEY", "k-supersecret")
    monkeypatch.setenv("BOOMI_TOKEN", "boomi-secret")
    git = FakeGit(monkeypatch)
    await cloner.clone(URL, "main", "scn_a")
    assert not any(k in git.env for k in ("LLM_API_KEY", "PATCHPILOT_API_KEY", "BOOMI_TOKEN", "GITHUB_TOKEN"))
    assert "PATH" in git.env


def test_s2_clean_env_keeps_only_whitelisted(monkeypatch):
    monkeypatch.setenv("SECRET_THING", "x")
    monkeypatch.setenv("PIP_CACHE_DIR", "/cache")
    env = subproc.clean_env({"EXTRA": "1"})
    assert "SECRET_THING" not in env and env["PIP_CACHE_DIR"] == "/cache" and env["EXTRA"] == "1" and "PATH" in env


async def test_failure_and_timeout_clean_the_workdir(monkeypatch):
    work = get_settings().work_path
    FakeGit(monkeypatch, code=128, stderr="fatal: repository not found")
    with pytest.raises(CloneError, match="repository not found"):
        await cloner.clone(URL, "main", "scn_f")
    assert not (work / "scn_f").exists()  # E13
    FakeGit(monkeypatch, raises=CommandTimeout(["git"], 60))
    with pytest.raises(CloneError, match="timed out after 60s"):
        await cloner.clone(URL, "main", "scn_t")
    assert not (work / "scn_t").exists()


def test_cleanup_removes_readonly_git_files_and_is_idempotent():
    work = get_settings().work_path / "scn_x" / "repo" / ".git" / "objects"
    work.mkdir(parents=True)
    f = work / "pack"
    f.write_text("x")
    f.chmod(stat.S_IREAD)
    cloner.cleanup("scn_x")
    assert not (get_settings().work_path / "scn_x").exists()
    cloner.cleanup("scn_x")  # no error when already gone


# ---- E7 / N2: real subprocesses, loop stays responsive, timeout kills
async def test_e7_subprocess_does_not_block_the_event_loop():
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    t = asyncio.create_task(ticker())
    res = await subproc.run([sys.executable, "-c", "import time; time.sleep(0.6); print('ok')"], timeout=10)
    t.cancel()
    assert res.returncode == 0 and res.stdout.strip() == "ok"
    assert ticks >= 5  # the loop kept running while the child slept


async def test_timeout_kills_the_process():
    with pytest.raises(CommandTimeout):
        await subproc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)


async def test_blocking_fallback_when_loop_has_no_subprocess_support(monkeypatch):
    async def nope(*a, **k):
        raise NotImplementedError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", nope)
    res = await subproc.run([sys.executable, "-c", "print('hi')"], timeout=10)
    assert res.stdout.strip() == "hi"
    with pytest.raises(CommandTimeout):
        await subproc.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
