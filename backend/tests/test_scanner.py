"""T02 scanner + ecosystems: fixtures only, no network. Hardening: N3, E7, L1, L2, L4, L6, L8."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.core.subproc import CommandResult, CommandTimeout
from app.services import ecosystems, scanner
from app.services.scanner import ScanError

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE = (FIXTURES / "osv_sample.json").read_text(encoding="utf-8")


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "requirements.txt").write_text(
        "# deps\nPyYAML==5.3.1  # pinned\nrequests[security]==2.25.1\nJinja2==2.11.2 ; python_version > '3'\n"
        "flask>=1.0\nclick\n-r other.txt\nurllib3==1.26.*\n", encoding="utf-8")
    (repo / "tools" / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {"": {"name": "tools"}, "node_modules/lodash": {"version": "4.17.15"},
                     "node_modules/a/node_modules/b": {"version": "1.0.0"}, "node_modules/l": {"link": True}},
    }), encoding="utf-8")
    (repo / "node_modules" / "x").mkdir(parents=True)
    (repo / "node_modules" / "x" / "package-lock.json").write_text("{}", encoding="utf-8")
    return repo


class FakeCli:
    """Stands in for the osv-scanner binary: patches `which` and `run`."""

    def __init__(self, monkeypatch, *, version="osv-scanner version: 2.7.0", code=1, out=SAMPLE, raises=None):
        self.calls: list[list[str]] = []
        self.version, self.code, self.out, self.raises = version, code, out, raises
        monkeypatch.setattr(scanner, "_find_cli", lambda: "osv-scanner")
        monkeypatch.setattr(scanner, "run", self.run)

    async def run(self, cmd, **kw):
        self.calls.append(list(cmd))
        self.timeout = kw.get("timeout")
        if "--version" in cmd:
            return CommandResult(0, self.version, "")
        if self.raises:
            raise self.raises
        return CommandResult(self.code, self.out, "")


# ---------------------------------------------------------------- ecosystems.detect

def test_detect_lists_pypi_deep_and_npm_generic_skipping_vendored(tmp_path):
    langs = ecosystems.detect(make_repo(tmp_path))
    assert [(x.ecosystem, x.analysis) for x in langs] == [("PyPI", "deep"), ("npm", "generic")]
    assert langs[0].manifests == ["requirements.txt"]
    assert langs[1].manifests == ["tools/package-lock.json"]  # node_modules copy skipped


def test_detect_other_ecosystems(tmp_path):
    for name in ("pom.xml", "go.mod", "Cargo.lock", "composer.lock", "Gemfile.lock", "app.csproj"):
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "go.mod").write_text("", encoding="utf-8")
    langs = {x.ecosystem: x for x in ecosystems.detect(tmp_path)}
    assert set(langs) == {"Maven", "Go", "crates.io", "Packagist", "RubyGems", "NuGet"}
    assert all(x.analysis == "generic" for x in langs.values())
    assert langs["Go"].manifests == ["go.mod"]
    assert ecosystems.detect(tmp_path / "missing") == []


# ---------------------------------------------------------------- scan via CLI fixture

async def test_scan_returns_vulns_with_cve_and_fixed_versions_for_both_ecosystems(tmp_path, monkeypatch):
    cli = FakeCli(monkeypatch)
    vulns = await scanner.scan(make_repo(tmp_path))
    assert len(vulns) >= 3
    assert {v.ecosystem for v in vulns} == {"PyPI", "npm"}
    assert all(v.cve_id.startswith("CVE-") and v.fixed_versions for v in vulns)
    by_pkg = {(v.package, v.cve_id): v for v in vulns}
    yaml = by_pkg[("pyyaml", "CVE-2020-14343")]
    assert yaml.installed_version == "5.3.1" and yaml.fixed_versions == ["5.4"] and yaml.cvss == 9.8
    assert yaml.analysis == "deep" and yaml.manifest == "requirements.txt"
    assert yaml.aliases and "CVE-2020-14343" not in yaml.aliases
    lodash = next(v for v in vulns if v.package == "lodash")
    assert lodash.analysis == "generic" and lodash.ecosystem == "npm"
    # v2 CLI invocation, exit code 1 treated as success
    assert cli.calls[1][:5] == ["osv-scanner", "scan", "source", "-r", "--format"] and cli.timeout == 120  # N3


async def test_scan_uses_v1_syntax_for_old_cli(tmp_path, monkeypatch):
    cli = FakeCli(monkeypatch, version="osv-scanner version: 1.9.2")
    await scanner.scan(make_repo(tmp_path))
    assert cli.calls[1][:3] == ["osv-scanner", "--format", "json"] and "scan" not in cli.calls[1]


async def test_exit_zero_and_no_packages_are_success(tmp_path, monkeypatch):
    FakeCli(monkeypatch, code=0, out='{"results": []}')
    assert await scanner.scan(tmp_path) == []
    FakeCli(monkeypatch, code=128, out="")
    assert await scanner.scan(tmp_path) == []


async def test_duplicate_advisories_for_one_cve_are_merged(tmp_path, monkeypatch):
    def rec(i, aliases):
        return {"id": i, "aliases": aliases, "summary": "s", "details": i * 5 if i.startswith("GHSA") else "",
                "severity": [], "affected": []}

    out = json.dumps({"results": [{"source": {"path": str(tmp_path / "requirements.txt")}, "packages": [{
        "package": {"name": "Foo_Bar", "version": "1.0", "ecosystem": "PyPI"},
        "vulnerabilities": [rec("GHSA-aaaa-bbbb-cccc", ["CVE-2020-1"]),
                            rec("PYSEC-2020-9", ["CVE-2020-1", "GHSA-aaaa-bbbb-cccc"])]}]}]})
    FakeCli(monkeypatch, out=out)
    vulns = await scanner.scan(tmp_path)
    assert len(vulns) == 1 and vulns[0].cve_id == "CVE-2020-1"
    assert vulns[0].package == "foo-bar"  # L2
    assert set(vulns[0].aliases) == {"GHSA-aaaa-bbbb-cccc", "PYSEC-2020-9"}
    assert vulns[0].details.startswith("GHSA")


async def test_unpinned_versions_from_cli_are_skipped(tmp_path, monkeypatch):
    out = json.dumps({"results": [{"source": {"path": "requirements.txt"}, "packages": [
        {"package": {"name": "flask", "version": ">=1.0", "ecosystem": "PyPI"}, "vulnerabilities": [{"id": "CVE-1"}]},
        {"package": {"name": "click", "version": "", "ecosystem": "PyPI"}, "vulnerabilities": [{"id": "CVE-2"}]}]}]})
    FakeCli(monkeypatch, out=out)
    assert await scanner.scan(tmp_path) == []  # L6


# ---------------------------------------------------------------- pure helpers (L1, L2, L4, L8)

def test_l1_versions_are_compared_as_versions_not_strings():
    assert scanner.vkey("5.10") > scanner.vkey("5.9") and "5.10" < "5.9"
    rec = {"affected": [{"package": {"name": "p", "ecosystem": "PyPI"}, "ranges": [{"type": "ECOSYSTEM", "events": [
        {"introduced": "0"}, {"fixed": "5.9"}, {"introduced": "5.10"}, {"fixed": "5.12"}]}]}]}
    assert scanner.fixed_versions_for(rec, "PyPI", "p", "5.10.1") == ["5.12"]  # string compare would pick 5.9
    assert scanner.fixed_versions_for(rec, "PyPI", "p", "5.3") == ["5.9"]
    assert scanner.vkey("v1.2.3") == scanner.vkey("1.2.3") and scanner.vkey("garbage") == scanner.vkey("0")


def test_fixed_versions_ignore_other_packages_and_sort_smallest_first():
    ev = lambda f: [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": f}]}]  # noqa: E731
    rec = {"affected": [{"package": {"name": "Foo-Bar", "ecosystem": "PyPI"}, "ranges": ev("1.10")},
                        {"package": {"name": "foo_bar", "ecosystem": "PyPI"}, "ranges": ev("1.2")},
                        {"package": {"name": "other", "ecosystem": "PyPI"}, "ranges": ev("1.1")}]}
    assert scanner.fixed_versions_for(rec, "PyPI", "FOO.BAR", "1.0") == ["1.2", "1.10"]  # L2 canonical match + L1 order


def test_l2_canonical_names():
    assert scanner.canon("PyPI", "PyYAML") == "pyyaml"
    assert scanner.canon("PyPI", "Foo_Bar.Baz") == "foo-bar-baz"
    assert scanner.canon("npm", "@Scope/Pkg") == "@Scope/Pkg"


def test_l4_cve_id_preference():
    assert scanner.pick_cve_id(["GHSA-x", "PYSEC-1", "CVE-2020-1"]) == "CVE-2020-1"
    assert scanner.pick_cve_id(["PYSEC-1", "GHSA-x"]) == "GHSA-x"
    assert scanner.pick_cve_id(["PYSEC-1", "OSV-9"]) == "PYSEC-1"
    assert scanner.pick_cve_id(["OSV-9"]) == "OSV-9"


def test_l8_cvss_from_vector_severity_word_and_default():
    v3 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
    assert scanner.cvss_for({"severity": [{"type": "CVSS_V3", "score": v3}]}) == (9.8, False)
    v4 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"
    assert scanner.cvss_for({"severity": [{"type": "CVSS_V4", "score": v4}]}) == (9.3, False)
    assert scanner.cvss_for({"severity": [{"type": "CVSS_V2", "score": "AV:N/AC:L/Au:N/C:P/I:P/A:P"}]}) == (7.5, False)
    bogus = {"severity": [{"type": "CVSS_V3", "score": "bogus"}], "database_specific": {"severity": "HIGH"}}
    assert scanner.cvss_for(bogus) == (8.0, True)
    for word, score in {"CRITICAL": 9.5, "HIGH": 8.0, "MODERATE": 5.5, "MEDIUM": 5.5, "LOW": 3.0}.items():
        assert scanner.cvss_for({"affected": [{"database_specific": {"severity": word}}]}) == (score, True)
    assert scanner.cvss_for({}) == (5.0, True)


# ---------------------------------------------------------------- OSV.dev API fallback (N3, L6)

def test_parse_requirements_pins_only_l6():
    text = "PyYAML==5.3.1\nrequests[security]==2.25.1 \\\n  --hash=sha256:abc\nflask>=1\nclick\nx~=1.0\nurllib3==1.26.*\n-e .\n"
    parsed = [(p.name, p.version) for p in scanner.parse_requirements(text, "r.txt")]
    assert parsed == [("PyYAML", "5.3.1"), ("requests", "2.25.1")]


def test_parse_package_lock_v1_and_v3():
    v3 = {"packages": {"": {}, "node_modules/lodash": {"version": "4.17.15"}, "node_modules/@s/p": {"version": "1.0.0"},
                       "node_modules/a/node_modules/b": {"version": "2.0.0"}, "node_modules/l": {"link": True}}}
    assert {(p.name, p.version) for p in scanner.parse_package_lock(json.dumps(v3), "p")} == {
        ("lodash", "4.17.15"), ("@s/p", "1.0.0"), ("b", "2.0.0")}
    v1 = {"dependencies": {"a": {"version": "1.0.0", "dependencies": {"b": {"version": "2.0.0"}}}, "f": {"version": "file:../f"}}}
    assert {(p.name, p.version) for p in scanner.parse_package_lock(json.dumps(v1), "p")} == {("a", "1.0.0"), ("b", "2.0.0")}


def _osv_transport(sample: dict, seen: list):
    records = {v["id"]: v for r in sample["results"] for p in r["packages"] for v in p["vulnerabilities"]}
    index = {(p["package"]["name"].lower(), p["package"]["version"]): [v["id"] for v in p["vulnerabilities"]]
             for r in sample["results"] for p in r["packages"]}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path.endswith("/querybatch"):
            qs = json.loads(request.content)["queries"]
            return httpx.Response(200, json={"results": [
                {"vulns": [{"id": i} for i in index.get((q["package"]["name"], q["version"]), [])]} for q in qs]})
        return httpx.Response(200, json=records[request.url.path.rsplit("/", 1)[1]])

    return httpx.MockTransport(handler)


async def test_api_fallback_when_cli_missing_covers_both_ecosystems(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "_find_cli", lambda: None)
    seen: list = []
    transport = _osv_transport(json.loads(SAMPLE), seen)
    monkeypatch.setattr(scanner, "_http_client", lambda: httpx.AsyncClient(transport=transport, timeout=15))
    vulns = await scanner.scan(make_repo(tmp_path))
    assert {v.ecosystem for v in vulns} == {"PyPI", "npm"}
    assert {v.package for v in vulns} == {"pyyaml", "requests", "jinja2", "lodash"}
    assert ("POST", "/v1/querybatch") in seen
    assert all(v.fixed_versions for v in vulns)


async def test_cli_timeout_falls_back_to_api_then_both_fail_gives_clear_error(tmp_path, monkeypatch):
    FakeCli(monkeypatch, raises=CommandTimeout(["osv-scanner"], 120))

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(scanner, "_http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    with pytest.raises(ScanError) as exc:
        await scanner.scan(make_repo(tmp_path))
    assert "timed out after 120s" in str(exc.value) and "OSV.dev API unavailable" in str(exc.value)  # N3: clear, no hang


async def test_cli_crash_falls_back_to_api(tmp_path, monkeypatch):
    FakeCli(monkeypatch, code=2, out="")
    seen: list = []
    transport = _osv_transport(json.loads(SAMPLE), seen)
    monkeypatch.setattr(scanner, "_http_client", lambda: httpx.AsyncClient(transport=transport))
    assert len(await scanner.scan(make_repo(tmp_path))) >= 3


async def test_api_fallback_with_nothing_parsable_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner, "_find_cli", lambda: None)
    assert await scanner.scan(tmp_path) == []
