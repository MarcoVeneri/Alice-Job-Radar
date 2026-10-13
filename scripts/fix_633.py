from pathlib import Path
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

BUILD = "633"
VERSION = "6.33"
TODAY = "2026-10-13"
now_rome = datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="seconds")

# ---- config: new immutable data/audit asset versions
p = Path("config.js")
s = p.read_text(encoding="utf-8")
s = re.sub(r'dataUrl:"[^"]+"', 'dataUrl:"./data/jobs.json?v=20261013-633"', s, count=1)
s = re.sub(r'appVersion:"[^"]+"', f'appVersion:"{VERSION}"', s, count=1)
s = re.sub(r's\.src="\.\/audit-fix\.js\?v=[^"]+"', 's.src="./audit-fix.js?v=20261013-633"', s, count=1)
p.write_text(s, encoding="utf-8")

# ---- index: truthful counters + hard build migration + no stale worker script
p = Path("index.html")
s = p.read_text(encoding="utf-8")
s = re.sub(r'<link rel="manifest" href="\.\/manifest\.webmanifest(?:\?v=[^"]*)?">',
           f'<link rel="manifest" href="./manifest.webmanifest?v={BUILD}">', s, count=1)
s = s.replace('PWA v6.32', f'PWA v{VERSION}')
s = s.replace('appVersion:"6.32"', f'appVersion:"{VERSION}"')

old = '''   box.classList.add(checked>=total?"ok":"partial");
   el.textContent=checked+"/"+total+" fonti verificate";'''
new = '''   box.classList.add(a.fullyComplete?"ok":"partial");
   el.textContent=checked+"/"+total+" complete · "+a.explored.length+" esplorate";
   el.title=(a.queries||0)+" controlli reali";'''
if old in s:
    s = s.replace(old, new, 1)

marker = 'id="alice-build-633"'
if marker not in s:
    force = f'''<script {marker}>
(function(){{
  try{{
    const u=new URL(location.href);
    if(u.searchParams.get('ajr')!=='{BUILD}'){{u.searchParams.set('ajr','{BUILD}');location.replace(u.toString());return;}}
  }}catch(e){{}}
}})();
</script>
'''
    s = s.replace('</head>', force + '</head>', 1)

# Replace the legacy registration block if present, then guarantee exactly one fresh registration.
s = re.sub(r'<script>\s*if\(\'serviceWorker\' in navigator\)\{window\.addEventListener\(\'load\',[\s\S]*?</script>\s*</body>', '</body>', s, count=1)
reg = f'''<script id="alice-sw-633">
if('serviceWorker' in navigator){{
  window.addEventListener('load',async()=>{{
    try{{
      const r=await navigator.serviceWorker.register('./sw.js?v={BUILD}',{{updateViaCache:'none'}});
      await r.update();
    }}catch(e){{}}
  }});
}}
</script>
'''
if 'id="alice-sw-633"' not in s:
    s = s.replace('</body>', reg + '</body>', 1)
p.write_text(s, encoding="utf-8")

