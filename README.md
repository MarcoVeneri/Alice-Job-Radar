# Alice Job Radar

PWA collegata alla ricerca automatica delle 08:00.

La ricerca quotidiana aggiorna `data/jobs.json` nel repository. La PWA legge quel file senza cache, quindi le nuove offerte compaiono automaticamente. Ogni scheda contiene il link originale dell'annuncio; il pulsante **Apri annuncio** apre direttamente la pagina del portale/azienda.

Gli stati personali (`Nuova`, `Interessante`, `Candidata`, `Colloquio`, `Scartata`) restano salvati sul dispositivo tramite localStorage e non vengono sovrascritti dall'aggiornamento dei dati.

Per pubblicare:
1. GitHub → Settings → Pages
2. Source: Deploy from a branch
3. Branch: `main`, folder `/ (root)`
4. Save

URL atteso: `https://marcoveneri.github.io/Alice-Job-Radar/`
