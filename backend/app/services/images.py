"""Turn whatever an admin uploads into something safe to store and serve.

Nothing here trusts the request. The declared `Content-Type` is a claim by the
caller, the file extension is a claim by the caller, and the byte count is only
known once the body has actually been read. So the rule is: decode it with an
image library or reject it, then re-encode it ourselves — the output is always
a file this module produced, never a file someone else uploaded.

Re-encoding also drops EXIF, which matters more than it sounds: a photo taken
on a phone carries GPS coordinates, and a product shot taken in the salon is
tagged with the salon's address.

L'ordine dei controlli qui non è cosmetico, ed è la ragione per cui questo
file è stato riscritto. La prima versione decodificava **e poi** guardava se
il formato era ammesso:

    image = Image.open(io.BytesIO(raw))
    image.load()                      # <- il decoder ha già girato, su tutto
    if image.format not in ALLOWED_FORMATS:
        raise ImageRejected(...)

Cioè l'allowlist non proteggeva niente: era un giudizio pronunciato dopo il
fatto. Chiunque potesse caricare arrivava a tutti i decoder registrati in
Pillow — TIFF, GIF, ICO, PCX, DDS, una trentina in tutto — che sono codice C
che gira su byte scelti dal chiamante, ed è lì che stanno storicamente i bug
di Pillow. Il formato "non supportato" veniva rifiutato *dopo* aver fatto
esattamente ciò che il rifiuto doveva impedire.

Adesso l'elenco arriva prima, e come parametro di `Image.open`: Pillow prova
soltanto i tre plugin passati, quindi l'header di un TIFF malevolo non viene
letto affatto — nemmeno dal parser dell'header. Il resto (dimensione in byte,
numero di pixel) è ordinato secondo lo stesso principio: ogni controllo sta
prima del lavoro che vuole evitare.
"""
import io

from PIL import Image, UnidentifiedImageError

# A phone camera writes 4–8 MB per shot. This is a ceiling on what we will read
# at all, so a 200 MB "image" is refused before it reaches the decoder.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Nobody inspects a shampoo bottle at 4000px. 900 keeps it crisp on a retina
# card while cutting a typical upload to a few tens of kilobytes.
MAX_EDGE = 900
JPEG_QUALITY = 82

# Formats Pillow may decode here. Narrow on purpose: the decoder is the part of
# the stack facing untrusted bytes, so it should be asked to do as little as
# possible.
#
# Tupla e non `set` perché è ciò che `Image.open(formats=...)` accetta: con un
# set solleva `TypeError`, che il gestore generico più sotto trasformerebbe in
# «immagine danneggiata» — un errore di configurazione travestito da colpa di
# chi carica il file. Il test `test_la_tupla_dei_formati_e_accettata_da_pillow`
# esiste per questo.
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")

# Quanti pixel accettiamo di allocare. Il limite in byte sopra non basta da
# solo: la compressione fa sì che pochi kB dichiarino una tela enorme, e la
# tela va in RAM decompressa (~3 byte per pixel), non compressa. 50 MP sono
# ~150 MB di RAM — abbondanti per una foto di prodotto, che ne usa una
# frazione, e sotto la soglia oltre cui il servizio verrebbe ucciso per OOM.
#
# Pillow ha una sua guardia (`MAX_IMAGE_PIXELS`), ma avvisa a 89 MP e solleva
# solo al doppio, cioè a ~178 MP = mezzo giga di RAM: troppo tardi per noi.
MAX_PIXELS = 50_000_000

OUTPUT_CONTENT_TYPE = "image/jpeg"

# Stesso messaggio per «non è un'immagine» e per «è un'immagine di un formato
# che non prendiamo»: da quando l'elenco è passato dentro `Image.open`, Pillow
# non distingue più i due casi — un TIFF non viene riconosciuto perché il suo
# plugin non è fra quelli provati. Il messaggio dice comunque l'unica cosa
# utile a chi ha scelto il file, cioè cosa caricare al posto suo.
UNSUPPORTED = (
    "Il file non è un'immagine in un formato supportato: "
    "carica un JPEG, un PNG o un WebP."
)


class ImageRejected(Exception):
    """The upload is not something we are willing to store."""


def process_upload(raw: bytes) -> tuple[bytes, str]:
    """Validate, downscale and re-encode an uploaded image.

    Returns the bytes to store and their content type. Raises `ImageRejected`
    with a message meant for the person who picked the file.
    """
    # 1. Byte. Il controllo più a buon mercato che ci sia, quindi il primo.
    if not raw:
        raise ImageRejected("Il file è vuoto.")
    if len(raw) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ImageRejected(f"Immagine troppo grande: il limite è {mb} MB.")

    # 2. Formato. `formats=` fa sì che Pillow provi soltanto i tre plugin che
    #    ci interessano: gli altri venti e passa non toccano questi byte
    #    nemmeno per leggerne l'intestazione. È qui che l'allowlist smette di
    #    essere un parere e diventa un confine.
    #
    #    `Image.open` legge solo l'header: decide formato e dimensioni senza
    #    decomprimere. Il lavoro vero è `load()`, più sotto — e in mezzo c'è
    #    spazio per il controllo sui pixel.
    try:
        image = Image.open(io.BytesIO(raw), formats=ALLOWED_FORMATS)
    except UnidentifiedImageError:
        raise ImageRejected(UNSUPPORTED)
    except Image.DecompressionBombError:
        raise ImageRejected("Immagine con troppi pixel.")
    except Exception:
        raise ImageRejected("Immagine illeggibile o danneggiata.")

    # Cintura oltre alle bretelle: `formats=` è già il confine, ma se un giorno
    # qualcuno rimettesse `Image.open(...)` senza parametro, questa riga
    # continuerebbe a reggere.
    if image.format not in ALLOWED_FORMATS:
        raise ImageRejected(UNSUPPORTED)

    # 3. Pixel, prima di allocarli. Un PNG di 40 kB può dichiarare 30.000 ×
    #    30.000: sono 900 milioni di pixel, ~2,7 GB di RAM, e il processo muore
    #    prima di poter rifiutare alcunché. Il conto si fa sull'header.
    larghezza, altezza = image.size
    if larghezza * altezza > MAX_PIXELS:
        mp = MAX_PIXELS // 1_000_000
        raise ImageRejected(f"Immagine con troppi pixel: il limite è {mp} MP.")

    # 4. Solo adesso il decoder gira davvero.
    try:
        image.load()
    except Image.DecompressionBombError:
        raise ImageRejected("Immagine con troppi pixel.")
    except Exception:
        raise ImageRejected("Immagine illeggibile o danneggiata.")

    # JPEG has no alpha channel, so a transparent PNG has to land on something.
    # White rather than black: these are product shots, usually already on a
    # pale background, and black would read as a border.
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flattened = Image.new("RGB", image.size, (255, 255, 255))
        flattened.paste(image, mask=image.split()[-1])
        image = flattened
    elif image.mode != "RGB":
        image = image.convert("RGB")

    image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue(), OUTPUT_CONTENT_TYPE
