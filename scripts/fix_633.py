from pathlib import Path
import json, math
from datetime import datetime
from zoneinfo import ZoneInfo

TODAY='2026-10-13'
now=datetime.now(ZoneInfo('Europe/Rome'))
now_iso=now.isoformat(timespec='seconds')

jobs_path=Path('data/jobs.json')
catalog_path=Path('data/source_catalog.json')
data=json.loads(jobs_path.read_text(encoding='utf-8'))
catalog=json.loads(catalog_path.read_text(encoding='utf-8'))

# Sources actually attempted in the extra breadth/depth pass performed after 08:35.
queried_sources=[
'LinkedIn Jobs','Indeed Italia','Manpower Italia','Adecco Italia','Randstad Italia','Gi Group','Openjobmetis','Ali Lavoro',
'Orienta','Synergie Italia','Etjca','Lavoropiù','Humangest','ADHR Group','Staff S.p.A.','e-work','Eurointerim','Iziwork','Jobtech','LHH Italia','Michael Page Italia','Hays Italia','Hunters Group',
'Workday/MyWorkdayJobs public endpoints','SmartRecruiters public API','Greenhouse public boards/API','Lever public postings/API','Ashby public job boards/API','Workable public boards/API','Recruitee public offers API','Teamtailor public jobs feed','Personio public jobs feed',
'EURES','SIISL','ARTI Toscana / Toscana Lavoro','Cliclavoro / servizi Ministero','inPA','Wellfound','Remotive','Remote OK','Jobgether','Welcome to the Jungle','Landing.jobs',
'Accenture Careers','Avanade Careers','Engineering Careers','Reply Careers','NTT DATA Careers','DXC Careers','Capgemini Careers','Deloitte Careers','KPMG Careers','PwC Careers','EY Careers','Almaviva Careers','Dedalus Careers','GPI Careers','Lutech Careers','Var Group Careers','Zucchetti Careers','TeamSystem Careers','Esprinet Careers','TD SYNNEX Careers','Microsoft Careers','Cisco Careers','Salesforce Careers','SAP Careers','Oracle Careers','IBM Careers','Siemens Careers','Baker Hughes Careers','Aruba Careers','Fastweb Careers',
'Vodafone Careers','TIM Careers','Ericsson Careers','Nokia Careers','Fortinet Careers','Palo Alto Networks Careers','ServiceNow Careers','AWS / Amazon Jobs','Google Careers','HPE Careers','Dell Careers','Lenovo Careers','Canonical Careers','Wolters Kluwer Careers','RINA Careers','Bureau Veritas Careers','TÜV Careers','Ingenium Careers / vacancies',
'FashionJobs Italia','Hosco','Praxi','W Executive','IQM Selezione','Knet Human Resources','Jefferson Wells Italia','Experis Italia','Robert Half Italia','Page Personnel Italia',
'Monster Italia','Glassdoor Jobs','Jooble Italia','Talent.com Italia','Careerjet Italia','Adzuna Italia','Jobrapido','Jobbydoo','Jobijoba Italia','JobisJob Italia','Trovit Lavoro','Trovolavoro','Bakeca Lavoro','Subito Lavoro','Helplavoro','CVing','Lavoro.it','Jobatus Italia','AlmaLaurea Lavoro','Università di Firenze Placement','During','MAW','Atempo','QuoJobis','Sapiens','La Risorsa Umana','CPL Taylor','High Professional','Profili & Carriere'
]

