"""T08 fix engine. Hardening: S2, S6, S7, S14, S15, N4, E7, E10, E11, E12, E13, L1, L2, L5, L7.

git runs for real on a local fixture repo; pip / pytest / npm are faked (no network). The real end-to-end run on
the demo target (PyPI + npm) is opt-in: `PATCHPILOT_FIX_INTEGRATION=1` (needs network, Node and Python 3.11 via
`FIX_PYTHON`).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.core.subproc import CommandResult, CommandTimeout
from app.models.domain import RawVuln
from app.services import fixer
from app.services.fixer import PatchOutput, PatchRejected, validate_patch
from app.services.llm import LLMError

SCAN = "scn_t08"
MOCK_DIFF = json.loads((fixer.llm.PROMPTS_DIR / "mocks" / "patch_code.json").read_text(encoding="utf-8"))["diff"]

IMPORTER = '''import yaml


def parse_import_payload(raw: str) -> dict:
    """Parse a YAML import payload sent by a client."""
    data = yaml.load(raw)
    if not isinstance(data, dict):
        raise ValueError("import payload must be a mapping")
    return data
'''

FAILING_OUTPUT = ("F.....\n=================================== FAILURES ===================================\n"
                  "demo_app/importer.py:6: in parse_import_payload\n    data = yaml.load(raw)\n"
                  "E   TypeError: load() missing 1 required positional argument: 'Loader'\n"
                  "tests/test_app.py:40: in test_parse\n1 failed, 5 passed in 0.12s")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "core.autocrlf=false", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def _make_repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")
    return root


def _snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def py_repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path / "src", {
        "requirements.txt": "Flask==1.1.2\nPyYAML==5.3.1  # YAML parser\nrequests==2.25.1\n",
        "requirements-dev.txt": "-r requirements.txt\npytest==7.4.4\n",
        "demo_app/__init__.py": "",
        "demo_app/importer.py": IMPORTER,
        "demo_app/settings.py": 'import yaml\nAPI_KEY = "abcd1234supersecret"\n',
        "tests/test_app.py": "from demo_app.importer import parse_import_payload\n",
        "tests/conftest.py": "import yaml\n",
    })


def _vuln(**kw) -> RawVuln:
    base = dict(cve_id="CVE-2020-14343", ecosystem="PyPI", package="PyYAML", installed_version="5.3.1",
                fixed_versions=["5.4"], manifest="requirements.txt", analysis="deep")
    base.update(kw)
    return RawVuln(**base)


def _pin(repo: Path, package: str = "PyYAML") -> str:
    for line in (repo / "requirements.txt").read_text().splitlines():
        if line.lower().startswith(package.lower() + "=="):
            return line.split("==")[1].split()[0]
    return ""


class FakeTools:
    """Replaces `fixer.run` for everything but git: venv, pip, pytest and npm."""

    def __init__(self, monkeypatch, *, install_fail=(), install_timeout=False, test_rc=None, npm=False):
        self.calls: list[tuple[list[str], dict[str, str], Path, float]] = []
        self.install_fail, self.install_timeout, self.test_rc = set(install_fail), install_timeout, test_rc
        self._real = fixer.run
        monkeypatch.setattr(fixer, "run", self.run)
        if npm:
            monkeypatch.setattr(fixer.shutil, "which", lambda name: name if name == "npm" else None)

    def names(self) -> list[str]:
        return [" ".join(Path(c[0]).name if i == 0 else c for i, c in enumerate(cmd)) for cmd, *_ in self.calls]

    async def run(self, cmd, *, cwd=None, env=None, timeout):
        if cmd[0] == "git":
            return await self._real(cmd, cwd=cwd, env=env, timeout=timeout)
        cwd = Path(cwd)
        self.calls.append((list(cmd), dict(env or {}), cwd, timeout))
        if "venv" in cmd:
            Path(cmd[-1]).mkdir(parents=True)
            return CommandResult(0, "", "")
        if "pip" in cmd:
            if self.install_timeout:
                raise CommandTimeout(cmd, timeout)
            if _pin(cwd) in self.install_fail:
                return CommandResult(1, "", "error: subprocess-exited-with-error\nCython build failed")
            return CommandResult(0, "Successfully installed", "")
        if "pytest" in cmd:
            if self.test_rc is not None:
                return CommandResult(self.test_rc, "no tests ran", "")
            ok = "SafeLoader" in (cwd / "demo_app/importer.py").read_text()
            return CommandResult(0, "6 passed", "") if ok else CommandResult(1, FAILING_OUTPUT, "")
        if Path(cmd[0]).name == "npm" and cmd[1] == "install":
            pkg, version = cmd[2].rsplit("@", 1)
            data = json.loads((cwd / "package.json").read_text())
            data["dependencies"][pkg] = version
            (cwd / "package.json").write_text(json.dumps(data, indent=2) + "\n")
            return CommandResult(0, "added 1 package", "")
        if Path(cmd[0]).name == "npm" and cmd[1] == "test":
            return CommandResult(0, "# pass 1", "")
        raise AssertionError(f"unexpected command {cmd}")


class FakeLLM:
    def __init__(self, monkeypatch, diffs: list[str] | None = None, error: bool = False):
        self.calls: list[dict] = []
        self.diffs, self.error = diffs, error
        self._real = fixer.llm.complete_json
        monkeypatch.setattr(fixer.llm, "complete_json", self.complete_json)

    async def complete_json(self, name, variables, schema):
        self.calls.append(variables)
        if self.error:
            raise LLMError("provider down")
        if self.diffs is None:
            return await self._real(name, variables, schema)  # LLM_MODE=mock canned diff
        return PatchOutput(diff=self.diffs[min(len(self.calls), len(self.diffs)) - 1], explanation="x")


# --- acceptance: demo repo, upgrade breaks one call, mock AI patch fixes it --------------------------------------

async def test_upgrade_breaks_call_ai_patch_fixes_it_in_mock_mode(py_repo, monkeypatch):
    tools = FakeTools(monkeypatch)
    llm = FakeLLM(monkeypatch)  # passes through to the real mock-mode llm
    before = _snapshot(py_repo)
    head = _git(py_repo, "rev-parse", "HEAD")

    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])

    assert result.status == "fixed" and result.tests_passed and result.attempts == 1
    assert result.new_version == "5.4" and result.branch == "patchpilot/pyyaml-5.4"
    assert "+PyYAML==5.4  # YAML parser" in result.patch_diff  # comment kept
    assert "+    data = yaml.load(raw, Loader=yaml.SafeLoader)" in result.patch_diff
    repo = result.work_dir
    assert repo is not None and repo.is_relative_to(get_settings().work_path / SCAN)
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() == "patchpilot/pyyaml-5.4"
    log = _git(repo, "log", "--format=%s|%an")
    assert "PatchPilot: adapt code to PyYAML 5.4|PatchPilot" in log and "upgrade PyYAML 5.3.1 -> 5.4" in log
    assert _git(repo, "status", "--porcelain") == ""
    # never leaves the original clone modified
    assert _snapshot(py_repo) == before and _git(py_repo, "rev-parse", "HEAD") == head
    assert _git(py_repo, "status", "--porcelain") == ""
    assert not (repo.parent / "venv").exists()  # E13: venv removed, repo copy kept for the PR stage
    # venv created once, pytest re-run after the patch only
    names = tools.names()
    assert sum("venv" in n for n in names) == 1 and sum("pip install" in n for n in names) == 1
    assert sum("-m pytest -q" in n for n in names) == 2
    pip = next(c for c in tools.calls if "pip" in c[0])[0]
    assert pip[-5:] == ["-r", "requirements.txt", "-r", "requirements-dev.txt", "pytest"]
    assert len(llm.calls) == 1


async def test_tests_pass_right_after_bump_no_ai(py_repo, monkeypatch):
    (py_repo / "demo_app/importer.py").write_text(IMPORTER.replace("yaml.load(raw)", "yaml.load(raw, Loader=yaml.SafeLoader)"))
    _git(py_repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qam", "safe")
    FakeTools(monkeypatch)
    llm = FakeLLM(monkeypatch)
    result = await fixer.fix_package(SCAN, py_repo, "pyyaml", [_vuln()])
    assert result.status == "fixed" and result.attempts == 0 and llm.calls == []


# --- versions (L1, L2, L5, S14) ------------------------------------------------------------------------------

def test_target_version_uses_version_compare_and_covers_all_cves():
    vulns = [_vuln(fixed_versions=["5.10"]), _vuln(cve_id="X", fixed_versions=["5.9"])]
    assert fixer.target_version("5.3.1", vulns) == "5.10"  # L1: 5.10 > 5.9, never string compare
    assert fixer.target_version("5.3.1", [_vuln(fixed_versions=["4.0", "5.4.1", "5.4"])]) == "5.4"
    assert fixer.target_version("5.3.1", [_vuln(), _vuln(cve_id="Y", fixed_versions=[])]) is None  # L5
    assert fixer.target_version("6.0", [_vuln(fixed_versions=["5.4"])]) is None


def test_fallback_versions_only_same_package_newer_stable():
    releases = ["3.0", "5.4", "5.4.1", "6.0", "6.0.1", "6.0.2", "6.0.3", "7.0b1", "not-a-version"]
    assert fixer.fallback_versions("5.4", [_vuln()], releases, 2) == ["5.4.1", "6.0.3"]
    assert fixer.fallback_versions("5.4", [_vuln(fixed_versions=["5.4", "5.4.1"])], [], 2) == ["5.4.1"]
    assert fixer.fallback_versions("5.4", [_vuln()], releases, 0) == []


async def test_no_fixed_version_needs_human_no_fix_available(py_repo, monkeypatch):
    tools = FakeTools(monkeypatch)
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln(fixed_versions=[])])
    assert (result.status, result.reason) == ("needs_human", "no_fix_available") and tools.calls == []


def test_bump_requirements_preserves_formatting_and_normalises_names():
    text = ("# pins\r\nFlask==1.1.2\r\npyyaml[extra] == 5.3.1 ; python_version >= '3.6'  # parser\r\n"
            "requests>=2.0,<3\r\n-r other.txt\r\n")
    out = fixer.bump_requirements(text, "PyYAML", "5.4")  # L2: PyYAML == pyyaml
    assert out == text.replace("== 5.3.1 ;", "== 5.4 ;")
    assert fixer.bump_requirements(text, "requests", "2.31.0") == text.replace(">=2.0,<3", ">=2.31.0")
    assert fixer.bump_requirements("Py_YAML==1.0\n", "py-yaml", "2.0") == "Py_YAML==2.0\n"
    assert fixer.bump_requirements(text, "urllib3", "1.26.5") is None  # S14: never add a package


def test_text_bumps_for_other_ecosystems():
    assert fixer.bump_package_json('{"dependencies": {"lodash": "^4.17.15"}}', "lodash", "4.18.0") == \
        '{"dependencies": {"lodash": "^4.18.0"}}'
    bumps = fixer._TEXT_BUMPS
    assert bumps["go.mod"]("require (\n\tgolang.org/x/net v0.1.0\n)\n", "golang.org/x/net", "0.23.0") == \
        "require (\n\tgolang.org/x/net v0.23.0\n)\n"
    pom = "<dependency><groupId>g</groupId><artifactId>log4j-core</artifactId><version>2.14.1</version></dependency>"
    assert "<version>2.17.1</version>" in bumps["pom.xml"](pom, "org.apache.logging.log4j:log4j-core", "2.17.1")
    assert bumps["pom.xml"](pom.replace("2.14.1", "${log4j.version}"), "x:log4j-core", "2") is None
    assert bumps["Cargo.lock"]('name = "time"\nversion = "0.1.0"\n', "time", "0.2.23") == 'name = "time"\nversion = "0.2.23"\n'
    assert bumps[".csproj"]('<PackageReference Include="Newtonsoft.Json" Version="12.0.1" />', "Newtonsoft.Json",
                            "13.0.1") == '<PackageReference Include="Newtonsoft.Json" Version="13.0.1" />'
    assert bumps["Gemfile.lock"]("GEM\n  specs:\n    rack (2.0.1)\n", "rack", "2.2.8") == "GEM\n  specs:\n    rack (2.2.8)\n"


# --- install fallback and failures (N4, E11, E13) -------------------------------------------------------------

async def test_install_failure_tries_next_and_latest_release(py_repo, monkeypatch):
    tools = FakeTools(monkeypatch, install_fail={"5.4", "5.4.1"})
    FakeLLM(monkeypatch, diffs=[MOCK_DIFF])

    async def releases(self, package):
        return ["5.3.1", "5.4", "5.4.1", "6.0", "6.0.1", "6.0.3", "7.0b1"]
    monkeypatch.setattr(fixer._PyPI, "releases", releases)

    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert result.status == "fixed" and result.new_version == "6.0.3" and result.branch == "patchpilot/pyyaml-6.0.3"
    assert sum("pip install" in n for n in tools.names()) == 3
    assert sum("venv" in n for n in tools.names()) == 1  # venv created once per fix
    assert "+PyYAML==6.0.3" in result.patch_diff and "5.4.1" not in result.patch_diff


async def test_install_fails_three_times_needs_human_and_cleans_up(py_repo, monkeypatch):
    tools = FakeTools(monkeypatch, install_fail={"5.4", "5.4.1", "6.0", "6.0.3"})

    async def releases(self, package):
        return ["5.4.1", "6.0", "6.0.3"]
    monkeypatch.setattr(fixer._PyPI, "releases", releases)
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert (result.status, result.reason) == ("needs_human", "install_failed")
    assert sum("pip install" in n for n in tools.names()) == 3
    assert not (get_settings().work_path / SCAN / "fix-pyyaml").exists()  # E13


async def test_install_timeout_needs_human_without_more_tries(py_repo, monkeypatch):
    tools = FakeTools(monkeypatch, install_timeout=True)
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert (result.status, result.reason) == ("needs_human", "install_failed")  # N4
    pip = [c for c in tools.calls if "pip" in c[0]]
    assert len(pip) == 1 and pip[0][3] == fixer.INSTALL_TIMEOUT_S == 180
    assert not (get_settings().work_path / SCAN / "fix-pyyaml").exists()


async def test_pytest_exit_5_is_no_tests(py_repo, monkeypatch):
    tools = FakeTools(monkeypatch, test_rc=5)
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert (result.status, result.reason) == ("needs_human", "no_tests")  # E11
    test_call = next(c for c in tools.calls if c[0][1:3] == ["-m", "pytest"])
    assert test_call[3] == fixer.TEST_TIMEOUT_S == 120
    assert result.patch_diff and "+PyYAML==5.4" in result.patch_diff  # humans still get the bump diff


@pytest.mark.parametrize("manifest,files", [("poetry.lock", {"poetry.lock": "x"}), ("requirements.txt", {"app.py": "x"}),
                                            ("requirements.txt", {"requirements.txt": "foo==1 --hash=sha256:ab\n"})])
async def test_unsupported_manifest(tmp_path, monkeypatch, manifest, files):
    repo = _make_repo(tmp_path / "r", files)
    FakeTools(monkeypatch)
    result = await fixer.fix_package(SCAN, repo, "PyYAML", [_vuln(manifest=manifest)])
    assert (result.status, result.reason) == ("needs_human", "unsupported_manifest")  # E11


async def test_package_not_pinned_is_never_added(py_repo, monkeypatch):
    FakeTools(monkeypatch)
    result = await fixer.fix_package(SCAN, py_repo, "urllib3", [_vuln(package="urllib3", installed_version="1.26.4",
                                                                       fixed_versions=["1.26.5"])])
    assert (result.status, result.reason) == ("needs_human", "package_not_in_manifest")  # S14


# --- AI patch loop (S6, S7, E10, E12) ------------------------------------------------------------------------

def _diff(path: str, old: str = "    data = yaml.load(raw)", new: str = "    data = yaml.load(raw, Loader=yaml.SafeLoader)"):
    before, after = '    """Parse a YAML import payload sent by a client."""', "    if not isinstance(data, dict):"
    return f"--- a/{path}\n+++ b/{path}\n@@ -5,3 +5,3 @@\n {before}\n-{old}\n+{new}\n {after}\n"


async def test_rejected_patches_count_as_attempts_then_needs_human(py_repo, monkeypatch):
    FakeTools(monkeypatch)
    llm = FakeLLM(monkeypatch, diffs=[_diff("tests/test_app.py"), _diff("../outside.py")])
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert (result.status, result.reason, result.attempts) == ("needs_human", "ai_patch_failed", 2)
    assert len(llm.calls) == 2
    assert "rejected" in llm.calls[1]["previous_attempt"] and "tests/test_app.py" in llm.calls[1]["previous_attempt"]
    assert llm.calls[0]["previous_attempt"] == "(none)"


async def test_git_apply_failure_feeds_error_to_next_attempt(py_repo, monkeypatch):
    FakeTools(monkeypatch)
    bad = _diff("demo_app/importer.py", old="    data = something_else(raw)")
    llm = FakeLLM(monkeypatch, diffs=[bad, MOCK_DIFF])
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert result.status == "fixed" and result.attempts == 2  # E12: failed apply = one attempt
    assert "git apply failed" in llm.calls[1]["previous_attempt"]
    assert "something_else" not in result.patch_diff


async def test_patch_that_still_fails_retries_once_with_new_test_output(py_repo, monkeypatch):
    FakeTools(monkeypatch)
    noop = _diff("demo_app/importer.py", new="    data = yaml.load(raw)  # still broken")
    llm = FakeLLM(monkeypatch, diffs=[noop, noop])
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert (result.status, result.reason, result.attempts) == ("needs_human", "ai_patch_failed", 2)
    assert "tests still fail" in llm.calls[1]["previous_attempt"]
    assert "still broken" not in result.patch_diff  # failed attempt rolled back; bump kept for the human


async def test_llm_unavailable_needs_human(py_repo, monkeypatch):
    FakeTools(monkeypatch)
    FakeLLM(monkeypatch, error=True)
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert (result.status, result.reason) == ("needs_human", "ai_unavailable")


async def test_prompt_gets_masked_capped_non_test_files(py_repo, monkeypatch):
    big = "import yaml\n" + "".join(f"x{i} = {i}\n" for i in range(600))
    for i in range(3):
        (py_repo / f"demo_app/extra{i}.py").write_text(big)
    _git(py_repo, "add", "-A")
    _git(py_repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qm", "more")
    FakeTools(monkeypatch)
    llm = FakeLLM(monkeypatch)
    await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    files = llm.calls[0]["files"]
    assert files.count("BEGIN UNTRUSTED CODE") == fixer.MAX_PATCH_FILES == 3  # E10
    assert files.index("BEGIN UNTRUSTED CODE demo_app/importer.py") == files.index("BEGIN UNTRUSTED CODE")  # traceback first
    assert "tests/" not in files and "conftest" not in files  # S6: tests never offered
    assert "x450 =" not in files and "more lines not shown" in files  # E10: 400 lines per file
    settings_block = "BEGIN UNTRUSTED CODE demo_app/settings.py"
    assert settings_block not in files or "abcd1234supersecret" not in files  # S7
    assert "Loader" in llm.calls[0]["test_output"] and llm.calls[0]["new_version"] == "5.4"


def test_prompt_masks_secrets_in_files(py_repo, tmp_path):
    fix = fixer._Fix(SCAN, py_repo, "PyYAML", [_vuln()])
    fix.repo = py_repo
    block = fix._file_blocks(["demo_app/settings.py"])
    assert "abcd1234supersecret" not in block and "API_KEY" in block  # S7


@pytest.mark.parametrize("diff,error", [
    ("--- a/tests/test_app.py\n+++ b/tests/test_app.py\n@@ -1 +1 @@\n-a\n+b\n", "test, CI or build"),
    ("--- a/conftest.py\n+++ b/conftest.py\n@@ -1 +1 @@\n-a\n+b\n", "test, CI or build"),
    ("--- a/setup.py\n+++ b/setup.py\n@@ -1 +1 @@\n-a\n+b\n", "test, CI or build"),
    ("--- a/.github/workflows/ci.yml\n+++ b/.github/workflows/ci.yml\n@@ -1 +1 @@\n-a\n+b\n", "test, CI or build"),
    ("--- a/../evil.py\n+++ b/../evil.py\n@@ -1 +1 @@\n-a\n+b\n", "outside the repository"),
    ("--- /etc/passwd\n+++ /etc/passwd\n@@ -1 +1 @@\n-a\n+b\n", "absolute path"),
    ("--- a/C:/x.py\n+++ b/C:/x.py\n@@ -1 +1 @@\n-a\n+b\n", "absolute path"),
    ("--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+b\n", "creating or deleting"),
    ("diff --git a/app.py b/x.py\nrename from app.py\nrename to x.py\n", "unsupported diff operation"),
    ("--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-a\n+b\n", "not one of the files"),
    ("--- a/app.py\n+++ b/app.py\n@@ -1,201 +1,1 @@\n" + "-x\n" * 201, "max 200"),
    ("--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-PyYAML==5.4\n+evilpkg==1.0\n", "only change the PyYAML"),
    ("just text", "no --- a/<path>"),
    ("", "empty diff"),
])
def test_validate_patch_rejects(diff, error):
    with pytest.raises(PatchRejected, match=error.replace("(", r"\(")):
        validate_patch(diff, {"app.py"}, "requirements.txt", "PyYAML")


def test_validate_patch_accepts_allowed_file_and_target_package_line():
    diff = ("--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n--- comment line\n+x = 1\n"
            "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-PyYAML==5.4\n+pyyaml==6.0.1\n")
    assert validate_patch(diff, {"app.py"}, "requirements.txt", "PyYAML") == ["app.py", "requirements.txt"]


async def test_ai_may_not_pin_target_below_bump(py_repo, monkeypatch):
    FakeTools(monkeypatch)
    down = "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -2 +2 @@\n-PyYAML==5.4  # YAML parser\n+PyYAML==5.3.1\n"
    FakeLLM(monkeypatch, diffs=[down, down])
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert result.status == "needs_human" and "+PyYAML==5.4" in result.patch_diff  # S14


# --- clean env, no scripts, async subprocesses (S2, S15, E7) --------------------------------------------------

async def test_tools_get_clean_env_without_secrets(py_repo, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-live-should-not-leak-123")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_shouldnotleak1234567890")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "nope")
    tools = FakeTools(monkeypatch)
    FakeLLM(monkeypatch)
    await fixer.fix_package(SCAN, py_repo, "PyYAML", [_vuln()])
    assert tools.calls
    for cmd, env, cwd, _ in tools.calls:
        assert not {"LLM_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY"} & set(env)  # S2
        assert "sk-live" not in json.dumps(env) and "ghp_" not in json.dumps(env)
        assert get_settings().work_path in cwd.parents  # runs inside WORK_DIR, never the app folder
    pip_env = next(c[1] for c in tools.calls if "pip" in c[0])
    assert pip_env["PIP_CACHE_DIR"] == str(get_settings().work_path / "cache" / "pip")  # N4 shared cache


def test_fixer_never_blocks_the_event_loop():
    source = Path(fixer.__file__).read_text(encoding="utf-8")
    assert "subprocess.run" not in source and "os.system" not in source and "Popen" not in source  # E7


@pytest.fixture
def npm_repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path / "npmsrc", {
        "package.json": json.dumps({"name": "t", "scripts": {"test": "node --test"},
                                    "dependencies": {"lodash": "4.17.15"}}, indent=2) + "\n",
        "package-lock.json": "{}\n",
        "report.js": "const _ = require('lodash');\n",
    })


def _npm_vuln(**kw) -> RawVuln:
    base = dict(cve_id="CVE-2021-23337", ecosystem="npm", package="lodash", installed_version="4.17.15",
                fixed_versions=["4.18.0"], manifest="package-lock.json")
    base.update(kw)
    return RawVuln(**base)


async def test_npm_bump_never_runs_scripts(npm_repo, monkeypatch):
    tools = FakeTools(monkeypatch, npm=True)
    result = await fixer.fix_package(SCAN, npm_repo, "lodash", [_npm_vuln()])
    assert result.status == "fixed" and result.tests_passed and result.branch == "patchpilot/lodash-4.18.0"
    install, test = tools.calls[0], tools.calls[1]
    assert install[0][1:] == ["install", "lodash@4.18.0", "--ignore-scripts", "--no-audit", "--no-fund",
                              "--save-prod", "--save-exact"]  # S15
    assert install[1]["npm_config_ignore_scripts"] == "true" and test[0][1] == "test"
    assert '"lodash": "4.18.0"' in result.patch_diff


async def test_npm_missing_toolchain_is_fixed_untested(npm_repo, monkeypatch):
    tools = FakeTools(monkeypatch)
    monkeypatch.setattr(fixer.shutil, "which", lambda name: None)
    result = await fixer.fix_package(SCAN, npm_repo, "lodash", [_npm_vuln()])
    assert (result.status, result.tests_passed, result.reason) == ("fixed_untested", False, "toolchain_missing")
    assert '+    "lodash": "4.18.0"' in result.patch_diff and tools.calls == []
    assert _git(result.work_dir, "rev-parse", "--abbrev-ref", "HEAD").strip() == "patchpilot/lodash-4.18.0"


async def test_other_ecosystem_without_toolchain_bumps_manifest_untested(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path / "go", {"go.mod": "module x\n\nrequire golang.org/x/net v0.1.0\n"})
    FakeTools(monkeypatch)
    monkeypatch.setattr(fixer.shutil, "which", lambda name: None)
    vuln = RawVuln(cve_id="CVE-2023-44487", ecosystem="Go", package="golang.org/x/net", installed_version="0.1.0",
                   fixed_versions=["0.17.0"], manifest="go.mod")
    result = await fixer.fix_package(SCAN, repo, "golang.org/x/net", [vuln])
    assert result.status == "fixed_untested" and "+require golang.org/x/net v0.17.0" in result.patch_diff
    assert result.branch == "patchpilot/golang.org-x-net-0.17.0"


# --- L7: one fix per package ---------------------------------------------------------------------------------

async def test_one_fix_covers_all_cves_of_the_package(py_repo, monkeypatch):
    FakeTools(monkeypatch)
    FakeLLM(monkeypatch)
    vulns = [_vuln(), _vuln(cve_id="CVE-2020-1747", fixed_versions=["5.3.1", "5.4"]),
             _vuln(cve_id="GHSA-xxxx", fixed_versions=["5.4"])]
    result = await fixer.fix_package(SCAN, py_repo, "PyYAML", vulns)
    assert result.status == "fixed" and result.new_version == "5.4"
    body = _git(result.work_dir, "log", "-1", "--skip=1", "--format=%b")
    assert "CVE-2020-14343, CVE-2020-1747, GHSA-xxxx" in body


# --- opt-in real run on the demo target (needs network, Python 3.11, Node) ------------------------------------

@pytest.mark.skipif(os.environ.get("PATCHPILOT_FIX_INTEGRATION") != "1", reason="set PATCHPILOT_FIX_INTEGRATION=1")
async def test_demo_target_real_fix_pypi_and_npm(tmp_path):
    src = os.environ.get("PATCHPILOT_DEMO_TARGET", "https://github.com/BommepalliRoop/demo-target")
    repo = tmp_path / "demo"
    subprocess.run(["git", "clone", "-q", "--depth", "1", src, str(repo)], check=True)
    before = _snapshot(repo)
    py = await fixer.fix_package(SCAN, repo, "PyYAML", [_vuln()])
    assert py.status == "fixed" and py.tests_passed and py.attempts == 1, py.reason
    npm = await fixer.fix_package(SCAN, repo, "lodash", [_npm_vuln()])
    assert npm.status == "fixed" and npm.new_version == "4.18.0", npm.reason
    assert "package-lock.json" in npm.patch_diff and "package.json" in npm.patch_diff
    assert _snapshot(repo) == before
