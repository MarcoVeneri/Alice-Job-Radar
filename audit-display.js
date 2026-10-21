(()=>{
"use strict";
const TZ="Europe/Rome";
const SLOTS=["08:00","15:00"];
let lastAudit=null;
let painting=false;

function parts(d=new Date()){
  const p=new Intl.DateTimeFormat("en-CA",{timeZone:TZ,year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).formatToParts(d);
  return Object.fromEntries(p.map(x=>[x.type,x.value]));
}
function todayKey(){const p=parts();return `${p.year}-${p.month}-${p.day}`}
function nowMinutes(){const p=parts();return Number(p.hour)*60+Number(p.minute)}
function slotMinutes(slot){const [h,m]=slot.split(":").map(Number);return h*60+m}
function finiteCount(v){
  if(v===null||v===undefined||v==="")return null;
  const n=Number(v);
  return Number.isFinite(n)&&n>=0?Math.floor(n):null;
}
function names(v){
  return Array.isArray(v)?[...new Set(v.filter(x=>typeof x==="string"&&x.trim()).map(x=>x.trim()))]:[];
}
function dateKeyFromIso(iso){
  if(!iso)return "";
  const d=new Date(iso);
  if(Number.isNaN(d.getTime()))return String(iso).slice(0,10);
  const p=new Intl.DateTimeFormat("en-CA",{timeZone:TZ,year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(d);
  const o=Object.fromEntries(p.map(x=>[x.type,x.value]));
  return `${o.year}-${o.month}-${o.day}`;
}
function auditNumbers(r){
  const total=Math.max(1,finiteCount(r?.requiredSourcesTotal)??finiteCount(r?.sourceUniverseTotal)??60);
  const complete=names(r?.sourcesChecked);
  const partial=names(r?.coverageDiagnostics?.sourcesPartiallyCovered);
  const searched=names(r?.sourcesSearched);
  const verified=names(r?.sourcesVerified);
  const exploredNames=[...new Set([...complete,...partial,...searched,...verified])];
  const exploredExplicit=finiteCount(r?.sourcesExplored);
  const explored=Math.min(total,Math.max(exploredNames.length,exploredExplicit??0));
  const queries=finiteCount(r?.queriesRun)??0;
  const newJobs=finiteCount(r?.newJobs)??0;
  return {total,explored,queries,newJobs,fullyCovered:complete.length};
}
function validRun(audit,slot){
  if(!audit||audit.date!==todayKey()||!audit.runs)return null;
  const r=audit.runs[slot];
  if(!r)return null;
  const runDay=dateKeyFromIso(r.scheduledFor||r.completedAt);
  return runDay===todayKey()?r:null;
}
function labelFor(a){
  const jobLabel=a.newJobs===1?"1 nuova":`${a.newJobs} nuove`;
  return `${a.explored}/${a.total} esplorate · ${a.queries} controlli · ${jobLabel}`;
}
function paint(audit=lastAudit){
  if(painting)return;
  painting=true;
  try{
    const now=nowMinutes();
    for(const slot of SLOTS){
      const is08=slot==="08:00";
      const el=document.getElementById(is08?"run08":"run15");
      const box=document.getElementById(is08?"run08box":"run15box");
      if(!el||!box)continue;
      box.classList.remove("ok","partial","failed");
      if(now<slotMinutes(slot)){
        if(el.textContent!=="Da verificare")el.textContent="Da verificare";
        el.removeAttribute("title");
        continue;
      }
      const r=validRun(audit,slot);
      if(!r){
        if(el.textContent!=="Da verificare")el.textContent="Da verificare";
        el.removeAttribute("title");
        continue;
      }
      const a=auditNumbers(r);
      const detail=labelFor(a);
      el.title=`${a.fullyCovered} fonti coperte completamente; ${a.explored} esplorate; ${a.queries} controlli reali`;
      if(r.status==="failed"){
        box.classList.add("failed");
        el.textContent=`Non completata · ${detail}`;
      }else if(r.status==="running"||r.status==="in_progress"){
        box.classList.add("partial");
        el.textContent=`In corso · ${detail}`;
      }else{
        const ok=r.status==="complete"&&a.explored>=a.total;
        box.classList.add(ok?"ok":"partial");
        if(el.textContent!==detail)el.textContent=detail;
      }
    }
  }finally{
    painting=false;
  }
}
async function refresh(){
  try{
    const cfg=window.ALICE_RADAR_CONFIG||{};
    const url=cfg.dataUrl||"./data/jobs.json";
    const sep=url.includes("?")?"&":"?";
    const r=await fetch(url+sep+"auditdisplay="+Date.now(),{cache:"no-store"});
    if(!r.ok)return;
    const j=await r.json();
    lastAudit=j.audit||null;
    paint();
  }catch(_){ }
}
function start(){
  refresh();
  setTimeout(refresh,700);
  setTimeout(refresh,1800);
  const section=document.querySelector(".runAudit");
  if(section){
    const obs=new MutationObserver(()=>{
      if(!painting)queueMicrotask(()=>paint());
    });
    obs.observe(section,{childList:true,characterData:true,subtree:true});
  }
  document.getElementById("refreshBtn")?.addEventListener("click",()=>setTimeout(refresh,700));
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")refresh()});
  setInterval(refresh,60000);
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