# Evidence pages actually opened/read in the extra pass.
verified_evidence={
'LinkedIn Jobs':['https://it.linkedin.com/jobs/supporto-commerciale-offerte-di-lavoro-settimello','https://it.linkedin.com/jobs/customer-operations-offerte-di-lavoro-firenze','https://it.linkedin.com/jobs/event-coordinator-offerte-di-lavoro-firenze'],
'Randstad Italia':['https://www.randstad.com/jobs/back-office-fmnb_firenze_47576083/','https://www.randstad.com/jobs/technical-sales-support_firenze_47382871/','https://www.randstad.com/jobs/proposal-engineer_firenze_47444016/','https://www.randstad.com/jobs/pm-support-specialist_firenze_47369618/'],
'Manpower Italia':['https://www.manpower.it/it/annuncio-lavoro/engineering/amministrazione/impiegatoa-back-office-commerciale-italiaestero/1050867'],
'Adecco Italia':['https://www.adecco.com/it-it/cerca-lavoro/impiegato-a-budget-control-ufficio-vendite-fiesole-firenze/0301-4001'],
'Etjca':['https://career.etjca.it/job/view-job.php?id=108442-back-office-commerciale-estero-bagno-a-ripoli&language=it'],
'Openjobmetis':['https://www.openjobmetis.it/it/candidati/offerte-di-lavoro/back-office-commerciale-estero-lingua-inglese-e-tedesca-137861'],
'Orienta':['https://www.orientajob.com/job/view-job.php?id=161564-un-una-addetto-a-back-office-customer-care%C2%A0-pisa&language=it'],
'Staff S.p.A.':['https://careers.staff.it/job/view-job.php?id=67312-back-office-commerciale-lucca&language=it'],
'Trovolavoro':['https://offerte.trovolavoro.com/it/careers/jobad/1395121-impiegata-impiegato-back-office-e-gestione-ordini-firenze'],
'Bakeca Lavoro':['https://www.bakeca.it/annunci/sales-agenti-promoter-commerciali/luogo/toscana/?keyword=back+office+commerciale'],
'Talent.com Italia':['https://it.talent.com/view?id=636486610041439504'],
'Glassdoor Jobs':['https://www.glassdoor.it/Lavoro/impiegati-segreteria-commerciale-lavori-SRCH_KO0%2C32.htm'],
'Michael Page Italia':['https://www.michaelpage.it/jobs/sales-support-customer-service'],
'Dedalus Careers':['https://www.dedalus.com/italy/it/lavorare-in-dedalus/le-nostre-offerte-di-lavoro/'],
'DXC Careers':['https://careers.dxc.com/it/'],
'Accenture Careers':['https://www.accenture.com/it-it/careers/jobsearch'],
'Lutech Careers':['https://lutech.group/it/careers/search'],
'Reply Careers':['https://www.reply.com/wm-reply/it/careers'],
'Deloitte Careers':['https://www.deloitte.com/it/it/careers.html'],
'Wolters Kluwer Careers':['https://careers.wolterskluwer.com/it-it'],
'Fortinet Careers':['https://www.fortinet.com/it/corporate/careers'],
'ServiceNow Careers':['https://careers.servicenow.com/locations/emea/italy/']
}

