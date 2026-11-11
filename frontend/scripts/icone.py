"""Rigenera le icone del portale da un solo disegno.

    python3 frontend/scripts/icone.py

Le icone stanno in `public/` già fatte, e questo script non gira nel build:
serve solo quando cambia il disegno. È lo stesso di `public/favicon.svg` —
lastra scura, filetto oro, «NSH» in crema — ridisegnato per ogni misura
invece che ingrandito, perché a 180 pixel il filetto di 2 pixel della
favicon sparirebbe e gli angoli arrotondati li mette già il telefono.

Rasterizza con Chrome senza finestra, non con una libreria: è l'unico
strumento sul Mac che ha Georgia, il carattere che la favicon nomina, e una
libreria con un altro serif farebbe un'icona diversa da quella della scheda.
`favicon.ico` è scritto a mano (un ICO che contiene PNG, formato accettato
da tutti i browser da Windows Vista in poi): niente Pillow da installare.
"""
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

FONDO, ORO, CREMA = "#211a15", "#b07d3c", "#ecdcc0"


def disegno(lato: int, *, testo: float, filetto: float, angolo: float = 0) -> str:
    """Il disegno della favicon su un quadrato di `lato`, in proporzione.

    `testo` e `filetto` sono frazioni del lato. Per l'icona «maskable» di
    Android il testo è più piccolo: il sistema ritaglia un cerchio e deve
    restare tutto dentro l'80% centrale.
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {lato} {lato}" width="{lato}" height="{lato}">
  <rect width="{lato}" height="{lato}" rx="{angolo}" fill="{FONDO}"/>
  <rect width="{lato}" height="{lato * filetto:.2f}" fill="{ORO}"/>
  <text x="{lato / 2}" y="{lato * 0.5 + lato * testo * 0.35:.2f}" text-anchor="middle"
        font-family="Georgia, 'Times New Roman', serif" font-size="{lato * testo:.2f}"
        letter-spacing="{lato * testo * 0.033:.2f}" fill="{CREMA}">NSH</text>
</svg>"""


ICONE = {
    # iPhone, «Aggiungi a Home». Quadrato pieno: gli angoli li arrotonda iOS.
    "apple-touch-icon.png": (180, dict(testo=0.36, filetto=0.045)),
    # Android e il manifest.
    "icon-192.png": (192, dict(testo=0.36, filetto=0.045)),
    "icon-512.png": (512, dict(testo=0.36, filetto=0.045)),
    "icon-maskable-512.png": (512, dict(testo=0.30, filetto=0.045)),
    # Dentro favicon.ico: lo stesso disegno della favicon.svg.
    "_ico-32.png": (32, dict(testo=15 / 32, filetto=2 / 32, angolo=2)),
    "_ico-48.png": (48, dict(testo=15 / 32, filetto=2 / 32, angolo=3)),
}


def rasterizza(svg: str, lato: int, uscita: Path, cartella: Path) -> None:
    sorgente = cartella / f"{uscita.stem}.svg"
    # Una pagina HTML e non l'SVG diretto: così il margine del body è zero e
    # il quadrato riempie la finestra al pixel.
    pagina = cartella / f"{uscita.stem}.html"
    sorgente.write_text(svg)
    pagina.write_text(
        f'<html><body style="margin:0;background:transparent"><img src="{sorgente.name}" '
        f'width="{lato}" height="{lato}" style="display:block"></body></html>'
    )
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=1", "--default-background-color=00000000",
         f"--window-size={lato},{lato}",
         f"--screenshot={uscita}", pagina.as_uri()],
        check=True, capture_output=True,
    )


def ico(pngs: list[Path], uscita: Path) -> None:
    """ICO con dentro i PNG così come sono (intestazione + una voce per PNG)."""
    dati = [p.read_bytes() for p in pngs]
    testa = struct.pack("<HHH", 0, 1, len(dati))
    offset = 6 + 16 * len(dati)
    voci = b""
    for blob in dati:
        larghezza, altezza = struct.unpack(">II", blob[16:24])
        voci += struct.pack("<BBBBHHII", larghezza % 256, altezza % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    uscita.write_bytes(testa + voci + b"".join(dati))


def main() -> None:
    if not Path(CHROME).exists():
        sys.exit(f"Serve Google Chrome in {CHROME}")
    with tempfile.TemporaryDirectory() as tmp:
        cartella = Path(tmp)
        for nome, (lato, opzioni) in ICONE.items():
            destinazione = (cartella if nome.startswith("_") else PUBLIC) / nome
            rasterizza(disegno(lato, **opzioni), lato, destinazione, cartella)
            print("scritta", destinazione.name)
        ico([cartella / "_ico-32.png", cartella / "_ico-48.png"], PUBLIC / "favicon.ico")
        print("scritta favicon.ico")
    # iOS, quando la pagina non lo dice, prova anche questo nome.
    shutil.copyfile(PUBLIC / "apple-touch-icon.png", PUBLIC / "apple-touch-icon-precomposed.png")
    print("scritta apple-touch-icon-precomposed.png")


if __name__ == "__main__":
    main()
