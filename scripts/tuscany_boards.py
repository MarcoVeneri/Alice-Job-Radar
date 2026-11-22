"""Read public employer boards and verify matching Italian vacancies."""
import json
import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlsplit
from concurrent.futures import ThreadPoolExecutor
from linkedin_search import page, MODE, NEGATIVE
from jobsora_extract import clean, ROLE

BOARDS = {
    "AICOM": "https://aicomspa-1736851116.teamtailor.com/jobs",
    "Var Group": "https://www.careers.vargroup.com/jobs",
    "Motoabbigliamento": "https://motoabbigliamento.teamtailor.com/jobs",
    "Prada Group Valdarno": "https://jobs.pradagroup.com/search/?q=&locationsearch=Terranuova",
}

def check_board(item):
    company, url = item
    log = dict(source=company, method="employer_board", checkedAt=datetime.now(timezone.utc).isoformat(), evidenceUrls=[url])
    rows = []
    try:
        listing = page(url)
        links = set()
        for href in re.findall(r'href="([^"]+)"',listing):
            link=urljoin(url,href).split("?")[0]
            parsed=urlsplit(link)
            if parsed.netloc==urlsplit(url).netloc and re.search(r"/(?:jobs/\d+-|job/[^/]+/\d+)",parsed.path):
                links.add(link)
        if not links:
            log["outcome"]="unconfirmed: no readable job links"
            return rows,log
        log["outcome"]=f"success: {len(links)} vacancy links"
        for link in sorted(links):
            if not ROLE.search(urlsplit(link).path.replace("-"," ")):
                continue
            try:
                body=page(link)
            except OSError:
                continue
            for block in re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',body,re.I|re.S):
                try: obj=json.loads(block)
                except ValueError: continue
                for job in (obj if isinstance(obj,list) else [obj]):
                    if not isinstance(job,dict) or job.get("@type")!="JobPosting": continue
                    if str(job.get("validThrough") or "9999")[:10]<date.today().isoformat(): continue
                    address=job.get("jobLocation") or {}
                    if isinstance(address,list): address=address[0] if address else {}
                    address=address.get("address",{}) if isinstance(address,dict) else {}
                    country=address.get("addressCountry")
                    if isinstance(country,dict):country=country.get("name")
                    if str(country).lower() not in ("it","italy","italia"):continue
                    desc=clean(job.get("description")); mode=MODE.search(desc)
                    tele=job.get("jobLocationType")=="TELECOMMUTE"
                    if not (tele or mode) or NEGATIVE.search(desc):continue
                    rows.append((company,"employer",dict(title=clean(job.get("title")),company=company,
                        place=address.get("addressLocality") or "Italia",url=link,
                        details=desc[max(0,mode.start()-90):mode.end()+140] if mode else desc[:300],
                        mode="Da remoto" if tele else "Smart working previsto")))
    except (OSError,ValueError) as exc:
        log["outcome"]="unavailable: "+str(exc)[:120]
    return rows,log

def discover_boards():
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(check_board,BOARDS.items()))
    results.append(prato_board())
    return [row for rows,_ in results for row in rows],[log for _,log in results]

def prato_board():
    from urllib.request import Request, urlopen
    base="https://aliaserviziambientali.wd103.myworkdayjobs.com"
    site="Multiutility_External_Career_Site"
    endpoint=base+"/wday/cxs/aliaserviziambientali/"+site+"/jobs"
    log=dict(source="Plures / Estra",method="employer_board",checkedAt=datetime.now(timezone.utc).isoformat(),evidenceUrls=[endpoint])
    rows=[]
    try:
        req=Request(endpoint,data=json.dumps(dict(appliedFacets={},limit=20,offset=0,searchText="Prato")).encode(),headers={"Content-Type":"application/json","Accept":"application/json"})
        with urlopen(req,timeout=8) as response: data=json.load(response)
        postings=data["jobPostings"]
        log["outcome"]=f"success: {len(postings)} Prato vacancy links"
        for item in postings:
            if not ROLE.search(item["title"]):continue
            path=item["externalPath"]
            if not path.startswith("/job/"):continue
            job=json.loads(page(endpoint[:-5]+path))["jobPostingInfo"]
            desc=clean(job.get("jobDescription"));mode=MODE.search(desc)
            if not mode or NEGATIVE.search(desc) or "prato" not in str(job.get("location","")).lower():continue
            rows.append((log["source"],"employer",dict(company=log["source"],title=item["title"],url=base+"/it-IT/"+site+path,place=job["location"],details=desc[max(0,mode.start()-90):mode.end()+140],mode="Smart working previsto")))
    except (OSError,KeyError,ValueError) as exc:log["outcome"]="unavailable: "+str(exc)[:120]
    return rows,log
