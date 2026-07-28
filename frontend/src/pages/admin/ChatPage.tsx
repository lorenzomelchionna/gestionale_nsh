import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO, formatDistanceToNowStrict, isToday } from 'date-fns'
import { it } from 'date-fns/locale'
import {
  MessageSquare, Send, ChevronLeft, AlertTriangle, Archive, Loader2, Clock, User,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  getConversations, getConversation, replyToConversation, setConversationArchived,
} from '@/services/api'
import type { ChatMessage, Conversation } from '@/types'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'
import clsx from 'clsx'

export default function ChatPage() {
  const qc = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: () => getConversations(false),
    // New messages arrive by webhook, so the list has to poll to notice them.
    refetchInterval: 20_000,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['conversations'] })
    qc.invalidateQueries({ queryKey: ['chat-unread'] })
  }

  return (
    <div className="space-y-5 lg:space-y-0 lg:h-full lg:flex lg:flex-col">
      {/* On phones the thread replaces the list, so the header only belongs to
          the list view. */}
      <div className={clsx(selectedId !== null && 'hidden lg:block')}>
        <PageHeader
          title="Messaggi WhatsApp"
          subtitle={conversations.length ? `${conversations.length} conversazioni` : undefined}
        />
      </div>

      <div className="lg:flex lg:flex-1 lg:min-h-0 lg:gap-4 lg:mt-5">
        {/* Conversation list */}
        <div
          className={clsx(
            'lg:w-80 lg:shrink-0 lg:overflow-y-auto',
            selectedId !== null && 'hidden lg:block'
          )}
        >
          {isLoading ? (
            <SkeletonList rows={4} />
          ) : conversations.length === 0 ? (
            <div className="card">
              <EmptyState
                icon={MessageSquare}
                title="Nessun messaggio"
                description="Le conversazioni WhatsApp dei clienti compaiono qui."
              />
            </div>
          ) : (
            <div className="space-y-2">
              {conversations.map(c => (
                <ConversationRow
                  key={c.id}
                  conversation={c}
                  active={c.id === selectedId}
                  onClick={() => setSelectedId(c.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Thread */}
        <div className={clsx('lg:flex-1 lg:min-w-0', selectedId === null && 'hidden lg:block')}>
          {selectedId === null ? (
            <div className="card h-full hidden lg:flex items-center justify-center">
              <EmptyState
                icon={MessageSquare}
                title="Seleziona una conversazione"
                description="Scegli un cliente dall'elenco per leggere e rispondere."
              />
            </div>
          ) : (
            <Thread
              conversationId={selectedId}
              onBack={() => setSelectedId(null)}
              onChanged={invalidate}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function ConversationRow({ conversation: c, active, onClick }: {
  conversation: Conversation
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'card-interactive w-full text-left p-3.5 flex items-start gap-3',
        active && 'border-primary/60 bg-primary/[0.04]'
      )}
    >
      <div className="w-10 h-10 rounded-full bg-primary/12 flex items-center justify-center shrink-0">
        <span className="text-primary text-[13px] font-semibold">
          {c.display_name.slice(0, 2).toUpperCase()}
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="font-medium text-foreground truncate">{c.display_name}</p>
          {c.last_message_at && (
            <span className="text-[11px] text-muted-foreground shrink-0 tabular-nums">
              {isToday(parseISO(c.last_message_at))
                ? format(parseISO(c.last_message_at), 'HH:mm')
                : format(parseISO(c.last_message_at), 'd MMM', { locale: it })}
            </span>
          )}
        </div>
        {c.last_message_preview && (
          <p className="text-[13px] text-muted-foreground truncate mt-0.5">
            {c.last_message_preview}
          </p>
        )}
      </div>
      {c.unread_count > 0 && (
        <span className="min-w-5 h-5 px-1.5 bg-warning text-white text-[11px] font-bold rounded-full flex items-center justify-center shrink-0">
          {c.unread_count > 9 ? '9+' : c.unread_count}
        </span>
      )}
    </button>
  )
}

function Thread({ conversationId, onBack, onChanged }: {
  conversationId: number
  onBack: () => void
  onChanged: () => void
}) {
  const qc = useQueryClient()
  const [draft, setDraft] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: conv, isLoading } = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => getConversation(conversationId),
    refetchInterval: 15_000,
  })

  // Opening the thread clears its unread badge server-side; refresh the list.
  useEffect(() => { if (conv) onChanged() }, [conv?.id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [conv?.messages.length])

  const replyMut = useMutation({
    mutationFn: (body: string) => replyToConversation(conversationId, body),
    onSuccess: () => {
      setDraft('')
      qc.invalidateQueries({ queryKey: ['conversation', conversationId] })
      onChanged()
    },
  })

  const archiveMut = useMutation({
    mutationFn: () => setConversationArchived(conversationId, true),
    onSuccess: () => { onBack(); onChanged() },
  })

  if (isLoading || !conv) return <SkeletonList rows={3} />

  const windowOpen = conv.can_reply_freely
  const expiresIn = conv.window_expires_at
    ? formatDistanceToNowStrict(parseISO(conv.window_expires_at), { locale: it })
    : null

  const send = (e: React.FormEvent) => {
    e.preventDefault()
    const body = draft.trim()
    if (body) replyMut.mutate(body)
  }

  return (
    <div className="card flex flex-col lg:h-full min-h-[60vh]">
      {/* Thread header */}
      <div className="flex items-center gap-2 p-3 border-b border-border shrink-0">
        <button onClick={onBack} className="btn-icon lg:hidden -ml-1" aria-label="Torna all'elenco">
          <ChevronLeft className="w-5 h-5" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-foreground truncate">{conv.display_name}</p>
          <p className="text-xs text-muted-foreground tabular-nums">{conv.phone}</p>
        </div>
        {conv.client_id && (
          <Link
            to={`/admin/clients/${conv.client_id}`}
            className="btn-icon"
            title="Apri scheda cliente"
          >
            <User className="w-[18px] h-[18px]" />
          </Link>
        )}
        <button
          onClick={() => archiveMut.mutate()}
          className="btn-icon"
          title="Archivia conversazione"
        >
          <Archive className="w-[18px] h-[18px]" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2.5 min-h-0">
        {conv.messages.map(m => <Bubble key={m.id} message={m} />)}
        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-border p-3 shrink-0">
        {windowOpen ? (
          <>
            <form onSubmit={send} className="flex items-end gap-2">
              <textarea
                className="input flex-1 resize-none"
                rows={1}
                placeholder="Scrivi una risposta..."
                value={draft}
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(e) }
                }}
              />
              <button
                type="submit"
                disabled={!draft.trim() || replyMut.isPending}
                className="btn-primary !px-3 shrink-0"
                aria-label="Invia"
              >
                {replyMut.isPending
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : <Send className="w-4 h-4" />}
              </button>
            </form>
            {expiresIn && (
              <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground mt-2">
                <Clock className="w-3 h-3" />
                Puoi rispondere liberamente per altre {expiresIn}
              </p>
            )}
          </>
        ) : (
          <div className="flex items-start gap-2.5 text-[13px] bg-warning/10 text-warning rounded-lg px-3 py-2.5">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <p>
              Finestra di risposta chiusa. WhatsApp permette messaggi liberi solo entro
              24 ore dall'ultimo messaggio del cliente: oltre, servono i template
              approvati da Meta.
            </p>
          </div>
        )}
        {replyMut.isError && (
          <p role="alert" className="text-[13px] text-danger mt-2">
            Invio non riuscito. Riprova.
          </p>
        )}
      </div>
    </div>
  )
}

function Bubble({ message: m }: { message: ChatMessage }) {
  const mine = m.direction === 'outbound'
  return (
    <div className={clsx('flex', mine ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'max-w-[85%] sm:max-w-[70%] rounded-2xl px-3.5 py-2',
          mine
            ? 'bg-primary text-primary-foreground rounded-br-sm'
            : 'bg-muted text-foreground rounded-bl-sm'
        )}
      >
        <p className="text-sm whitespace-pre-wrap break-words">{m.body}</p>
        <div
          className={clsx(
            'flex items-center gap-1.5 mt-1 text-[10px]',
            mine ? 'text-primary-foreground/70 justify-end' : 'text-muted-foreground'
          )}
        >
          <span className="tabular-nums">{format(parseISO(m.created_at), 'HH:mm')}</span>
          {m.status === 'failed' && (
            <span className="font-semibold text-danger bg-surface px-1 rounded">
              non inviato
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
