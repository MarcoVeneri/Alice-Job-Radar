window.ALICE_RADAR_CONFIG={
  dataUrl:"./data/jobs.json?v=20261007-auditfix",
  appVersion:"6.32",
  sync:{
    enabled:true,
    url:"https://nlhxjpartgvplythgzrz.supabase.co",
    publishableKey:"sb_publishable_uA9EbSMwJ5oFraqP-r5njg_EXtLSjEH",
    table:"job_state"
  }
};
(()=>{
  const s=document.createElement("script");
  s.src="./audit-fix.js?v=20261007-0850";
  s.async=true;
  document.head.appendChild(s);
})();
