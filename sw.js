const VERSION="659";
const CACHE=`alice-job-radar-native-v${VERSION}-tuscany659`;
const SHELL=["./scan-clock.js?v=659","./?ajr=659","./index.html?ajr=659","./config.js?v=659","./audit-fix.js?v=659","./manifest.webmanifest?v=659","./icon.svg?v=659"];

const FAST_CACHE=CACHE+"-fast1";
const scope=new URL(self.registration.scope);
const keyFor=req=>req.mode==="navigate"?new URL("index.html",scope).href:req;
self.addEventListener("install",e=>e.waitUntil((async()=>{
 const c=await caches.open(FAST_CACHE);
 await Promise.allSettled(SHELL.map(async path=>{const url=new URL(path,scope);const res=await fetch(url,{cache:"reload"});if(res.ok){await c.put(url,res.clone());if(url.pathname===scope.pathname||url.pathname===scope.pathname+"index.html")await c.put(new URL("index.html",scope),res.clone());}}));
 await self.skipWaiting();
})()));
self.addEventListener("activate",e=>e.waitUntil((async()=>{
 await Promise.all((await caches.keys()).filter(k=>k.startsWith("alice-job-radar")&&k!==FAST_CACHE).map(k=>caches.delete(k)));
 await self.clients.claim();
})()));
self.addEventListener("fetch",e=>{
 const req=e.request,u=new URL(req.url);
 if(req.method!=="GET"||u.origin!==scope.origin||!u.pathname.startsWith(scope.pathname))return;
 const data=/\\.json$/i.test(u.pathname);
 const key=data?u.origin+u.pathname:keyFor(req);
 const c=caches.open(FAST_CACHE);
 const live=c.then(async cache=>{const res=await fetch(req,{cache:data?"no-store":"no-cache"});if(res.ok)await cache.put(key,res.clone());return res;});
 const cached=c.then(cache=>cache.match(key));
 if(data){e.respondWith(live.catch(async()=>await cached||Response.error()));return;}
 e.waitUntil(live.then(()=>{},()=>{}));
 e.respondWith(cached.then(hit=>hit||live).catch(()=>Response.error()));
});
self.addEventListener("push",event=>{
 event.waitUntil((async()=>{
  let p={};try{p=event.data?.json()||{}}catch(_){}
  await self.registration.showNotification(p.title||"Alice Job Radar",{
   body:p.body||"Una scansione è terminata. Apri l'app.",tag:p.tag||"alice-scan",
   icon:new URL("./icon.svg",self.registration.scope).href,
   data:{url:self.registration.scope}
  });
  if(Number.isInteger(p.count)&&p.count>0&&self.navigator.setAppBadge){try{await self.navigator.setAppBadge(p.count)}catch(_){}}
 })());
});
self.addEventListener("notificationclick",event=>{
 event.notification.close();
 event.waitUntil((async()=>{
  if(self.navigator.clearAppBadge){try{await self.navigator.clearAppBadge()}catch(_){}}
  const windows=await self.clients.matchAll({type:"window",includeUncontrolled:true});
  for(const client of windows){if(client.url.startsWith(self.registration.scope)){await client.navigate(self.registration.scope);return client.focus();}}
  return self.clients.openWindow(self.registration.scope);
 })());
});