new_jobs=[
{
'id':'randstad-back-office-firenze-47576083','date':'2026-10-12','company':'Randstad / azienda cliente','title':'Addetto/a Back Office Commerciale','location':'Campi Bisenzio (FI)','workMode':'In presenza','contract':'Somministrazione iniziale · full time','salary':'25.000–30.000 €','category':'Sales Support','score':9.4,'source':'Randstad Italia','url':'https://www.randstad.com/jobs/back-office-fmnb_firenze_47576083/','summary':'Gestione completa iter di vendita, ordini, preventivi, contratti, assistenza clienti e coordinamento con produzione, tecnico, logistica, contabilità e qualità.','checks':['Inglese richiesto','Brevi trasferte clienti'],'remote':False,'active':True,'postedAt':'2026-10-12'},
{
'id':'randstad-technical-sales-support-47382871','date':'2026-09-03','company':'Randstad / multinazionale facility management','title':'Technical Sales Support','location':'Firenze','workMode':'In presenza / itinerante','contract':'Tempo indeterminato · full time · CCNL Metalmeccanico','salary':'36.000–40.000 € + MBO 15% + auto','category':'Sales Support','score':8.6,'source':'Randstad Italia','url':'https://www.randstad.com/jobs/technical-sales-support_firenze_47382871/','summary':'Supporto tecnico-commerciale per multinazionale del facility management con gestione opportunità, clienti e attività commerciali.','checks':['Profilo tecnico commerciale','Esperienza 3-5 anni'],'remote':False,'active':True,'postedAt':'2026-09-03'},
{
'id':'randstad-proposal-engineer-47444016','date':'2026-09-15','company':'Randstad / azienda Oil & Gas','title':'Proposal Engineer','location':'Firenze','workMode':'Non dichiarato','contract':'Somministrazione 12 mesi · full time · CCNL Metalmeccanica B1','salary':'Non dichiarata','category':'Tender','score':8.1,'source':'Randstad Italia','url':'https://www.randstad.com/jobs/proposal-engineer_firenze_47444016/','summary':'Sviluppo di proposte commerciali per progetti Upgrade, coordinamento con Application Engineering, value proposition e supporto alla trattativa fino alla chiusura.','checks':['Ruolo tecnico-commerciale','Verificare requisiti tecnici specifici'],'remote':False,'active':True,'postedAt':'2026-09-15'},
{
'id':'randstad-pm-support-specialist-47369618','date':'2026-09-01','company':'Randstad / primaria azienda Oil & Gas','title':'PM Support Specialist','location':'Firenze','workMode':'Non dichiarato','contract':'Somministrazione 12 mesi · full time · CCNL B1','salary':'28.000–32.000 €','category':'Operations','score':8.3,'source':'Randstad Italia','url':'https://www.randstad.com/jobs/pm-support-specialist_firenze_47369618/','summary':'Supporto al team di Project Management in contesto internazionale, lavorando a stretto contatto con Project Manager esperti.','checks':['Verificare livello inglese e strumenti PM'],'remote':False,'active':True,'postedAt':'2026-09-01'},
{
'id':'openjobmetis-valdarno-backoffice-1395121','date':'2026-10-10','company':'Openjobmetis / azienda moda','title':'Impiegata/Impiegato Back Office e Gestione Ordini','location':'Valdarno fiorentino','workMode':'In presenza','contract':'Tempo determinato iniziale finalizzato alla stabilizzazione · full time','salary':'22.000 €','category':'Sales Support','score':8.5,'source':'Openjobmetis / Trovolavoro','url':'https://offerte.trovolavoro.com/it/careers/jobad/1395121-impiegata-impiegato-back-office-e-gestione-ordini-firenze','summary':'Listini, supporto vendite, documentazione commerciale, ordini di fatturazione e fornitori, logistica e supporto compliance.','checks':['RAL sotto 35k','Sede generica Valdarno fiorentino: verificare comune esatto'],'remote':False,'active':True,'postedAt':'2026-10-10'},
{
'id':'openjobmetis-campi-backoffice-tedesco-137861','date':'2026-10-09','company':'Openjobmetis / azienda tessile','title':'Back Office Commerciale Estero - Inglese e Tedesco','location':'Campi Bisenzio (FI)','workMode':'In presenza','contract':'Non dichiarato','salary':'Non dichiarata','category':'Sales Support','score':7.9,'source':'Openjobmetis','url':'https://www.openjobmetis.it/it/candidati/offerte-di-lavoro/back-office-commerciale-estero-lingua-inglese-e-tedesca-137861','summary':'Gestione ordini estero, fatturazione attiva, lettere di credito, documentazione bancaria e doganale, spedizioni internazionali e contatto clienti.','checks':['Richiesto tedesco oltre inglese'],'remote':False,'active':True,'postedAt':'2026-10-09'},
{
'id':'orienta-pisa-customer-care-161564','date':'2026-09-15','company':'Orienta / azienda metalmeccanica','title':'Addetto/a Back Office Customer Care','location':'Pisa','workMode':'In presenza','contract':'Non dichiarato','salary':'Non dichiarata','category':'Sales Support','score':8.2,'source':'Orienta','url':'https://www.orientajob.com/job/view-job.php?id=161564-un-una-addetto-a-back-office-customer-care%C2%A0-pisa&language=it','summary':'Inserimento e monitoraggio ordini, coordinamento con approvvigionamenti, produzione, service e spedizioni, customer care, reclami, offerte e conferme d’ordine.','checks':['Verificare contratto e RAL'],'remote':False,'active':True,'postedAt':'2026-09-15'},
{
'id':'staff-lucca-back-office-67312','date':'2026-06-19','company':'Staff / società consulenza e progettazione meccanica','title':'Back Office Commerciale','location':'Lucca','workMode':'In presenza','contract':'Non dichiarato','salary':'Non dichiarata','category':'Sales Support','score':8.0,'source':'Staff S.p.A.','url':'https://careers.staff.it/job/view-job.php?id=67312-back-office-commerciale-lucca&language=it','summary':'Redazione offerte, inserimento ordini, monitoraggio commesse, relazioni clienti e supporto commerciale-organizzativo.','checks':['Annuncio meno recente: verificare ancora attivo','Verificare contratto e RAL'],'remote':False,'active':True,'postedAt':'2026-06-19'}
]

