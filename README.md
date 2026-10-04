# Alice Job Radar

PWA collegata alla ricerca automatica delle 08:00 e delle 15:00.

La ricerca aggiorna `data/jobs.json`. Gli stati personali delle offerte (Salvata, Candidata, Eliminata e stato candidatura) possono essere sincronizzati tra dispositivi tramite Supabase.

## Sicurezza della sincronizzazione

La publishable key Supabase presente nel frontend è pubblica per definizione e non costituisce un segreto.

L'accesso a `job_state` è invece protetto da un token privato ad alta entropia. La PWA:

- riutilizza automaticamente il token privato già usato dalla PWA Lista Spesa quando disponibile sul dispositivo;
- può importare lo stesso token tramite un link con `#key=...`, che viene subito salvato in `localStorage` e rimosso dall'URL;
- usa RPC protette (`alice_get_state` e `alice_upsert_state`) per leggere e modificare gli stati;
- mantiene il `localStorage` come fallback se il token non è disponibile.

Le policy RLS di `job_state` **non devono mai** essere sostituite con policy permissive tipo `USING (true)` o `WITH CHECK (true)`.

## Dati pubblici e privati

`data/jobs.json` contiene le offerte raccolte dal radar e viene servito dalla PWA pubblica.

Gli stati personali delle candidature sono invece nel database protetto e non sono leggibili o modificabili da un visitatore anonimo senza il token privato.

URL PWA: `https://marcoveneri.github.io/Alice-Job-Radar/`
