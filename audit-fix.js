(()=>{
"use strict";
const TZ="Europe/Rome";
const SLOTS=["09:30","15:30"];
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
  const r=audit.runs[slot];
  if(!r||typeof r!=="object")return null;
  const day=dateKeyFromIso(r.startedAt||r.completedAt||r.scheduledFor);
  return day===todayKey()?r:null;
}
function actualTime(iso){
  if(!iso)return "";
  const d=new Date(iso);
  if(Number.isNaN(d.getTime()))return "";
  return new Intl.DateTimeFormat("it-IT",{timeZone:TZ,hour:"2-digit",minute:"2-digit"}).format(d);
}
function sameExecution(a,b){
  if(!a||!b)return false;
  if(a.runId&&b.runId&&a.runId===b.runId)return true;
  return !!(a.startedAt&&b.startedAt&&a.startedAt===b.startedAt&&
    a.completedAt&&b.completedAt&&a.completedAt===b.completedAt);
}
function syncLabels(){
  const morning=document.querySelector("#run08box strong");
  const afternoon=document.querySelector("#run15box strong");
  if(morning)morning.textContent="09:30";
  if(afternoon)afternoon.textContent="15:30";
  const footer=document.querySelector(".footer");
  if(footer)footer.textContent="Alice Job Radar · PWA v6.48 · aggiornamento automatico 09:30 / 15:30";
}
function runLabel(a,r){
  const jobs=a.newJobs===1?"1 nuova":a.newJobs+" nuove";
  if (r?.coordinationVersion >= 1 && r.coordination) {
    const d=r.coordination;
    return jobs+" · "+d.directSources+" fonti dirette · "+d.indexedOnly+" indicizzate";
  }
  const verified=finiteCount(r?.universalDetailGate?.verified)??finiteCount(r?.specificJobPagesVerified)??0;
  return jobs+" · "+(verified?verified+" annunci verificati":a.explored+" fonti con esito");
}
function paintToday(jobs){
  const el=document.getElementById("runToday");
  if(!el||!Array.isArray(jobs))return;
  const unique=new Set();
  for(const j of jobs){
    if(!j||!j.firstSeenAt||dateKeyFromIso(j.firstSeenAt)!==todayKey())continue;
    if(j.id!==null&&j.id!==undefined)unique.add(String(j.id));
  }
  const n=unique.size;
  el.textContent="";
}
function paint(audit,history=[],jobs=null){
  syncLabels();
  const now=nowMinutes();
  const morning=validRun(audit,"09:30");
  for(const slot of SLOTS){
    const isMorning=slot==="09:30";
    const el=document.getElementById(isMorning?"run08":"run15");
    const box=document.getElementById(isMorning?"run08box":"run15box");
    const state=document.getElementById(isMorning?"run08State":"run15State");
    const moment=document.getElementById(isMorning?"run08At":"run15At");
    if(!el||!box)continue;
    box.classList.remove("ok","partial","failed");
    const r=validRun(audit,slot);
    let status="In programma", time="",detail="",fullDetail="";
    if(now>=slotMinutes(slot)){
      if(!r){
        status="Non registrata";
        detail="Nessun risultato distinto pubblicato";
        box.classList.add("partial");
      }else if(!isMorning&&sameExecution(morning,r)){
        status="Dati duplicati";
        detail="Non risulta una seconda esecuzione autonoma";
        box.classList.add("failed");
      }else{
        const a=auditNumbers(r);
        fullDetail=a.explored+"/"+a.total+" fonti esplorate · "+a.queries+" controlli · "+a.newJobs+" nuove";
        time=actualTime((r.status==="running"||r.status==="in_progress")?r.startedAt:(r.completedAt||r.startedAt||r.scheduledFor));
        if(r.status==="queued"){
          status="In attesa di avvio";time="";detail="Scansione registrata";box.classList.add("partial");
        }else if(r.status==="failed"){
          status="Fallita";
          detail="Risultati non confermati";
          box.classList.add("failed");
        }else if(r.status==="running"||r.status==="in_progress"){
          status="In corso";
          detail=runLabel(a,r);
          box.classList.add("partial");
        }else if(r.status==="complete"){
          status="Completata";
          detail=runLabel(a,r);
          box.classList.add("ok");
        }else if(r.status==="partial"){
          status="Parziale";
          detail=runLabel(a,r);
          box.classList.add("partial");
        }else{
          status="Esito non verificato";
          detail="Stato della scansione non disponibile";
          box.classList.add("partial");
        }
      }
    }
    if(state)state.textContent=status;
    const delayed=!!(r?.startedAt&&r?.scheduledFor&&
      (Date.parse(r.startedAt)-Date.parse(r.scheduledFor)>10*60*1000));
    if(moment)moment.textContent=time?((status==="In corso"?"Avviata":"Eseguita")+" alle "+time+
      (delayed?" · in ritardo":"")):"";
    el.textContent=detail;
    const catalog=document.getElementById(isMorning?"catalog08":"catalog15");
    const catalogDetail=catalog&&!catalog.hidden?catalog.textContent:"";
    box.title="Scansione "+slot+" · "+status+(time?" · ora reale "+time:"")+
      (r&&status!=="Dati duplicati"?" · "+(fullDetail||detail):"")+
      (catalogDetail?" · "+catalogDetail:"");
  }
  paintToday(Array.isArray(jobs)?jobs.filter(j=>j&&j.active!==false):jobs);
  // Manual searches are represented by inline offers only.
  document.getElementById("runNationalBox")?.remove();
  document.getElementById("runRecoveryBox")?.remove();
}

window.paintAliceAudit = paint;
})();
