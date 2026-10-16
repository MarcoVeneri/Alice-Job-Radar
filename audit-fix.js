(()=>{
"use strict";
const TZ="Europe/Rome";
const SLOTS=["08:00","15:00"];
const nativeFetch=window.fetch.bind(window);

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

// Protect the UI from a single malformed record in the generated JSON.
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
  const explicit=finiteCount(r?.requiredSourcesChecked);
  const checked=explicit===null?names(r?.sourcesChecked).length:Math.min(total,explicit);
  const partial=names(r?.coverageDiagnostics?.sourcesPartiallyCovered);
  const complete=names(r?.sourcesChecked);
  const exploredNames=[...new Set([...complete,...partial,...names(r?.sourcesSearched),...names(r?.sourcesVerified)])];
  const exploredExplicit=finiteCount(r?.sourcesExplored);
  const explored=Math.min(total,Math.max(exploredNames.length,exploredExplicit??0));
  const queries=finiteCount(r?.queriesRun)??0;
  return {total,checked,explored,queries};
}
function validRun(audit,slot){
  if(!audit||audit.date!==todayKey()||!audit.runs)return null;
  const r=audit.runs[slot];
  if(!r)return null;
  const runDay=dateKeyFromIso(r.scheduledFor||r.completedAt);
  return runDay===todayKey()?r:null;
}
function paint(audit){
  const now=nowMinutes();
  for(const slot of SLOTS){
    const el=document.getElementById(slot==="08:00"?"run08":"run15");
    const box=document.getElementById(slot==="08:00"?"run08box":"run15box");
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
    const detail=`${a.checked}/${a.total} complete · ${a.explored} esplorate`;
    el.title=`${a.queries} controlli reali eseguiti`;
    if(r.status==="failed"){
      box.classList.add("failed");
      el.textContent=`Non completata · ${detail}`;
    }else if(r.status==="running"||r.status==="in_progress"){
      box.classList.add("partial");
      el.textContent=`In corso · ${detail}`;
    }else{
      const trulyComplete=r.status==="complete"&&a.checked>=a.total;
      box.classList.add(trulyComplete?"ok":"partial");
      el.textContent=detail;
    }
  }
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
  refreshAudit();
  setTimeout(refreshAudit,500);
  setTimeout(retryMainLoad,700);
  setTimeout(refreshAudit,1600);
  document.getElementById("refreshBtn")?.addEventListener("click",()=>setTimeout(refreshAudit,450));
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible"){refreshAudit();setTimeout(retryMainLoad,250)}});
  setInterval(refreshAudit,60000);
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
