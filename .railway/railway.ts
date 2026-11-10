// La configurazione dei servizi Railway di produzione, da quando i
// `railway.toml` (Config as Code) sono deprecati: Railway smette di leggerli
// il 2026-12-01. Generato con `railway config pull` il 2026-10-08, poi con
// dentro a mano quello che stava nei toml (comando d'avvio del backend,
// healthcheck, riavvio su errore fino a 3 volte).
//
// **Railway non legge questo file durante il deploy.** Le impostazioni
// arrivano sui servizi solo con `railway config apply`, lanciato a mano;
// un merge su `main` che cambia questo file non cambia niente in
// produzione finché qualcuno non fa plan + apply.
//
// **Un servizio che manca da qui viene cancellato dall'apply** — compresi
// Postgres e Redis coi loro volumi. Per questo `railway config migrate` non
// andava usato così com'è: il file che proponeva aveva solo i servizi coi
// toml, più uno inesistente ricavato dal `railway.toml` della radice.
//
// Le variabili sono `preserve()`: i valori restano su Railway e non
// finiscono in questo repository, che è pubblico. Eccezione dal 2026-11-10:
// `DATABASE_URL` e `REDIS_URL` di backend e worker sono **riferimenti** a
// quelle di Postgres e Redis. Così, rigenerando la password di un database,
// Railway aggiorna e riavvia da sé i servizi che la usano; con un valore
// copiato resterebbero con quella vecchia e il gestionale andrebbe giù. Il
// riferimento di Postgres arriva come `postgresql://…`: il driver asincrono
// lo aggiunge `app/config.py` (dalla 1.4.5). I `POSTGRES_*` del backend
// sono stati tolti lo stesso giorno: il codice non li usava e tenevano una
// password non più valida.
//
// Il riavvio è `ON_FAILURE`, il default di Railway: scriverlo qui lo farebbe
// risultare sempre «da cambiare» nel plan, perché Railway il default non lo
// salva (null). Si dichiarano solo i 3 tentativi.
//
// **Tutto ad Amsterdam (`europe-west4-drams3a`) dal 2026-11-10**: prima
// `sfo`, e dall'Italia ogni richiesta pagava ~200 ms di viaggio in
// California. Spostato con `railway scale --service X eu-west=1 sfo=0`, non
// con `config apply`: il plan **non vede i cambi di regione** («No changes»
// col file diverso). Qui le regioni sono scritte perché il file dica com'è,
// non perché lo producano.
//
// Il Dockerfile non si dichiara: Railway usa da solo quello nella cartella
// del servizio (`backend/Dockerfile`, `frontend/Dockerfile`).
//
//   cd .railway && npm ci && cd ..   # SDK, una volta
//   railway config plan              # sola lettura
//   railway config apply             # scrive su produzione

import { defineRailway, github, postgres, preserve, project, redis, service, volume } from "railway/iac";

// Il mittente delle email, uguale per backend e worker. Scritto qui e non
// `preserve()` perché i due servizi si erano separati: l'11/08 il dominio è
// stato autenticato su Brevo e la variabile cambiata sul solo backend, così
// conferme, promemoria e auguri — mandati dal worker — sono usciti per due
// mesi dall'indirizzo Gmail del salone, che Brevo riscrive in
// `…@11490705.brevosend.com`. Non è un segreto.
const MITTENTE = "noreply@newstylehair.it";

