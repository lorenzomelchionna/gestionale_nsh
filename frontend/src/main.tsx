import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as Sentry from '@sentry/react'
import App from './App'
import { avviaSentry } from './sentry'
import './index.css'

avviaSentry()

/** Al posto della pagina bianca, quando un componente si rompe. Con Sentry
 *  acceso l'errore parte da qui; senza, resta almeno un modo per ripartire. */
function PaginaRotta() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-background">
      <div className="max-w-sm text-center space-y-3">
        <p className="text-lg text-foreground">Qualcosa è andato storto.</p>
        <p className="text-sm text-muted-foreground">
          Ricarica la pagina. Se succede ancora, avvisa il salone.
        </p>
        <button className="btn-primary" onClick={() => window.location.reload()}>
          Ricarica
        </button>
      </div>
    </div>
  )
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Sentry.ErrorBoundary fallback={<PaginaRotta />}>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </Sentry.ErrorBoundary>
  </React.StrictMode>
)
