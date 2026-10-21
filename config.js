window.ALICE_RADAR_CONFIG={
  dataUrl:"./data/jobs.json?v=20261021-schedule0930",
  appVersion:"6.33.5",
  sync:{
    enabled:true,
    url:"https://nlhxjpartgvplythgzrz.supabase.co",
    publishableKey:"sb_publishable_uA9EbSMwJ5oFraqP-r5njg_EXtLSjEH",
    table:"job_state"
  }
};
(()=>{
  const s=document.createElement("script");
  s.src="./audit-fix.js?v=20261021-schedule0930";
  s.async=true;
  s.onload=()=>{
    const d=document.createElement("script");
    d.src="./audit-display.js?v=20261021-schedule0930";
    d.async=true;
    document.head.appendChild(d);
  };
  document.head.appendChild(s);
})();
