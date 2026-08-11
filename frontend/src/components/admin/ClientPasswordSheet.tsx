import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { resetClientPassword } from '@/services/api'
import type { Client } from '@/types'
import Sheet from '@/components/ui/Sheet'
import clsx from 'clsx'

/** Stesso minimo del portale (`MIN_CLIENT_PASSWORD` lato server): più alto qui
 *  sembrerebbe una difesa e durerebbe fino al primo cambio password. */
const MIN_PASSWORD = 10

function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  // Gli errori di validazione Pydantic arrivano come lista di oggetti.
  if (Array.isArray(detail)) return 'Dati non validi: controlla i campi.'
  return 'Operazione non riuscita. Riprova.'
}

/**
 * Reimposta la password del portale di una cliente.
 *
 * Serve nell'unico caso in cui il `password dimenticata` del portale non
 * serve a niente: quando è la casella email a non essere più raggiungibile.
 * Lì il link di reset parte e non arriva a nessuno, e prima di questa
 * schermata non c'era altra strada.
 */
export default function ClientPasswordSheet({
  client,
  onClose,
}: {
  client: Client
  onClose: () => void
}) {
  const [password, setPassword] = useState('')
  const [done, setDone] = useState(false)

  const mut = useMutation({
    mutationFn: () => resetClientPassword(client.id, password),
    onSuccess: () => setDone(true),
  })

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD

  return (
    <Sheet
      onClose={onClose}
      title="Reimposta password portale"
      description={`${client.first_name} ${client.last_name}`}
      size="sm"
      footer={
        done ? (
          <button onClick={onClose} className="btn-primary btn-sm">Chiudi</button>
        ) : (
          <>
            <button type="button" onClick={onClose} className="btn-secondary btn-sm">
              Annulla
            </button>
            <button
              type="submit" form="client-password-form"
              disabled={mut.isPending || tooShort || !password}
              className="btn-primary btn-sm"
            >
              {mut.isPending ? 'Salvataggio...' : 'Reimposta'}
            </button>
          </>
        )
      }
    >
      {done ? (
        <div className="flex items-start gap-2.5 text-[13px] bg-primary/10 text-primary-dark dark:text-primary px-3 py-2.5">
          <Check className="w-4 h-4 shrink-0 mt-0.5" />
          <p>
            Password aggiornata. Comunicagliela a voce: potrà cambiarla dal
            portale dopo l'accesso.
          </p>
        </div>
      ) : (
        <form
          id="client-password-form"
          onSubmit={e => { e.preventDefault(); mut.mutate() }}
          className="space-y-4"
        >
          {/* Il campo è `text` e non `password`: chi la digita la deve leggere
              per dettarla al telefono, ed è comunque temporanea. */}
          <div>
            <label className="label">Nuova password *</label>
            <input
              className="input" type="text" required minLength={MIN_PASSWORD}
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoFocus
            />
            <p className={clsx('text-xs mt-1.5', tooShort ? 'text-danger' : 'text-muted-foreground')}>
              Almeno {MIN_PASSWORD} caratteri.
            </p>
          </div>
          {mut.isError && (
            <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5">
              {errorText(mut.error)}
            </p>
          )}
        </form>
      )}
    </Sheet>
  )
}
