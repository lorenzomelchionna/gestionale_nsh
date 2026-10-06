/**
 * Un numero come lo legge una persona: «+393351112233» → «+39 335 111 2233».
 *
 * Il backend li tiene in E.164, che è la forma giusta per confrontarli e per
 * WhatsApp ma non per controllarli a occhio: una cifra sbagliata in mezzo a
 * dieci attaccate non si vede. Solo i cellulari italiani vengono spezzati
 * (3-3-4, come si dettano); un fisso ha prefissi di lunghezza diversa e uno
 * straniero regole sue, quindi restano come sono dopo il prefisso.
 */
export function telefonoLeggibile(numero: string | null | undefined): string {
  if (!numero) return ''
  const italiano = /^\+39(\d+)$/.exec(numero)
  if (!italiano) return numero
  const cifre = italiano[1]
  if (cifre.startsWith('3') && cifre.length === 10) {
    return `+39 ${cifre.slice(0, 3)} ${cifre.slice(3, 6)} ${cifre.slice(6)}`
  }
  return `+39 ${cifre}`
}
