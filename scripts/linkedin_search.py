"""Read public Italian search results; confirm work arrangements on each vacancy."""
import re
import time
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from jobsora_extract import clean, field

TERMS = ("ufficio gare", "tender specialist", "PMO", "back office commerciale", "sales operations", "project coordinator", "gare e appalti", "bid coordinator", "proposal specialist", "project support", "segreteria commerciale", "order management")
MODE = re.compile(r"\b(?:smart[ -]working|lavoro (?:ibrido|da remoto|agile)|modalità ibrida|hybrid (?:work(?:ing)?|model)|work from home|fully remote)\b", re.I)
NEGATIVE = re.compile(r"(?:\bnon\b|\bno\b|\bsenza\b|esclus[oa]).{0,45}(?:smart working|ibrid|hybrid|remot)|(?:smart working|remoto).{0,18}non (?:previsto|possibile)|(?:esclusivamente|solo) in (?:sede|presenza)", re.I)


def page(url):
    with urlopen(Request(url, headers={"User-Agent":"AliceJobRadar/1.0"}), timeout=8) as response:
        return response.read(450000).decode("utf-8", "replace")


def discover(previous_logs=()):
    pairs = [(term, area) for term in TERMS for area in ("Firenze, Toscana, Italia", "Italia")]
    prior = {(log.get("query"),log.get("area")):log for log in previous_logs if log.get("source")=="LinkedIn Jobs"}
    pairs.sort(key=lambda pair: not prior.get(pair,{}).get("outcome","").startswith(("unavailable","unconfirmed")))
    candidates = {}
    logs = []
    def search(pair):
        term, area = pair
        params = {"keywords":term,"location":area,"f_WT":"2,3","start":0}
        if term not in TERMS[:6]:
            params.pop("f_WT")
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
            delay = getattr(exc,"headers",{}).get("Retry-After") if getattr(exc,"headers",None) else None
            pause = 60
            if delay:
                try: pause = max(60,int(delay))
                except ValueError:
                    try: pause=max(60,int(parsedate_to_datetime(delay).timestamp()-time.time())+1)
                    except (TypeError,ValueError): pass
            log["retryAfterEpoch"]=int(time.time())+pause
            log["outcome"]="unavailable: "+str(exc)[:120]
            return log,[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for log,rows in pool.map(search,[pair for pair in pairs if prior.get(pair,{}).get("retryAfterEpoch",0)<=time.time()]):
            logs.append(log)
            candidates.update(rows)
    # Retry transient failures once per scan, respecting the server's waiting period.
    retryable = [log for log in logs if any(code in log["outcome"]
                 for code in ("429", "502", "503", "504", "timed out"))
                 and log.get("retryAfterEpoch", 0) <= time.time() + 61]
    if retryable:
        time.sleep(max(0, max(log["retryAfterEpoch"] for log in retryable) - time.time()))
        with ThreadPoolExecutor(max_workers=2) as pool:
            for old, (updated, rows) in zip(retryable, pool.map(search, [(log["query"], log["area"]) for log in retryable])):
                updated["firstOutcome"] = old["outcome"]
                old.clear()
                old.update(updated)
                candidates.update(rows)
    for pair in pairs:
        if prior.get(pair,{}).get("retryAfterEpoch",0)>time.time() and not any((l["query"],l["area"])==pair for l in logs):
            logs.append(dict(prior[pair],deferred=True))
    for log in logs:
        if not log["outcome"].startswith("success:"):
            log["alternateSearch"]="https://it.indeed.com/jobs?"+urlencode({"q":log["query"],"l":log["area"]})
    alternate_logs = []
    alternate_rows = []
    def indeed(log):
        import json
        from datetime import date
        from urllib.parse import urljoin
        url = log["alternateSearch"]
        record = dict(source="Indeed Italia",query=log["query"],area=log["area"],method="direct_fallback",evidenceUrls=[url],checkedAt=datetime.now(timezone.utc).isoformat())
        found=[]
        try:
            listing=page(url)
            keys=list(dict.fromkeys(re.findall(r'data-jk="([0-9a-f]+)"',listing)))
            record["outcome"]="success: public vacancy cards" if keys else "unconfirmed: no readable vacancy cards"
            for key in keys[:5]:
                link="https://it.indeed.com/viewjob?jk="+key
                body=page(link)
                for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',body,re.S|re.I):
                    try: obj=json.loads(block)
                    except ValueError: continue
                    for job in (obj if isinstance(obj,list) else [obj]):
                        if not isinstance(job,dict) or job.get("@type")!="JobPosting":continue
                        if str(job.get("validThrough") or "9999")[:10]<date.today().isoformat():continue
                        desc=clean(job.get("description"));mode=MODE.search(desc)
                        if not mode or NEGATIVE.search(desc):continue
                        loc=job.get("jobLocation") or {}
                        if isinstance(loc,list):loc=loc[0] if loc else {}
                        address=loc.get("address") or {};country=address.get("addressCountry")
                        if isinstance(country,dict):country=country.get("name")
                        if str(country).lower() not in ("it","italia","italy"):continue
                        found.append(("Indeed Italia","employer",dict(title=clean(job.get("title")),company=clean((job.get("hiringOrganization") or {}).get("name")),place=address.get("addressLocality") or "Italia",url=link,mode="Smart working previsto",details=desc[max(0,mode.start()-90):mode.end()+140])))
        except (OSError,ValueError,TypeError,AttributeError) as exc: record["outcome"]="unavailable: "+str(exc)[:120]
        return found,record
    with ThreadPoolExecutor(max_workers=2) as pool:
        for found,record in pool.map(indeed,[log for log in logs if "alternateSearch" in log]):
            alternate_rows.extend(found)
            alternate_logs.append(record)
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
    return rows+alternate_rows,logs+alternate_logs
