"""Public search-index fallback for LinkedIn/Indeed blocked guest search pages.

This only discovers individual posting identifiers, NEVER validates or publishes
a job. The primary scanner must open and check each original individual posting.
No authentication, scraping around challenges, or claims of exhaustive coverage.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import re

GROUPS = (
    ("ufficio gare", "tender specialist"),
    ("bid coordinator", "proposal specialist"),
    ("PMO", "project support"),
    ("back office commerciale", "sales operations"),
    ("order management", "segreteria commerciale"),
)
from tuscany_scope import PROVINCES
AREAS = tuple(p + " Toscana" for p in PROVINCES) + ("Toscana", "Valdarno Toscana")
LI_RE = re.compile(r"/jobs/view/(?:[^/?#]*?-)?(\d{9,})(?:[/?#]|$)", re.I)
JK_RE = re.compile(r"[0-9a-f]{12,}", re.I)

def _utc():
    return datetime.now(timezone.utc).isoformat()

def _get_rss(query):
    url = "https://www.bing.com/search?" + urlencode({
        "q": query, "format": "rss", "cc": "IT", "setlang": "it", "mkt": "it-IT",
    })
    req = Request(url, headers={
        "User-Agent": "AliceJobRadar/6.49 public indexed discovery",
        "Accept": "application/rss+xml,application/xml,text/xml",
    })
    with urlopen(req, timeout=9) as response:
        body = response.read(200000)
    root = ElementTree.fromstring(body)
    return url, [
        (item.findtext("link") or "", item.findtext("title") or "")
        for item in root.findall("./channel/item")
    ]

def _extract(url, platform):
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if platform == "LinkedIn Jobs":
        if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
            return None
        match = LI_RE.search(parts.path)
        return match.group(1) if match else None
    if not (host == "indeed.com" or host.endswith(".indeed.com")):
        return None
    key = (parse_qs(parts.query).get("jk") or parse_qs(parts.query).get("vjk") or [""])[0]
    return key if JK_RE.fullmatch(key) else None

def _one(task):
    platform, terms, area = task
    site = "site:linkedin.com/jobs/view" if platform == "LinkedIn Jobs" else "site:it.indeed.com"
    # Avoid mandatory "smart working" terms here: the individual posting
    # determines modality, just as someone browsing would check it.
    query = site + " (" + " OR ".join('"'+t+'"' for t in terms) + ") " + area
    record = {
        "source": platform, "query":query, "area":area,
        "checkedAt":_utc(), "method":"indexed_public_discovery",
        "candidateLinksFound":0,
    }
    try:
        url, listings = _get_rss(query)
        record["evidenceUrls"] = [url]
        extracted = []
        for link, title in listings:
            key = _extract(link, platform)
            if key:
                extracted.append((key,link,title))
        record["candidateLinksFound"] = len(extracted)
        record["outcome"] = (
            "success: " + str(len(extracted)) + " indexed posting links"
            if extracted else "unconfirmed: zero relevant indexed posting links")
        return record, extracted
    except Exception as exc:
        record["outcome"] = "unavailable: " + str(exc)[:135]
        return record, []

def discover_indexed(platforms=("LinkedIn Jobs","Indeed Italia")):
    tasks = [(provider, terms, area) for provider in platforms
             for terms in GROUPS for area in AREAS]
    logs = []
    linkedin = {}
    indeed = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for (platform, terms, area), (log, listings) in zip(tasks, pool.map(_one, tasks)):
            logs.append(log)
            for key, link, title in listings:
                if platform == "LinkedIn Jobs":
                    # Search geography is a hint, not proof of local eligibility.
                    linkedin.setdefault(key, area+" (da verificare)")
                else:
                    indeed.append(key)
    return linkedin, list(dict.fromkeys(indeed)), logs

def self_test():
    assert _extract("https://it.linkedin.com/jobs/view/tender-specialist-at-azienda-4491829304", "LinkedIn Jobs") == "4491829304"
    assert _extract("https://it.indeed.com/viewjob?jk=51921db8917b2edf", "Indeed Italia") == "51921db8917b2edf"
    assert _extract("https://fake.example/jobs/view/tender-4491829304", "LinkedIn Jobs") is None
    assert _extract("https://fake.example/viewjob?jk=51921db8917b2edf", "Indeed Italia") is None
    assert len(AREAS) == 12 and "Italia" not in AREAS
    print("Indexed fallback: safe posting IDs and Tuscany cross-portal queries OK")

if __name__ == "__main__":
    self_test()
