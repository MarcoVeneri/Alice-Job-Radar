"""Public nationwide catalog discovery.

Search every configured source, but never publish an indexed listing by itself.
Only individual live JobPosting pages with explicit hybrid/remote evidence
become candidates. A blocked source does not stop the rest of the catalog.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from jobsora_extract import ROLE, clean
from linkedin_search import MODE, NEGATIVE, EXPIRED, _json_ld_jobs
from verify_vacancies import _role, _eligible_country

IGNORED = {"LinkedIn Jobs", "Indeed Italia"}
SOURCE = Path("data/source_catalog.json")
QUERY_ROLES = '("ufficio gare" OR tender OR "PMO" OR "sales operations" OR "back office")'
GENERIC = {"", "/", "/jobs", "/search", "/careers", "/lavoro"}


def _read(url: str, limit=350000) -> str:
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; AliceJobRadar/6.5; public job research)",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml,text/xml",
    })
    with urlopen(req, timeout=9) as response:
        return response.read(limit).decode("utf-8", "replace")


def _host(item) -> str:
    domain = str(item.get("searchDomain") or "").strip().lower()
    if not domain:
        domain = urlsplit(str(item.get("url") or "")).hostname or ""
    return domain.removeprefix("www.").strip(".")


def _rss_links(source):
    host = _host(source)
    name = str(source.get("name") or "").strip()
    # One independent query per source: cannot equate a submitted request
    # with a checked or verified individual posting.
    query = (f"site:{host} {QUERY_ROLES}" if host else
             f'"{name}" (tender OR "ufficio gare" OR PMO)')
    url = "https://www.bing.com/search?" + urlencode({
        "format": "rss", "cc": "IT", "setlang": "it", "mkt": "it-IT", "q": query,
    })
    body = _read(url, 250000)
    root = ElementTree.fromstring(body)
    items = [(node.findtext("link") or "", node.findtext("title") or "")
             for node in root.findall("./channel/item")]
    out = []
    for link, title in items:
        parsed = urlsplit(link)
        if parsed.scheme != "https" or not parsed.hostname:
            continue
        if parsed.path.rstrip("/").lower() in GENERIC:
            continue
        if not (ROLE.search(title) or re.search(
              r"ufficio gare|back.office|bid|proposal|sales operations|"
              r"project (support|coordinator)|procurement|gestione ordini", title, re.I)):
            continue
        if host and host not in parsed.hostname.lower():
            continue
        if link not in out:
            out.append(link)
    return url, out[:2]


def _original_posting(url):
    page = _read(url)
    if EXPIRED.search(page[:140000]):
        return None
    for job in _json_ld_jobs(page):
        title = clean(job.get("title"))
        employer = job.get("hiringOrganization") or {}
        company = clean(employer.get("name") if isinstance(employer, dict) else employer)
        if not company or not title or not _role({"title": title}):
            continue
        expiry = str(job.get("validThrough") or "9999")[:10]
        if expiry < date.today().isoformat():
            continue
        if not _eligible_country(job):
            continue
        details = clean(job.get("description"))
        mode_match = MODE.search(details)
        tele = str(job.get("jobLocationType") or "").upper() == "TELECOMMUTE"
        if (not tele and not mode_match) or NEGATIVE.search(details):
            continue
        loc = job.get("jobLocation") or {}
        if isinstance(loc, list):
            loc = loc[0] if loc else {}
        place = ""
        if isinstance(loc, dict):
            address = loc.get("address") or {}
            if isinstance(address, dict):
                place = clean(address.get("addressLocality") or address.get("addressRegion"))
        evidence = (details[max(0, mode_match.start()-100):mode_match.end()+150]
                    if mode_match else details[:180])
        return {"title": title, "company": company,
                "place": place or "Italia / Europa (da confermare)",
                "url": url, "details": evidence,
                "mode": "Da remoto" if tele else "Ibrido/smart working",
                "telecommuteEvidence": bool(tele)}
    return None


def _probe(item):
    name = str(item.get("name") or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    log = {"source": name, "method": "catalog_source_individual_vacancy_probe",
           "checkedAt": now, "candidateLinksFound": 0,
           "specificJobPagesOpened": 0, "specificJobPagesVerified": 0,
           "evidenceUrls": []}
    if name in IGNORED or item.get("smartRecruitersAccount"):
        log["outcome"] = "handled_by_primary_or_ats_adapter"
        return [], log
    try:
        search_url, links = _rss_links(item)
        log["evidenceUrls"] = [search_url]
        log["candidateLinksFound"] = len(links)
    except Exception as exc:
        log["outcome"] = "unavailable: indexed discovery " + str(exc)[:130]
        return [], log
    rows = []
    for link in links:
        log["specificJobPagesOpened"] += 1
        try:
            detail = _original_posting(link)
            if detail:
                rows.append((name, "employer", detail))
                log["specificJobPagesVerified"] += 1
        except Exception:
            continue
    log["outcome"] = ("success: verified original vacancy" if rows
                      else "unconfirmed: no verified original posting")
    return rows, log


def discover_catalog(max_workers=12):
    sources = json.loads(SOURCE.read_text(encoding="utf-8")).get("sources", [])
    if not isinstance(sources, list):
        return [], []
    # Every source is processed independently. No portal failure aborts a scan.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(_probe, sources))
    return ([row for rows, _ in results for row in rows],
            [log for _, log in results])


def self_test():
    assert _host({"url":"https://www.example.it/jobs"}) == "example.it"
    assert _host({"searchDomain":"www.example.it"}) == "example.it"
    assert not _original_posting.__defaults__
    names = json.loads(SOURCE.read_text(encoding="utf-8"))["sources"]
    assert len(names) >= 200
    print("Catalog source checks configured:", len(names), "distinct catalogue entries")


if __name__ == "__main__":
    self_test()