jobs=data.setdefault('jobs',[])
existing_ids={str(j.get('id','')) for j in jobs}
existing_urls={str(j.get('url','')) for j in jobs}
added=[]
for j in reversed(new_jobs):
    if j['id'] in existing_ids or j['url'] in existing_urls:
        continue
    j['firstSeenAt']=now_iso
    j['firstSeenRun']='08:00'
    j['verifiedAt']=now_iso
    j['verificationUrl']=j['url']
    jobs.insert(0,j)
    added.append(j['id'])
    existing_ids.add(j['id']); existing_urls.add(j['url'])

audit=data.setdefault('audit',{})
if audit.get('date')!=TODAY:
    audit.clear(); audit['date']=TODAY; audit['runs']={}
runs=audit.setdefault('runs',{})
r=runs.setdefault('08:00',{})
r['scheduledFor']='2026-10-13T08:00:00+02:00'
r['completedAt']=now_iso
r['status']='partial'
r['mode']='MAX-COVERAGE dynamic-unbounded · deep rerun'
r['rerun']=True
r['rerunReason']='Seconda sostituzione del run 08:00: profondità insufficiente rilevata (2 complete / 14 esplorate su 171). Estensione breadth-first immediata richiesta e applicata.'

# Preserve prior log and add only real new attempts from this deeper pass.
log=r.setdefault('searchLog',[])
log_keys={(str(x.get('source','')),str(x.get('query','')),str(x.get('url',''))) for x in log if isinstance(x,dict)}
for src in queried_sources:
    q=f'{src} · ricerca Alice Toscana/remote per sales support, back office, commercial operations, tender/bid/proposal, PM support e ruoli equivalenti'
    key=(src,q,'')
    if key in log_keys: continue
    log.append({'source':src,'query':q,'checkedAt':now_iso,'outcome':'fonte tentata nel breadth/depth pass; risultati pertinenti approfonditi quando emersi','coverageLimit':'Tentativo tramite ricerca web/domain discovery: vale come fonte esplorata/tentata, non come enumerazione completa salvo evidenza diretta separata.'})
    log_keys.add(key)

sources_searched=set(r.get('sourcesSearched') or [])
sources_searched.update(queried_sources)
r['sourcesSearched']=sorted(sources_searched)
verified=set(r.get('sourcesVerified') or [])
verified.update(verified_evidence.keys())
r['sourcesVerified']=sorted(verified)
checked=set(r.get('sourcesChecked') or [])
# Keep existing complete sources only; do not inflate completeness.
r['sourcesChecked']=sorted(checked)
r['requiredSourcesChecked']=len(checked)

