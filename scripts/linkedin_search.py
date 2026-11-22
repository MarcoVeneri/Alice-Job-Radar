"""Read public Italian search results; confirm work arrangements on each vacancy."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from jobsora_extract import clean, field

TERMS = ("ufficio gare", "tender specialist", "PMO", "back office commerciale", "sales operations", "project coordinator")
MODE = re.compile(r"\b(?:smart[ -]working|lavoro (?:ibrido|da remoto|agile)|modalità ibrida|hybrid (?:work(?:ing)?|model)|work from home|fully remote)\b", re.I)
NEGATIVE = re.compile(r"(?:\bnon\b|\bno\b|\bsenza\b|esclus[oa]).{0,45}(?:smart working|ibrid|hybrid|remot)|(?:smart working|remoto).{0,18}non (?:previsto|possibile)|(?:esclusivamente|solo) in (?:sede|presenza)", re.I)


def page(url):
    with urlopen(Request(url, headers={"User-Agent":"AliceJobRadar/1.0"}), timeout=8) as response:
        return response.read(450000).decode("utf-8", "replace")


def discover():
    pairs = [(term, area) for term in TERMS for area in ("Firenze, Toscana, Italia", "Italia")]
    candidates = {}
    logs = []
    def search(pair):
        term, area = pair
        params = {"keywords":term,"location":area,"f_WT":"2,3","start":0}
        if area == "Italia":
            params["geoId"] = "103350119"
        url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + urlencode(params)
        log = {"source":"LinkedIn Jobs","query":term,"area":area,"method":"public_listing","evidenceUrls":[url],"checkedAt":datetime.now(timezone.utc).isoformat()}
        try:
            body = page(url)
            rows = []
            for block in re.findall(r"<li\b[^>]*>(.*?)</li>", body, re.I|re.S):
                m = re.search(r"urn:li:jobPosting:(\d+)",block)
                location = field(block,"span","job-search-card__location")
                if m and re.search(r"\b(?:Italia|Italy)\b",location,re.I):
                    rows.append((m[1],location))
            log["outcome"] = "success: public vacancy cards" if "job-search-card" in body else "unconfirmed: no readable vacancy cards"
            return log,rows
        except OSError as exc:
            log["outcome"]="unavailable: "+str(exc)[:120]
            return log,[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for log,rows in pool.map(search,pairs):
            logs.append(log)
            candidates.update(rows)
    def verify(item):
        ident,loc=item
        try:
            body=page("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"+ident)
        except OSError:
            return None
        desc=field(body,"div","show-more-less-html__markup")
        title=field(body,"h2","topcard__title")
        company=field(body,"a","topcard__org-name-link")
        mode=MODE.search(desc)
        if not (mode and title and company) or NEGATIVE.search(desc) or re.search(r"no longer accepting applications|non accetta più candidature",clean(body),re.I):
            return None
        return {"title":title,"company":company,"place":loc,"url":"https://www.linkedin.com/jobs/view/"+ident,
                "details":desc[max(0,mode.start()-130):mode.end()+170],"mode":"Smart working previsto"}
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows=[("LinkedIn Jobs","linkedin",r) for r in pool.map(verify,candidates.items()) if r]
    return rows,logs
