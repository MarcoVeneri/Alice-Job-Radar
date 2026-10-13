(()=>{
"use strict";
const TZ="Europe/Rome";
const SLOTS=["08:00","15:00"];
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
  const total=Math.max(1,finiteCount(r?.requiredSourcesTotal)??60);
  // IMPORTANT: an explicit zero is a real value. Never replace it with the number of log labels.
  const explicit=finiteCount(r?.requiredSourcesChecked);
  const checked=explicit===null?names(r?.sourcesChecked).length:Math.min(total,explicit);
  const partial=names(r?.coverageDiagnostics?.sourcesPartiallyCovered);
  const complete=names(r?.sourcesChecked);
  const explored=[...new Set([...complete,...partial])];
  const queries=finiteCount(r?.queriesRun)??0;
  return {total,checked,explored:explored.length,queries};
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
    const r=await fetch(url+sep+"auditfix="+Date.now(),{cache:"no-store"});
    if(!r.ok)return;
    const j=await r.json();
    paint(j.audit||null);
  }catch(_){ }
}
function start(){
  refreshAudit();
  setTimeout(refreshAudit,600);
  setTimeout(refreshAudit,1800);
  document.getElementById("refreshBtn")?.addEventListener("click",()=>setTimeout(refreshAudit,450));
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible")refreshAudit()});
  setInterval(refreshAudit,60000);
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();