export default defineRailway(() => {
  const gestionale_nsh = github("lorenzomelchionna/gestionale_nsh", { checkSuites: false, rootDirectory: "/backend" });

  const Redis = redis("Redis", { region: "europe-west4-drams3a" });
  Redis.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };
  Redis.networking = { privateNetworkEndpoint: "redis" };
  const Postgres = postgres("Postgres", { region: "europe-west4-drams3a" });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const redisVolume = volume("redis-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 500 });
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 500 });
  const backend = service("backend", {
    source: gestionale_nsh,
    start: "sh -c \"alembic upgrade head && python bootstrap.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}\"",
    healthcheck: "/health",
    healthcheckTimeout: 30,
    replicas: { "europe-west4-drams3a": 1 },
    deploy: { restartPolicyMaxRetries: 3 },
    networking: { privateNetworkEndpoint: "gestionalensh" },
    env: { ACCESS_TOKEN_EXPIRE_MINUTES: preserve(), ADMIN_EMAIL: preserve(), ALGORITHM: preserve(), APP_ENV: preserve(), BREVO_API_KEY: preserve(), DATABASE_URL: Postgres.env.DATABASE_URL, EMAILS_FROM_EMAIL: MITTENTE, EMAILS_FROM_NAME: preserve(), FRONTEND_URL: preserve(), REDIS_URL: Redis.env.REDIS_URL, REFRESH_TOKEN_EXPIRE_DAYS: preserve(), SECRET_KEY: preserve(), SEED_DEMO: preserve(), SMTP_HOST: preserve(), SMTP_PASSWORD: preserve(), SMTP_PORT: preserve(), SMTP_USER: preserve(), TWILIO_ACCOUNT_SID: preserve(), TWILIO_AUTH_TOKEN: preserve(), TWILIO_TEMPLATE_CONFERMA: preserve(), TWILIO_TEMPLATE_PROMEMORIA: preserve(), TWILIO_TEMPLATE_VERIFICA: preserve(), TWILIO_WHATSAPP_FROM: preserve() },
  });
  // Dopo il backend perché ne legge la `SECRET_KEY` per riferimento
  // (2026-11-10): il worker non firma niente, ma per avviarsi ne vuole una
  // valida, e una copia sua era una seconda chiave da ruotare — leggibile,
  // per di più, mentre quella del backend è sigillata.
  const worker = service("worker", {
    source: gestionale_nsh,
    start: "sh worker-start.sh",
    replicas: { "europe-west4-drams3a": 1 },
    deploy: { restartPolicyMaxRetries: 3 },
    networking: { privateNetworkEndpoint: "celery-worker" },
    env: { ACCESS_TOKEN_EXPIRE_MINUTES: preserve(), ALGORITHM: preserve(), APP_ENV: preserve(), BREVO_API_KEY: preserve(), DATABASE_URL: Postgres.env.DATABASE_URL, EMAILS_FROM_EMAIL: MITTENTE, EMAILS_FROM_NAME: preserve(), FRONTEND_URL: preserve(), REDIS_URL: Redis.env.REDIS_URL, REFRESH_TOKEN_EXPIRE_DAYS: preserve(), SECRET_KEY: backend.env.SECRET_KEY, SEED_DEMO: preserve(), SMTP_HOST: preserve(), SMTP_PASSWORD: preserve(), SMTP_PORT: preserve(), SMTP_USER: preserve(), TWILIO_ACCOUNT_SID: preserve(), TWILIO_AUTH_TOKEN: preserve(), TWILIO_TEMPLATE_CONFERMA: preserve(), TWILIO_TEMPLATE_PROMEMORIA: preserve(), TWILIO_TEMPLATE_VERIFICA: preserve(), TWILIO_WHATSAPP_FROM: preserve() },
  });
  const frontend = service("frontend", {
    source: github("lorenzomelchionna/gestionale_nsh", { checkSuites: false, rootDirectory: "/frontend" }),
    healthcheck: "/",
    healthcheckTimeout: 30,
    replicas: { "europe-west4-drams3a": 1 },
    deploy: { restartPolicyMaxRetries: 3 },
    domains: ["www.newstylehair.it"],
    networking: { privateNetworkEndpoint: "happy-benevolence" },
    env: { VITE_API_URL: preserve() },
  });

  return project("new-style-hair", {
    resources: [worker, Redis, backend, frontend, Postgres, redisVolume, postgresVolume],
  });
});