# ---- manifest: installed PWA always starts on current build URL
manifest = {
    "id": f"./?ajr={BUILD}",
    "name": "Alice Job Radar",
    "short_name": "Alice Jobs",
    "start_url": f"./?ajr={BUILD}",
    "scope": "./",
    "display": "standalone",
    "background_color": "#f3f5f8",
    "theme_color": "#6FAE86",
    "description": "Dashboard automatica delle opportunità di lavoro per Alice.",
    "icons": [{"src": "./icon.svg?v=633", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]
}
Path("manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# ---- service worker: delete all old Alice caches and force open clients to the new build
sw = '''const VERSION="633";
const CACHE=`alice-job-radar-native-v${VERSION}`;
const SHELL=[
  "./?ajr=633",
  "./index.html?ajr=633",
  "./config.js?v=633",
  "./audit-fix.js?v=20261013-633",
  "./manifest.webmanifest?v=633",
  "./icon.svg?v=633"
];
function fresh(url){
  const u=new URL(url,self.registration.scope);
  u.searchParams.set("__ajr",VERSION);
  u.searchParams.set("__t",Date.now().toString());
  return fetch(u.toString(),{cache:"no-store",credentials:"same-origin"});
}
self.addEventListener("install",e=>{
  e.waitUntil((async()=>{
    const c=await caches.open(CACHE);
    for(const key of SHELL){try{const r=await fresh(key);if(r.ok)await c.put(key,r.clone())}catch(_){}}
    await self.skipWaiting();
  })());
});
self.addEventListener("activate",e=>{
  e.waitUntil((async()=>{
    const keys=await caches.keys();
    await Promise.all(keys.filter(k=>k.startsWith("alice-job-radar")&&k!==CACHE).map(k=>caches.delete(k)));
    await self.clients.claim();
    const clients=await self.clients.matchAll({type:"window",includeUncontrolled:true});
    for(const client of clients){
      try{
        const u=new URL(client.url);
        if(u.origin===self.location.origin&&u.searchParams.get("ajr")!==VERSION){u.searchParams.set("ajr",VERSION);await client.navigate(u.toString())}
      }catch(_){}
    }
  })());
});
self.addEventListener("fetch",e=>{
  if(e.request.method!=="GET")return;
  const u=new URL(e.request.url);
  if(u.pathname.endsWith("/data/jobs.json")){
    e.respondWith((async()=>{
      try{
        const r=await fetch(e.request,{cache:"no-store"});
        if(r.ok){const c=await caches.open(CACHE);c.put("./data/jobs.json",r.clone()).catch(()=>{});}
        return r;
      }catch(_){return (await caches.match("./data/jobs.json"))||Response.error()}
    })());
    return;
  }
  if(e.request.mode==="navigate"){
    e.respondWith((async()=>{
      try{
        const live=new URL(e.request.url);
        live.searchParams.set("ajr",VERSION);
        live.searchParams.set("__t",Date.now().toString());
        const r=await fetch(live.toString(),{cache:"no-store",credentials:"same-origin"});
        if(r.ok){const c=await caches.open(CACHE);c.put("./index.html?ajr=633",r.clone()).catch(()=>{});return r}
      }catch(_){}
      return (await caches.match("./index.html?ajr=633"))||(await caches.match("./?ajr=633"))||Response.error();
    })());
    return;
  }
  if(u.origin===self.location.origin){
    e.respondWith((async()=>{
      try{const r=await fetch(e.request,{cache:"no-store"});if(r.ok){const c=await caches.open(CACHE);c.put(e.request,r.clone()).catch(()=>{})}return r}
      catch(_){return (await caches.match(e.request,{ignoreSearch:true}))||Response.error()}
    })());
  }
});
'''
Path("sw.js").write_text(sw, encoding="utf-8")

# ---- Correct this morning's result with independently verified missed ads.
p = Path("data/jobs.json")
data = json.loads(p.read_text(encoding="utf-8"))
jobs = data.setdefault("jobs", [])
existing_ids = {str(j.get("id", "")) for j in jobs}

missed = [
  {
    "id": "hiflex-back-office-commerciale-porrena-20261013",
    "date": TODAY,
    "company": "HI-flex Italia Srl",
    "title": "Back Office Commerciale",
    "location": "Porrena / Poppi (AR)",
    "workMode": "In presenza",
    "contract": "Tempo pieno · CCNL Commercio V livello",
    "salary": "Da 1.660,08 € lordi/mese",
    "category": "Sales Support",
    "score": 8.4,
    "source": "Indeed / HI-flex Italia",
    "url": "https://www.simplyhired.it/job/na2cHRabiXEZRsY-DBxFJ2WypbyconxCwkJPkVccqUgLvuEhYOhM4Q",
    "summary": "Supporto clienti e forza vendita, preparazione offerte, gestione ordini, documenti di vendita e reportistica commerciale.",
    "checks": ["Sede in presenza", "Verificare eventuale flessibilità organizzativa"],
    "remote": False,
    "active": True,
    "firstSeenAt": now_rome,
    "firstSeenRun": "08:00"
  },
  {
    "id": "umana-back-office-commerciale-montopoli-20261013",
    "date": TODAY,
    "company": "Umana S.p.A.",
    "title": "Back Office Commerciale",
    "location": "Montopoli in Val d'Arno (PI)",
    "workMode": "In presenza · part-time 20 ore",
    "contract": "Somministrazione 6 mesi · CCNL Alimentari Artigianato 5° livello",
    "salary": "21.000–22.000 €",
    "category": "Sales Support",
    "score": 7.4,
    "source": "Indeed / Umana",
    "url": "https://it.indeed.com/q-impiegato-back-office-commerciale-l-monsummano-terme%2C-toscana-offerte-lavoro.html?l=monsummano+terme%2C+toscana&q=impiegato+back+office+commerciale",
    "summary": "Gestione ciclo ordine, consegne e anagrafiche clienti, documentazione commerciale e supporto alla rete vendita.",
    "checks": ["Part-time 20 ore", "Inglese B2", "Francese B1", "RAL 21–22k"],
    "remote": False,
    "active": True,
    "firstSeenAt": now_rome,
    "firstSeenRun": "08:00"
  }
]
added = []
for j in reversed(missed):
    if j["id"] not in existing_ids:
        jobs.insert(0, j)
        added.append(j["id"])

run = (((data.get("audit") or {}).get("runs") or {}).get("08:00"))
if isinstance(run, dict) and (data.get("audit") or {}).get("date") == TODAY:
    run["newJobs"] = max(int(run.get("newJobs") or 0), 2)
    run["postVerificationAt"] = now_rome
    run["postVerificationAdded"] = 2
    note = "Post-verifica indipendente: individuati e aggiunti 2 annunci pertinenti sfuggiti alla scansione iniziale (HI-flex Porrena e Umana Montopoli in Val d'Arno)."
    oldnote = str(run.get("notes") or "")
    if note not in oldnote:
        run["notes"] = (oldnote + " " + note).strip()

p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Alice Job Radar {VERSION}: added {len(added)} missed jobs; cache/build hardened.")
