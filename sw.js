const VERSION="640";
const CACHE=`alice-job-radar-native-v${VERSION}-national640`;
const SHELL=["./?ajr=640","./index.html?ajr=640","./config.js?v=640","./audit-fix.js?v=20261114-national640","./manifest.webmanifest?v=640","./icon.svg?v=640"];
function fresh(url){const u=new URL(url,self.registration.scope);u.searchParams.set("__ajr","national640");u.searchParams.set("__t",Date.now().toString());return fetch(u.toString(),{cache:"no-store",credentials:"same-origin"})}
async function mergedJobs(request){
 const r=await fetch(request,{cache:"no-store"});
 if(!r.ok)return r;
 const data=await r.clone().json();
 try{
  const rr=await fresh("./data/recovery_jobs.json");
  if(rr.ok){
   const recovery=await rr.json();
   if(Array.isArray(data.jobs)&&Array.isArray(recovery)){
    const byId=new Map(data.jobs.map(j=>[String(j&&j.id||""),j]));
    for(const j of recovery){if(j&&j.id)byId.set(String(j.id),j)}
    data.jobs=[...byId.values()];
   }
  }
 }catch(_){}
 return new Response(JSON.stringify(data),{status:200,headers:{"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store, no-cache, must-revalidate","Pragma":"no-cache","Expires":"0"}})
}
self.addEventListener("install",e=>{e.waitUntil((async()=>{const c=await caches.open(CACHE);for(const key of SHELL){try{const r=await fresh(key);if(r.ok)await c.put(key,r.clone())}catch(_){}}await self.skipWaiting()})())});
self.addEventListener("activate",e=>{e.waitUntil((async()=>{const keys=await caches.keys();await Promise.all(keys.filter(k=>k.startsWith("alice-job-radar")&&k!==CACHE).map(k=>caches.delete(k)));await self.clients.claim()})())});
self.addEventListener("fetch",e=>{
 if(e.request.method!=="GET")return;
 const u=new URL(e.request.url);
 if(u.pathname.endsWith("/data/jobs.json")){
  e.respondWith((async()=>{try{const merged=await mergedJobs(e.request);if(merged.ok){const c=await caches.open(CACHE);c.put("./data/jobs.json",merged.clone()).catch(()=>{})}return merged}catch(_){return(await caches.match("./data/jobs.json"))||Response.error()}})());return;
 }
 if(e.request.mode==="navigate"){
  e.respondWith((async()=>{try{const live=new URL(e.request.url);live.searchParams.set("ajr","640");live.searchParams.set("__t",Date.now().toString());const r=await fetch(live.toString(),{cache:"no-store",credentials:"same-origin"});if(r.ok){const c=await caches.open(CACHE);c.put("./index.html?ajr=640",r.clone()).catch(()=>{});return r}}catch(_){}return(await caches.match("./index.html?ajr=640"))||(await caches.match("./?ajr=640"))||Response.error()})());return;
 }
 if(u.origin===self.location.origin){e.respondWith((async()=>{try{return await fetch(e.request,{cache:"no-store"})}catch(_){return(await caches.match(e.request,{ignoreSearch:true}))||Response.error()}})())}
});
