from pathlib import Path

p = Path("index.html")
s = p.read_text(encoding="utf-8")

s = s.replace(
    '<div id="run08box" class="runChip"><strong>08:00</strong><span class="runSummary" id="run08">In attesa</span></div>',
    '<div id="run08box" class="runChip"><strong>08:00</strong><span class="runSummary" id="run08">Da verificare</span></div>',
).replace(
    '<div id="run15box" class="runChip"><strong>15:00</strong><span class="runSummary" id="run15">In attesa</span></div>',
    '<div id="run15box" class="runChip"><strong>15:00</strong><span class="runSummary" id="run15">Da verificare</span></div>',
)

start = s.index("function renderAudit(audit){")
end = s.index("async function load(){", start)
new_render = '''function renderAudit(audit){
 const today=romeDateKey();
 const sameDay=audit&&audit.date===today;
 const runs=sameDay&&audit.runs?audit.runs:{};
 function one(slot,el,box){
   const r=runs[slot];
   box.classList.remove("ok","partial","failed");
   box.querySelector(".runDetails")?.remove();
   if(!r){
     el.textContent="Da verificare";
     return;
   }
   const a=auditSummary(r);
   const total=a.total||60;
   const checked=a.checked===null?0:a.checked;
   const running=r.status==="running"||r.status==="in_progress";
   const failed=r.status==="failed";
   if(failed){
     box.classList.add("failed");
     el.textContent="Non completata · "+checked+"/"+total+" fonti";
     return;
   }
   if(running){
     box.classList.add("partial");
     el.textContent="In corso · "+checked+"/"+total+" fonti";
     return;
   }
   box.classList.add(checked>=total?"ok":"partial");
   el.textContent=checked+"/"+total+" fonti verificate";
 }
 one("08:00",ui.run08,ui.run08box);
 one("15:00",ui.run15,ui.run15box);
}
'''
s = s[:start] + new_render + s[end:]

old_css = '.runChip{flex-wrap:wrap;align-content:start}.runChip .runSummary{flex:1;min-width:0;line-height:1.5}.runDetails{width:100%;font-size:11px;line-height:1.5;color:var(--muted);overflow-wrap:anywhere}.runDetails summary{cursor:pointer}.runDetails p{margin:6px 0}.runChip strong{font-size:13px;letter-spacing:-.01em}.runChip span{font-size:11px;font-weight:800;color:var(--muted);text-align:right}'
new_css = '.runChip .runSummary{flex:1;min-width:0;line-height:1.5}.runChip strong{font-size:13px;letter-spacing:-.01em}.runChip span{font-size:11px;font-weight:800;color:var(--muted);text-align:right}'
s = s.replace(old_css, new_css)
s = s.replace('Alice Job Radar · PWA v6.31 · aggiornamento automatico 08:00 / 15:00', 'Alice Job Radar · PWA v6.32 · aggiornamento automatico 08:00 / 15:00')
s = s.replace('const CFG=window.ALICE_RADAR_CONFIG||{dataUrl:"./data/jobs.json",appVersion:"6.27",sync:{enabled:false}};', 'const CFG=window.ALICE_RADAR_CONFIG||{dataUrl:"./data/jobs.json",appVersion:"6.32",sync:{enabled:false}};')
p.write_text(s, encoding="utf-8")

sw = Path("sw.js")
sw.write_text(sw.read_text(encoding="utf-8").replace("alice-job-radar-v6-31", "alice-job-radar-v6-32"), encoding="utf-8")

cfg = Path("config.js")
cfg.write_text(cfg.read_text(encoding="utf-8").replace('appVersion:"6.28"', 'appVersion:"6.32"'), encoding="utf-8")
