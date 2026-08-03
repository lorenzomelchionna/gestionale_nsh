import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, AlertTriangle, PackagePlus, Package, ImagePlus, Trash2 } from 'lucide-react'
import {
  getProducts, createProduct, addProductMovement,
  setProductImage, deleteProductImage,
} from '@/services/api'
import type { Product } from '@/types'
import { useAuthStore } from '@/store/authStore'
import Sheet from '@/components/ui/Sheet'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'
import clsx from 'clsx'

export default function ProductsPage() {
  const qc = useQueryClient()
  const isAdmin = useAuthStore(s => s.user?.role === 'admin')
  const [showCreate, setShowCreate] = useState(false)
  const [movementProduct, setMovementProduct] = useState<Product | null>(null)
  const [photoProduct, setPhotoProduct] = useState<Product | null>(null)

  const { data, isLoading } = useQuery({ queryKey: ['products'], queryFn: () => getProducts() })
  const inv = () => qc.invalidateQueries({ queryKey: ['products'] })

  const createMut = useMutation({
    // A photo chosen while creating cannot be uploaded until the product has an
    // id, so it goes up as a second call. The product is already saved by then:
    // if the image fails, the user gets an error about the image, not a lost form.
    mutationFn: async ({ photo, ...data }: Partial<Product> & { photo?: File | null }) => {
      const created = await createProduct(data)
      if (photo) await setProductImage(created.id, photo)
      return created
    },
    onSuccess: () => { inv(); setShowCreate(false) },
  })
  const moveMut = useMutation({
    mutationFn: addProductMovement,
    onSuccess: () => { inv(); setMovementProduct(null) },
  })

  const products = data?.items ?? []
  const lowStock = products.filter(p => p.quantity <= p.min_quantity)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Prodotti"
        subtitle={products.length ? `${products.length} a magazzino` : undefined}
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuovo prodotto
          </button>
        }
      />

      {lowStock.length > 0 && (
        <div className="flex items-start gap-2.5 border-l-2 border-danger bg-danger/[0.08] px-4 py-3">
          <AlertTriangle className="w-4 h-4 text-danger shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-danger tabular-nums">
              {lowStock.length} prodott{lowStock.length > 1 ? 'i' : 'o'} sotto scorta
            </p>
            <p className="text-[13px] text-muted-foreground mt-0.5">
              {lowStock.map(p => p.name).join(', ')}
            </p>
          </div>
        </div>
      )}

      {isLoading ? (
        <SkeletonList rows={4} />
      ) : products.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={Package}
            title="Magazzino vuoto"
            description="Aggiungi i prodotti che rivendi o usi in salone."
            action={
              <button onClick={() => setShowCreate(true)} className="btn-primary">
                <Plus className="w-4 h-4" /> Nuovo prodotto
              </button>
            }
          />
        </div>
      ) : (
        /* The stock read as a ledger: figures right-aligned so a shelf can be
           checked by running down one column. The category column drops on a
           phone rather than letting the table scroll sideways. */
        <div className="panel table-scroll">
          <table className="ledger [&_tbody_tr:last-child_td]:border-b-0">
            <thead>
              <tr>
                <th className="w-px" />
                <th>Prodotto</th>
                <th className="hidden sm:table-cell">Categoria</th>
                <th className="num">Giacenza</th>
                <th className="num">Prezzo</th>
                <th className="w-px" />
              </tr>
            </thead>
            <tbody>
              {products.map(p => {
                const low = p.quantity <= p.min_quantity
                return (
                  <tr key={p.id}>
                    <td className="w-px">
                      <Thumbnail
                        product={p}
                        onClick={isAdmin ? () => setPhotoProduct(p) : undefined}
                      />
                    </td>
                    <td>
                      <div className="flex items-baseline gap-2.5">
                        <span>{p.name}</span>
                        {low && (
                          <span className="status-badge status-rejected shrink-0">sotto scorta</span>
                        )}
                      </div>
                      {p.description && (
                        <p className="text-[13px] text-ink-3 line-clamp-1 mt-0.5">{p.description}</p>
                      )}
                      <span className="kicker sm:hidden mt-1">{p.category}</span>
                    </td>
                    <td className="hidden sm:table-cell text-muted-foreground">{p.category}</td>
                    <td className="num whitespace-nowrap">
                      <span className={clsx('amount', low && 'text-danger')}>{p.quantity}</span>
                      <span className={clsx('text-[13px]', low ? 'text-danger' : 'text-ink-3')}> pz</span>
                      <span className="block text-[11px] text-ink-3 tabular-nums">
                        min {p.min_quantity}
                      </span>
                    </td>
                    <td className="num whitespace-nowrap">
                      <span className="amount">€{p.sale_price.toFixed(2)}</span>
                      <span className="block text-[11px] text-ink-3 tabular-nums">
                        acquisto €{p.purchase_price.toFixed(2)}
                      </span>
                    </td>
                    <td className="w-px">
                      <button
                        onClick={() => setMovementProduct(p)}
                        className="btn-icon hover:text-primary"
                        title="Carico / scarico"
                        aria-label={`Movimento magazzino per ${p.name}`}
                      >
                        <PackagePlus className="w-[18px] h-[18px]" />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <ProductFormModal
          onClose={() => setShowCreate(false)}
          onSave={(d) => createMut.mutate(d)}
          loading={createMut.isPending}
        />
      )}

      {movementProduct && (
        <MovementModal
          product={movementProduct}
          onClose={() => setMovementProduct(null)}
          onSave={(d) => moveMut.mutate(d)}
          loading={moveMut.isPending}
        />
      )}

      {photoProduct && (
        <PhotoModal
          product={photoProduct}
          onClose={() => setPhotoProduct(null)}
          onDone={inv}
        />
      )}
    </div>
  )
}

/** The photo in the register: a ruled box, never a floating image. Products
    without one keep the same footprint so the column stays a column. */
function Thumbnail({ product, onClick }: { product: Product; onClick?: () => void }) {
  const inner = product.photo_url ? (
    <img
      src={product.photo_url}
      alt=""
      loading="lazy"
      className="w-full h-full object-cover"
    />
  ) : (
    <Package className="w-4 h-4 text-ink-3" />
  )

  const box = 'w-11 h-11 border border-border bg-band flex items-center justify-center overflow-hidden shrink-0'

  if (!onClick) return <div className={box}>{inner}</div>
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(box, 'hover:border-primary transition-colors')}
      title={product.photo_url ? 'Cambia foto' : 'Aggiungi foto'}
      aria-label={`${product.photo_url ? 'Cambia' : 'Aggiungi'} foto di ${product.name}`}
    >
      {inner}
    </button>
  )
}

