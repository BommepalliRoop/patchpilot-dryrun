"""T02 threat intel: KEV hit/miss, EPSS present, feed down (N12). No network."""
from __future__ import annotations

import json
import os
import time

import httpx

from app.core.config import get_settings, reset_settings_cache
from app.models.domain import RawVuln
from app.services import threat_intel


def vuln(cve: str, aliases: list[str] | None = None) -> RawVuln:
    return RawVuln(cve_id=cve, aliases=aliases or [], ecosystem="PyPI", package="p", installed_version="1")


def set_mode(monkeypatch, mode: str) -> None:
    monkeypatch.setenv("THREAT_INTEL", mode)
    reset_settings_cache()


async def test_off_leaves_everything_untouched(monkeypatch):
    set_mode(monkeypatch, "off")
    out = await threat_intel.enrich([vuln("CVE-2021-44228")])
    assert out[0].kev is False and out[0].epss is None and out[0].threat_feed_unavailable is False


async def test_mock_kev_hit_miss_and_epss_present(monkeypatch):
    set_mode(monkeypatch, "mock")
    hit, miss, via_alias, nodata = (vuln("CVE-2021-44228"), vuln("CVE-2020-14343"),
                                    vuln("GHSA-xxxx", ["CVE-2022-22965"]), vuln("CVE-2099-0001"))
    await threat_intel.enrich([hit, miss, via_alias, nodata])
    assert hit.kev and hit.kev_date_added == "2021-12-10" and hit.epss == 0.944 and hit.epss_percentile == 0.9998
    assert miss.kev is False and miss.kev_date_added is None
    assert miss.epss == 0.0598 and miss.epss_percentile == 0.9326  # PyYAML demo CVE
    assert via_alias.kev and via_alias.kev_date_added == "2022-04-04"
    assert nodata.kev is False and nodata.epss is None and nodata.threat_feed_unavailable is False


def live_client(handler, monkeypatch, calls: list):
    def wrapped(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return handler(request)

    monkeypatch.setattr(threat_intel, "_http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(wrapped)))


KEV_FEED = {"vulnerabilities": [{"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10"}]}


def ok_handler(request: httpx.Request) -> httpx.Response:
    if "cisa.gov" in str(request.url):
        return httpx.Response(200, json=KEV_FEED)
    ids = request.url.params["cve"].split(",")
    return httpx.Response(200, json={"data": [{"cve": i, "epss": "0.5", "percentile": "0.99"} for i in ids if i != "CVE-1-1"]})


async def test_live_enrich_batches_epss_and_caches(monkeypatch):
    set_mode(monkeypatch, "live")
    calls: list[str] = []
    live_client(ok_handler, monkeypatch, calls)
    vulns = [vuln(f"CVE-2020-{i}") for i in range(250)] + [vuln("CVE-2021-44228"), vuln("CVE-1-1")]
    await threat_intel.enrich(vulns)
    epss_calls = [c for c in calls if "first.org" in c]
    assert len(epss_calls) == 3  # 252 ids -> batches of <=100
    assert vulns[250].kev and vulns[250].epss == 0.5
    assert vulns[251].epss is None and not vulns[251].threat_feed_unavailable
    cache = get_settings().work_path / "cache"
    assert (cache / "kev.json").exists() and (cache / "epss.json").exists()
    before = len(calls)
    again = [vuln("CVE-2021-44228"), vuln("CVE-2020-5")]
    await threat_intel.enrich(again)  # served from the daily / 24 h caches
    assert len(calls) == before and again[0].kev and again[1].epss == 0.5


async def test_feed_down_gives_kev_false_epss_none_and_no_exception(monkeypatch):
    set_mode(monkeypatch, "live")
    calls: list[str] = []
    live_client(lambda r: httpx.Response(503), monkeypatch, calls)
    v = vuln("CVE-2021-44228")
    out = await threat_intel.enrich([v])
    assert out == [v] and v.kev is False and v.epss is None and v.epss_percentile is None
    assert v.threat_feed_unavailable is True
    assert len(calls) == 4  # KEV: 1 try + 1 retry, EPSS: 1 try + 1 retry — no retry storm


async def test_network_error_and_garbage_body_do_not_raise(monkeypatch):
    set_mode(monkeypatch, "live")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow")

    live_client(boom, monkeypatch, [])
    v = vuln("CVE-2021-44228")
    await threat_intel.enrich([v])
    assert v.kev is False and v.threat_feed_unavailable

    live_client(lambda r: httpx.Response(200, content=b"<html>not json</html>"), monkeypatch, [])
    v2 = vuln("CVE-2021-44229")
    await threat_intel.enrich([v2])
    assert v2.kev is False and v2.epss is None and v2.threat_feed_unavailable


async def test_stale_kev_cache_is_used_when_feed_is_down(monkeypatch):
    set_mode(monkeypatch, "live")
    cache = get_settings().work_path / "cache"
    cache.mkdir(parents=True)
    f = cache / "kev.json"
    f.write_text(json.dumps(KEV_FEED), encoding="utf-8")
    old = time.time() - 3 * 24 * 3600
    os.utime(f, (old, old))
    live_client(lambda r: httpx.Response(500), monkeypatch, [])
    v = vuln("CVE-2021-44228")
    await threat_intel.enrich([v])
    assert v.kev is True and v.kev_date_added == "2021-12-10"
    assert v.threat_feed_unavailable  # EPSS was down


async def test_empty_list_makes_no_calls(monkeypatch):
    set_mode(monkeypatch, "live")
    calls: list[str] = []
    live_client(ok_handler, monkeypatch, calls)
    assert await threat_intel.enrich([]) == [] and calls == []
