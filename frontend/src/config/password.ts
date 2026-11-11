/** Deve corrispondere a `MIN_CLIENT_PASSWORD` in `schemas/client.py`. Il
 *  controllo vero sta sul server — questo esiste perché il 422 di Pydantic
 *  arriva in inglese e non dice quanti caratteri mancano. Usato dalla
 *  registrazione e dal reset: due copie del numero erano già diventate due
 *  numeri diversi (la registrazione scriveva «almeno 6»). */
export const MIN_PASSWORD = 10