/** Add, replace or remove the photo of a product that already exists. */
function PhotoModal({ product, onClose, onDone }: {
  product: Product
  onClose: () => void
  onDone: () => void
}) {
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const preview = useObjectUrl(file)

  const upload = useMutation({
    mutationFn: () => setProductImage(product.id, file as File),
    onSuccess: () => { onDone(); onClose() },
    onError: (e: any) => setError(readError(e)),
  })
  const remove = useMutation({
    mutationFn: () => deleteProductImage(product.id),
    onSuccess: () => { onDone(); onClose() },
    onError: (e: any) => setError(readError(e)),
  })

  const busy = upload.isPending || remove.isPending
  const shown = preview ?? product.photo_url

  return (
    <Sheet
      onClose={onClose}
      title={product.photo_url ? 'Cambia foto' : 'Aggiungi foto'}
      description={product.name}
      size="sm"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button
            type="button"
            onClick={() => upload.mutate()}
            disabled={!file || busy}
            className="btn-primary btn-sm"
          >
            {upload.isPending ? 'Caricamento...' : 'Salva foto'}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="border border-border bg-band aspect-[4/3] flex items-center justify-center overflow-hidden">
          {shown ? (
            <img src={shown} alt="" className="w-full h-full object-contain" />
          ) : (
            <span className="note">Nessuna foto</span>
          )}
        </div>

        <label className="btn-secondary btn-sm w-full cursor-pointer">
          <ImagePlus className="w-4 h-4" />
          {file ? file.name : 'Scegli un file'}
          <input
            type="file"
            className="sr-only"
            accept="image/jpeg,image/png,image/webp"
            onChange={e => { setError(null); setFile(e.target.files?.[0] ?? null) }}
          />
        </label>

        <p className="text-xs text-muted-foreground">
          JPEG, PNG o WebP. Puoi caricare la foto così come esce dal telefono:
          viene rimpicciolita dal server.
        </p>

        {error && <p className="text-[13px] text-danger">{error}</p>}

        {product.photo_url && (
          <button
            type="button"
            onClick={() => remove.mutate()}
            disabled={busy}
            className="btn-danger-outline btn-sm w-full"
          >
            <Trash2 className="w-3.5 h-3.5" />
            {remove.isPending ? 'Rimozione...' : 'Rimuovi foto'}
          </button>
        )}
      </div>
    </Sheet>
  )
}

/** A local preview of a picked file, revoked when it is replaced or the sheet
    closes — an object URL pins the whole file in memory until it is. */
