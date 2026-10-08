"""La versione del gestionale.

Non si cambia a mano: la scrive `scripts/release.py prepare`, insieme a
`frontend/package.json`, e la CI controlla che le due coincidano. Sta qui e
non in un file alla radice perché su Railway il backend si costruisce dalla
sua cartella, e la radice del repository non la vede.
"""
__version__ = "1.2.4"