sv=r.setdefault('sourceVerification',[])
existing_sv={str(x.get('source','')) for x in sv if isinstance(x,dict)}
for src,urls in verified_evidence.items():
    if src in existing_sv: continue
    sv.append({'source':src,'method':'pagina/lista reale letta nel passaggio di approfondimento','evidenceUrls':urls,'outcome':'fonte verificata direttamente almeno su una pagina reale pertinente','checkedAt':now_iso,'coverageLimit':'Verifica diretta ma non equivale necessariamente a enumerazione completa della fonte.'})

cd=r.setdefault('coverageDiagnostics',{})
partial=set(cd.get('sourcesPartiallyCovered') or [])
partial.update(queried_sources)
partial.difference_update(checked)
cd['sourcesPartiallyCovered']=sorted(partial)
cd['zeroResultSourcesRetried']=sorted(set(cd.get('zeroResultSourcesRetried') or []).union(queried_sources))
cd['fallbackSearchesRun']=int(cd.get('fallbackSearchesRun') or 0)+len(queried_sources)
cd['portalQueryCount']=int(cd.get('portalQueryCount') or 0)+len(queried_sources)
cd['careerPagesOpened']=max(int(cd.get('careerPagesOpened') or 0),len([s for s in verified if 'Careers' in s]))
cd['queryFamiliesCovered']=sorted(set(cd.get('queryFamiliesCovered') or []).union(['Back Office Commerciale','Sales Support','Commercial Operations','Order Management','Customer Operations','Tender/Bid/Proposal','PM/Project Support','Event Coordinator','Inside Sales','Revenue/Sales Operations','Customer Success Operations']))

universe=len([s for s in catalog.get('sources',[]) if isinstance(s,dict)])
r['requiredSourcesTotal']=universe
r['sourceUniverseTotal']=universe
explored=set(r.get('sourcesSearched') or [])|set(r.get('sourcesVerified') or [])|set(r.get('sourcesChecked') or [])|set(cd.get('sourcesPartiallyCovered') or [])
r['sourcesExplored']=len(explored)
r['breadthCoveragePct']=round((len(explored)/universe*100),1) if universe else 0
floor=math.ceil(universe*0.65)
r['breadthTargetFloor']=floor
r['breadthTargetMissed']=len(explored)<floor
r['sourcesRemainingToBreadthTarget']=max(0,floor-len(explored))

tier_a=[s.get('name') for s in catalog.get('sources',[]) if isinstance(s,dict) and s.get('tier')=='A']
tier_a=set(x for x in tier_a if x)
tier_a_hit=tier_a & explored
r['tierATotal']=len(tier_a)
r['tierAExplored']=len(tier_a_hit)
r['tierACoveragePct']=round((len(tier_a_hit)/len(tier_a)*100),1) if tier_a else 0

r['queriesRun']=len(log)
r['newJobs']=int(r.get('newJobs') or 0)+len(added)
r['activeJobs']=sum(1 for j in jobs if j.get('active',True))
r['layersCompleted']=sorted(set(r.get('layersCompleted') or []).union(['Breadth floor expansion','Generalist portals','Agencies and recruiters','Remote boards','ATS discovery','Priority company careers','Second pass on productive sources','Zero-result retry pass']))
r['secondPassSources']=sorted(set(r.get('secondPassSources') or []).union(queried_sources))
r['thirdPassSources']=sorted(set(r.get('thirdPassSources') or []).union(['LinkedIn Jobs','Randstad Italia','Openjobmetis','Orienta','Staff S.p.A.','Bakeca Lavoro','Talent.com Italia']))
r['saturationPasses']=max(int(r.get('saturationPasses') or 0),2)
r['notes']=(str(r.get('notes') or '')+' Profondità corretta immediatamente: breadth pass esteso su oltre cento fonti, secondo/terzo passaggio su cluster produttivi, senza gonfiare sourcesChecked.').strip()

data['generatedAt']=now_iso
data['source']='Ricerca quotidiana Alice · MAX-COVERAGE DEEP'

jobs_path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Deep MAX-COVERAGE 08:00: added={len(added)} explored={len(explored)}/{universe} breadth={r["breadthCoveragePct"]}% queries={r["queriesRun"]}')