function useObjectUrl(file: File | null): string | null {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!file) { setUrl(null); return }
    const next = URL.createObjectURL(file)
    setUrl(next)
    return () => URL.revokeObjectURL(next)
  }, [file])
  return url
}

function readError(e: any): string {
  return e?.response?.data?.detail ?? 'Caricamento non riuscito. Riprova.'
}

function ProductFormModal({ onClose, onSave, loading }: {
  onClose: () => void
  onSave: (d: Partial<Product> & { photo?: File | null }) => void
  loading: boolean
}) {
  const [form, setForm] = useState({
    name: '', description: '', purchase_price: 0, sale_price: 0,
    category: 'Shampoo', quantity: 0, min_quantity: 2,
  })
  const [photo, setPhoto] = useState<File | null>(null)
  const preview = useObjectUrl(photo)

  return (
    <Sheet
      onClose={onClose}
      title="Nuovo prodotto"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="product-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form
        id="product-form"
        onSubmit={(e) => { e.preventDefault(); onSave({ ...form, photo }) }}
        className="space-y-4"
      >
        {/* Optional and first: on a phone the picture is usually already in the
            camera roll, and picking it before typing prices is the natural order. */}
        <div className="flex items-center gap-3">
          <div className="w-16 h-16 border border-border bg-band flex items-center justify-center overflow-hidden shrink-0">
            {preview
              ? <img src={preview} alt="" className="w-full h-full object-cover" />
              : <Package className="w-5 h-5 text-ink-3" />}
          </div>
          <label className="btn-secondary btn-sm cursor-pointer">
            <ImagePlus className="w-4 h-4" />
            {photo ? 'Cambia foto' : 'Foto (facoltativa)'}
            <input
              type="file"
              className="sr-only"
              accept="image/jpeg,image/png,image/webp"
              onChange={e => setPhoto(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
        <div>
          <label className="label">Nome *</label>
          <input className="input" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <label className="label">Categoria</label>
          <input className="input" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Prezzo acquisto</label>
            <input
              className="input" type="number" inputMode="decimal" step="0.01" min="0"
              value={form.purchase_price}
              onChange={e => setForm({ ...form, purchase_price: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Prezzo vendita</label>
            <input
              className="input" type="number" inputMode="decimal" step="0.01" min="0"
              value={form.sale_price}
              onChange={e => setForm({ ...form, sale_price: Number(e.target.value) })}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Quantità iniziale</label>
            <input
              className="input" type="number" inputMode="numeric" min="0"
              value={form.quantity}
              onChange={e => setForm({ ...form, quantity: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Scorta minima</label>
            <input
              className="input" type="number" inputMode="numeric" min="0"
              value={form.min_quantity}
              onChange={e => setForm({ ...form, min_quantity: Number(e.target.value) })}
            />
          </div>
        </div>
      </form>
    </Sheet>
  )
}

const MOVEMENT_TYPES = [
  { value: 'carico', label: 'Carico' },
  { value: 'scarico', label: 'Scarico' },
  { value: 'vendita', label: 'Vendita' },
]

function MovementModal({ product, onClose, onSave, loading }: {
  product: Product
  onClose: () => void
  onSave: (d: { product_id: number; type: string; quantity: number; notes?: string }) => void
  loading: boolean
}) {
  const [form, setForm] = useState({ type: 'carico', quantity: 1, notes: '' })

  return (
    <Sheet
      onClose={onClose}
      title="Movimento magazzino"
      description={`${product.name} · ${product.quantity} pz disponibili`}
      size="sm"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="movement-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form
        id="movement-form"
        onSubmit={(e) => {
          e.preventDefault()
          onSave({
            product_id: product.id,
            type: form.type,
            quantity: Number(form.quantity),
            notes: form.notes || undefined,
          })
        }}
        className="space-y-4"
      >
        <div>
          <label className="label">Tipo</label>
          {/* Three big tap targets beat a native select on a phone. */}
          <div className="grid grid-cols-3 gap-2">
            {MOVEMENT_TYPES.map(t => (
              <button
                key={t.value}
                type="button"
                onClick={() => setForm({ ...form, type: t.value })}
                className={clsx(
                  'min-h-touch border font-heading text-[12px] uppercase tracking-[0.1em] transition-colors',
                  form.type === t.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-surface text-muted-foreground hover:bg-foreground/[0.05]'
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="label">Quantità</label>
          <input
            className="input" type="number" inputMode="numeric" min="1"
            value={form.quantity}
            onChange={e => setForm({ ...form, quantity: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="label">Note</label>
          <input
            className="input"
            value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })}
          />
        </div>
      </form>
    </Sheet>
  )
}
