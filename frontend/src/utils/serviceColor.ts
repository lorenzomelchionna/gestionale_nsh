import type { CSSProperties } from 'react'

/**
 * I colori dei servizi nel calendario.
 *
 * La tavolozza è corta di proposito: dieci tinte abbastanza distanti da
 * distinguersi a colpo d'occhio, e abbastanza sature da leggersi sia sul
 * foglio chiaro sia su quello scuro — il testo del blocco resta del colore
 * normale, la tinta sta nel fondo e nel bordo.
 */
export const SERVICE_PALETTE: { value: string; label: string }[] = [
  { value: '#c8a96e', label: 'Oro' },
  { value: '#c0643f', label: 'Terracotta' },
  { value: '#e08a2e', label: 'Arancio' },
  { value: '#d17a9c', label: 'Rosa' },
  { value: '#8e6cc4', label: 'Viola' },
  { value: '#4f7cc4', label: 'Blu' },
  { value: '#3fa3b8', label: 'Azzurro' },
  { value: '#4f9a5f', label: 'Verde' },
  { value: '#9aa04a', label: 'Oliva' },
  { value: '#8a8f98', label: 'Grigio' },
]

const HEX = /^#[0-9a-f]{6}$/i

/**
 * Lo stile di un blocco del calendario per un appuntamento.
 *
 * Il colore è del primo servizio, quello con cui si comincia. Solo `#rrggbb`
 * arriva fin qui — il backend non accetta altro — ma il controllo si ripete:
 * finisce dentro uno `style`.
 *
 * Il fondo è la tinta al 38% (12% se annullato), il bordo sinistro la tinta
 * piena. Al 28% sul foglio scuro il blu si leggeva grigio. Lo stato resta
 * disegnato dalla classe del blocco (tratteggio per «da confermare», barrato
 * per «annullato»): il colore dice *che cosa*, il bordo *a che punto*.
 */
export function serviceBlockStyle(
  colors: (string | null | undefined)[] | undefined,
  faded = false,
): CSSProperties | undefined {
  const color = colors?.find(c => c && HEX.test(c))
  if (!color) return undefined
  return {
    backgroundColor: `${color}${faded ? '1f' : '61'}`,
    borderLeftColor: color,
    borderLeftWidth: 4,
  }
}
