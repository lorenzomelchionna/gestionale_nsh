/**
 * Dati dell'attività, in un posto solo.
 *
 * Stavano copiati a mano in quattro file, ed è così che il telefono è rimasto
 * sbagliato per mesi in tutti e quattro: `095` è il prefisso di Catania, il
 * salone è in provincia di Avellino (`0825`). Un dato che compare in più
 * schermate va tenuto in un posto solo, altrimenti si corregge dove capita di
 * guardare e resta storto altrove.
 */

/** Denominazione legale, come da visura — non l'insegna.
 *  Va lasciata testuale: è quella che deve comparire sui documenti e che
 *  Meta/Google confrontano con la camera di commercio. */
export const RAGIONE_SOCIALE = 'New Style Hair S.r.l. Semplificata'

/** Obbligatoria sul sito di un'attività (art. 35 DPR 633/72). */
export const PARTITA_IVA = '02795180641'

/**
 * Indirizzo.
 *
 * `legale` è quello registrato (senza numero civico); `visita` è quello che
 * serve a una cliente per trovare la porta. Sono diversi di proposito: il
 * primo deve combaciare con i documenti, il secondo con la realtà.
 */
export const INDIRIZZO = {
  legale: 'Corso Italia, snc — 83030 Melito Irpino (AV)',
  visita: 'Corso Italia, 32 · Melito Irpino (AV)',
} as const

/** Fisso del salone. `tel` è in E.164 per il link `tel:`; l'Italia tiene lo
 *  zero iniziale anche in forma internazionale. */
export const TELEFONO = {
  visibile: '0825 1728148',
  tel: '+3908251728148',
} as const
