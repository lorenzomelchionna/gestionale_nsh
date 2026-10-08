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
// Le variabili sono tutte `preserve()`: i valori restano su Railway e non
// finiscono in questo repository, che è pubblico.
//
// Il Dockerfile non si dichiara: Railway usa da solo quello nella cartella
// del servizio (`backend/Dockerfile`, `frontend/Dockerfile`).
//
//   cd .railway && npm ci && cd ..   # SDK, una volta
//   railway config plan              # sola lettura
//   railway config apply             # scrive su produzione

import { defineRailway, github, postgres, preserve, project, redis, service, volume } from "railway/iac";

export default defineRailway(() => {
  const gestionale_nsh = github("lorenzomelchionna/gestionale_nsh", { checkSuites: false, rootDirectory: "/backend" });

  const Redis = redis("Redis", { region: "sfo" });
  Redis.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };
  Redis.networking = { privateNetworkEndpoint: "redis" };
  const Postgres = postgres("Postgres", { region: "sfo" });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  const redisVolume = volume("redis-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 500 });
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 500 });
  const worker = service("worker", {
    source: gestionale_nsh,
    start: "sh worker-start.sh",
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3 },
    networking: { privateNetworkEndpoint: "celery-worker" },
    env: { ACCESS_TOKEN_EXPIRE_MINUTES: preserve(), ALGORITHM: preserve(), APP_ENV: preserve(), BREVO_API_KEY: preserve(), DATABASE_URL: preserve(), EMAILS_FROM_EMAIL: preserve(), EMAILS_FROM_NAME: preserve(), FRONTEND_URL: preserve(), REDIS_URL: preserve(), REFRESH_TOKEN_EXPIRE_DAYS: preserve(), SECRET_KEY: preserve(), SEED_DEMO: preserve(), SMTP_HOST: preserve(), SMTP_PASSWORD: preserve(), SMTP_PORT: preserve(), SMTP_USER: preserve(), TWILIO_ACCOUNT_SID: preserve(), TWILIO_AUTH_TOKEN: preserve(), TWILIO_TEMPLATE_CONFERMA: preserve(), TWILIO_TEMPLATE_PROMEMORIA: preserve(), TWILIO_TEMPLATE_VERIFICA: preserve(), TWILIO_WHATSAPP_FROM: preserve() },
  });
  const backend = service("backend", {
    source: gestionale_nsh,
    start: "sh -c \"alembic upgrade head && python bootstrap.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}\"",
    healthcheck: "/health",
    healthcheckTimeout: 30,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3 },
    networking: { privateNetworkEndpoint: "gestionalensh" },
    env: { ACCESS_TOKEN_EXPIRE_MINUTES: preserve(), ADMIN_EMAIL: preserve(), ALGORITHM: preserve(), APP_ENV: preserve(), BREVO_API_KEY: preserve(), DATABASE_URL: preserve(), EMAILS_FROM_EMAIL: preserve(), EMAILS_FROM_NAME: preserve(), FRONTEND_URL: preserve(), POSTGRES_DB: preserve(), POSTGRES_PASSWORD: preserve(), POSTGRES_USER: preserve(), REDIS_URL: preserve(), REFRESH_TOKEN_EXPIRE_DAYS: preserve(), SECRET_KEY: preserve(), SEED_DEMO: preserve(), SMTP_HOST: preserve(), SMTP_PASSWORD: preserve(), SMTP_PORT: preserve(), SMTP_USER: preserve(), TWILIO_ACCOUNT_SID: preserve(), TWILIO_AUTH_TOKEN: preserve(), TWILIO_TEMPLATE_CONFERMA: preserve(), TWILIO_TEMPLATE_PROMEMORIA: preserve(), TWILIO_TEMPLATE_VERIFICA: preserve(), TWILIO_WHATSAPP_FROM: preserve() },
  });
  const frontend = service("frontend", {
    source: github("lorenzomelchionna/gestionale_nsh", { checkSuites: false, rootDirectory: "/frontend" }),
    healthcheck: "/",
    healthcheckTimeout: 30,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 3 },
    domains: ["www.newstylehair.it"],
    networking: { privateNetworkEndpoint: "happy-benevolence" },
    env: { VITE_API_URL: preserve() },
  });

  return project("new-style-hair", {
    resources: [worker, Redis, backend, frontend, Postgres, redisVolume, postgresVolume],
  });
});
