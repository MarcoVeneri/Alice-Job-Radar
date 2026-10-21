(()=>{
"use strict";
const TZ="Europe/Rome";
const SLOTS=["09:30","15:30"];
const nativeFetch=window.fetch.bind(window);
let cachedNewCount=null;

function str(v){return v===null||v===undefined?"":String(v)}
function finiteNumber(v,fallback=0){const n=Number(v);return Number.isFinite(n)?n:fallback}
function sanitizeJob(job,index){
  if(!job||typeof job!=="object")job={};
  const checks=Array.isArray(job.checks)?job.checks.map(str).filter(Boolean):(job.checks?[str(job.checks)]:[]);
  const id=str(job.id)||`job-safe-${index}`;
  return {
    ...job,
    id,
    company:str(job.company)||"Azienda",
    title:str(job.title)||"Offerta",
    location:str(job.location),
    workMode:str(job.workMode),
    contract:str(job.contract),
    salary:str(job.salary),
    category:str(job.category)||"Operations",
    summary:str(job.summary),
    url:str(job.url)||"#",
    date:str(job.date),
    firstSeenAt:str(job.firstSeenAt),
    firstSeenRun:str(job.firstSeenRun),
    score:finiteNumber(job.score,0),
    checks,
    remote:!!job.remote,
    active:job.active!==false
  };
}
function sanitizePayload(payload){
  if(!payload||typeof payload!=="object")return {jobs:[],audit:null};
  const jobs=Array.isArray(payload.jobs)?payload.jobs.filter(x=>x&&typeof x==="object").map(sanitizeJob):[];
  return {...payload,jobs,audit:(payload.audit&&typeof payload.audit==="object")?payload.audit:null};
}
function isJobsUrl(input){
  try{
    const raw=typeof input==="string"?input:(input&&input.url)||"";
    const u=new URL(raw,location.href);
    return /\/data\/jobs\.json$/i.test(u.pathname);
  }catch(_){return false}
}

window.fetch=async function(input,init){
  const response=await nativeFetch(input,init);
  if(!isJobsUrl(input)||!response.ok)return response;
  try{
    const payload=JSON.parse(await response.clone().text());
    const safe=sanitizePayload(payload);
    const headers=new Headers(response.headers);
    headers.set("content-type","application/json; charset=utf-8");
    headers.set("cache-control","no-store");
    return new Response(JSON.stringify(safe),{status:response.status,statusText:response.statusText,headers});
  }catch(_){
    return response;
  }
};

function parts(d=new Date()){
  const p=new Intl.DateTimeFormat("en-CA",{timeZone:TZ,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(d);
  return Object.fromEntries(p.map(x=>[x.type,x.value]));
}
function todayKey(){const p=parts();return `${p.year}-${p.month}-${p.day}`}
function nowMinutes(){const p=parts();return Number(p.hour)*60+Number(p.minute)}
function slotMinutes(slot){const [h,m]=slot.split(":").map(Number);return h*60+m}
function dateKeyFromIso(iso){
  if(!iso)return "";
  const d=new Date(iso); if(Number.isNaN(d.getTime()))return String(iso).slice(0,10);
  const p=new Intl.DateTimeFormat("en-CA",{timeZone:TZ,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(d);
  const o=Object.fromEntries(p.map(x=>[x.type,x.value]));
  return `${o.year}-${o.month}-${o.day}`;
}
function names(v){return Array.isArray(v)?[...new Set(v.filter(x=>typeof x==="string"&&x.trim()).map(x=>x.trim()))]:[]}
function finiteCount(v){
  if(v===null||v===undefined||v==="")return null;
  const n=Number(v); return Number.isFinite(n)&&n>=0?Math.floor(n):null;
}
function auditNumbers(r){
  const total=Math.max(1,finiteCount(r?.requiredSourcesTotal)??finiteCount(r?.sourceUniverseTotal)??60);
  const partial=names(r?.coverageDiagnostics?.sourcesPartiallyCovered);
  const complete=names(r?.sourcesChecked);
  const exploredNames=[...new Set([...complete,...partial,...names(r?.sourcesSearched),...names(r?.sourcesVerified)])];
  const exploredExplicit=finiteCount(r?.sourcesExplored);
  const explored=Math.min(total,Math.max(exploredNames.length,exploredExplicit??0));
  const queries=finiteCount(r?.queriesRun)??0;
  const newJobs=finiteCount(r?.newJobs)??0;
  return {total,explored,queries,newJobs,complete:complete.length};
}
function validRun(audit,slot){
  if(!audit||audit.date!==todayKey()||!audit.runs)return null;
  let r=audit.runs[slot];
  // Oggi il cambio orario è avvenuto dopo il run mattutino: mostriamo il run 08:00
  // nella card mattutina finché il primo 09:30 non verrà eseguito domani.
  if(!r&&slot==="09:30")r=audit.runs["08:00"]||null;
  if(!r)return null;
  const runDay=dateKeyFromIso(r.scheduledFor||r.completedAt);
  return runDay===todayKey()?r:null;
}
function syncLabels(){
  const morning=document.querySelector("#run08box strong");
  const afternoon=document.querySelector("#run15box strong");
  if(morning)morning.textContent="09:30";
  if(afternoon)afternoon.textContent="15:30";
  const footer=document.querySelector(".footer");
  if(footer)footer.textContent="Alice Job Radar · PWA v6.33 · aggiornamento automatico 09:30 / 15:30";
}
function runLabel(a){
  const jobs=a.newJobs===1?"1 nuova":`${a.newJobs} nuove`;
  return `${a.explored}/${a.total} esplorate · ${a.queries} controlli · ${jobs}`;
}
function paint(audit){
  syncLabels();
  const now=nowMinutes();
  for(const slot of SLOTS){
    const isMorning=slot==="09:30";
    const el=document.getElementById(isMorning?"run08":"run15");
    const box=document.getElementById(isMorning?"run08box":"run15box");
    if(!el||!box)continue;
    box.classList.remove("ok","partial","failed");
    if(now<slotMinutes(slot)){
      el.textContent="Da verificare";
      el.removeAttribute("title");
      continue;
    }
    const r=validRun(audit,slot);
    if(!r){
      el.textContent="Da verificare";
      el.removeAttribute("title");
      continue;
    }
    const a=auditNumbers(r);
    const detail=runLabel(a);
    el.title=`${a.complete} fonti complete · ${a.explored} fonti esplorate · ${a.queries} controlli reali`;
    if(r.status==="failed"){
      box.classList.add("failed");
      el.textContent=`Non completata · ${detail}`;
    }else if(r.status==="running"||r.status==="in_progress"){
      box.classList.add("partial");
      el.textContent=`In corso · ${detail}`;
    }else{
      box.classList.add(a.explored>=a.total?"ok":"partial");
      el.textContent=detail;
    }
  }
}

function syncEndpoint(){
  const cfg=window.ALICE_RADAR_CONFIG||{};
  const sync=cfg.sync||{};
  if(!sync.enabled||!sync.url||!sync.publishableKey)return null;
  const table=String(sync.table||"job_state").replace(/[^a-zA-Z0-9_]/g,"");
  const base=String(sync.url).replace(/\/$/,"");
  return {
    url:`${base}/rest/v1/${table}?select=job_id,applied,dismissed`,
    headers:{"apikey":sync.publishableKey,"x-client-info":"alice-job-radar/new-count-hotfix"}
  };
}
async function loadFreshState(){
  const cfg=window.ALICE_RADAR_CONFIG||{};
  const dataUrl=cfg.dataUrl||"./data/jobs.json";
  const sep=dataUrl.includes("?")?"&":"?";
  const dataReq=nativeFetch(dataUrl+sep+"newcount="+Date.now(),{cache:"no-store"});
  const endpoint=syncEndpoint();
  const stateReq=endpoint?nativeFetch(endpoint.url,{headers:endpoint.headers,cache:"no-store"}):Promise.resolve(null);
  const [dataResp,stateResp]=await Promise.all([dataReq,stateReq]);
  if(!dataResp.ok)return;
  const payload=sanitizePayload(JSON.parse(await dataResp.text()));
  let rows=[];
  if(stateResp&&stateResp.ok){
    try{rows=await stateResp.json()}catch(_){rows=[]}
  }
  const states=new Map((Array.isArray(rows)?rows:[]).map(r=>[String(r.job_id),r]));
  const today=todayKey();
  cachedNewCount=payload.jobs.filter(j=>{
    if(String(j.firstSeenAt||"").slice(0,10)!==today)return false;
    const r=states.get(String(j.id));
    if(r&&r.dismissed)return false;
    if(r&&r.applied)return false;
    return true;
  }).length;
  paintNewSemantics();
}
function paintNewSemantics(){
  const st=document.getElementById("stNew");
  if(st&&cachedNewCount!==null)st.textContent=String(cachedNewCount);

  const activeNew=!!document.querySelector('.stat[data-stat="Nuove"].active');
  const jobs=document.getElementById("jobs");
  if(!jobs)return;

  jobs.querySelectorAll("article.card").forEach(card=>{
    const applied=card.classList.contains("alreadyApplied");
    if(applied){
      card.classList.remove("isNew");
      card.querySelector(".badge.new")?.remove();
    }
    card.style.display=(activeNew&&applied)?"none":"";
  });

  const oldEmpty=jobs.querySelector('[data-new-hotfix-empty="1"]');
  const visibleCards=[...jobs.querySelectorAll("article.card")].filter(x=>x.style.display!=="none");
  if(activeNew&&visibleCards.length===0&&!jobs.querySelector(".empty")){
    if(!oldEmpty)jobs.insertAdjacentHTML("beforeend",'<div class="empty" data-new-hotfix-empty="1">Nessuna nuova offerta da valutare.</div>');
  }else if(oldEmpty){
    oldEmpty.remove();
  }
}
function optimisticAppliedClick(e){
  const btn=e.target.closest?.("[data-applied]");
  if(!btn)return;
  const card=btn.closest("article.card");
  const st=document.getElementById("stNew");
  if(!card||!st||!card.classList.contains("isNew"))return;
  const n=Number(st.textContent);
  if(!Number.isFinite(n))return;
  const wasApplied=card.classList.contains("alreadyApplied");
  const next=Math.max(0,n+(wasApplied?1:-1));
  st.textContent=String(next);
  cachedNewCount=next;
}
async function refreshAudit(){
  try{
    const cfg=window.ALICE_RADAR_CONFIG||{};
    const url=cfg.dataUrl||"./data/jobs.json";
    const sep=url.includes("?")?"&":"?";
    const r=await nativeFetch(url+sep+"auditfix="+Date.now(),{cache:"no-store"});
    if(!r.ok)return;
    const j=JSON.parse(await r.text());
    paint(j.audit||null);
  }catch(_){ }
}
function retryMainLoad(){
  const btn=document.getElementById("refreshBtn");
  if(btn&&!btn.disabled){try{btn.click()}catch(_){}}
}
function start(){
  syncLabels();
  refreshAudit();
  loadFreshState();
  setTimeout(refreshAudit,500);
  setTimeout(retryMainLoad,700);
  setTimeout(loadFreshState,1100);
  setTimeout(refreshAudit,1600);

  const jobs=document.getElementById("jobs");
  if(jobs){
    const obs=new MutationObserver(()=>queueMicrotask(paintNewSemantics));
    obs.observe(jobs,{childList:true,subtree:true});
  }

  document.addEventListener("click",e=>{
    optimisticAppliedClick(e);
    if(e.target.closest?.("[data-applied]")){
      setTimeout(loadFreshState,350);
      setTimeout(loadFreshState,1200);
    }else if(e.target.closest?.(".stat,.tab,#navHome,#navSaved,#navSearch")){
      setTimeout(paintNewSemantics,40);
    }
  },true);

  document.getElementById("refreshBtn")?.addEventListener("click",()=>{
    setTimeout(refreshAudit,450);
    setTimeout(loadFreshState,650);
  });
  document.addEventListener("visibilitychange",()=>{
    if(document.visibilityState==="visible"){
      refreshAudit();
      loadFreshState();
      setTimeout(retryMainLoad,250);
    }
  });
  setInterval(()=>{
    refreshAudit();
    loadFreshState();
  },60000);
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
