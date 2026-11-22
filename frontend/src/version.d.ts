/** Sostituita da Vite al build con la versione di package.json (vite.config.ts). */
declare const __APP_VERSION__: string

interface ImportMetaEnv {
  /** DSN del progetto Sentry del frontend; assente = Sentry spento. */
  readonly VITE_SENTRY_DSN?: string
}
