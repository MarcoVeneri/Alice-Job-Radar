# Alice Job Radar

PWA collegata alla ricerca automatica delle 08:00 e delle 15:00.

La ricerca aggiorna `data/jobs.json`; la PWA continua a funzionare normalmente anche prima dell'attivazione del database condiviso.

## Sincronizzazione condivisa

La versione 6.21 è predisposta per sincronizzare tra tutti i dispositivi:
- stato dell'offerta
- Salvata
- Candidata
- Eliminata

La sincronizzazione resta disattivata finché il database non è configurato.

### Migrazione senza perdita dati

Il database può essere inizializzato soltanto da un link master. Quel link va aperto per la prima volta sul telefono di Alice. Prima di leggere il database, la PWA carica gli stati locali già presenti sul suo telefono e crea il riferimento di inizializzazione. Solo dopo gli altri dispositivi iniziano a leggere lo stato condiviso.

Quindi un altro iPhone, iPad o computer non può inizializzare accidentalmente il database vuoto e cancellare le selezioni locali di Alice.

Il `localStorage` resta anche come copia locale/fallback.

URL PWA: `https://marcoveneri.github.io/Alice-Job-Radar/`
