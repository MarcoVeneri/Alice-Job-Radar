const VERSION="644";
const CACHE=`alice-job-radar-native-v${VERSION}-smartonly644`;
const SHELL=["./?ajr=644","./index.html?ajr=644","./config.js?v=644","./audit-fix.js?v=20261115-smartonly644","./manifest.webmanifest?v=644","./icon.svg?v=644"];
function fresh(url){const u=new URL(url,self.registration.scope);u.searchParams.set("__ajr","smartonly644");u.searchParams.set("__t",Date.now().toString());return fetch(u.toString(),{cache:"no-store",credentials:"same-origin"})}
async function mergedJobs(request){
 // The published jobs.json is authoritative. Recovery files are history only:
 // merging them here resurrected excluded, on-site vacancies.
 return fetch(request,{cache:"no-store"});
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
  e.respondWith((async()=>{try{const live=new URL(e.request.url);live.searchParams.set("ajr","642");live.searchParams.set("__t",Date.now().toString());const r=await fetch(live.toString(),{cache:"no-store",credentials:"same-origin"});if(r.ok){const c=await caches.open(CACHE);c.put("./index.html?ajr=644",r.clone()).catch(()=>{});return r}}catch(_){}return(await caches.match("./index.html?ajr=644"))||(await caches.match("./?ajr=644"))||Response.error()})());return;
 }
 if(u.origin===self.location.origin){e.respondWith((async()=>{try{return await fetch(e.request,{cache:"no-store"})}catch(_){return(await caches.match(e.request,{ignoreSearch:true}))||Response.error()}})())}
});
