"""Turn whatever an admin uploads into something safe to store and serve.

Nothing here trusts the request. The declared `Content-Type` is a claim by the
caller, the file extension is a claim by the caller, and the byte count is only
known once the body has actually been read. So the rule is: decode it with an
image library or reject it, then re-encode it ourselves — the output is always
a file this module produced, never a file someone else uploaded.

Re-encoding also drops EXIF, which matters more than it sounds: a photo taken
on a phone carries GPS coordinates, and a product shot taken in the salon is
tagged with the salon's address.
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
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}

OUTPUT_CONTENT_TYPE = "image/jpeg"


class ImageRejected(Exception):
    """The upload is not something we are willing to store."""


def process_upload(raw: bytes) -> tuple[bytes, str]:
    """Validate, downscale and re-encode an uploaded image.

    Returns the bytes to store and their content type. Raises `ImageRejected`
    with a message meant for the person who picked the file.
    """
    if not raw:
        raise ImageRejected("Il file è vuoto.")
    if len(raw) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise ImageRejected(f"Immagine troppo grande: il limite è {mb} MB.")

    try:
        # Pillow refuses absurd pixel counts on its own (MAX_IMAGE_PIXELS), which
        # is the guard against a small file that decodes to gigabytes of canvas.
        image = Image.open(io.BytesIO(raw))
        image.load()
    except UnidentifiedImageError:
        raise ImageRejected("Il file non è un'immagine riconoscibile.")
    except Image.DecompressionBombError:
        raise ImageRejected("Immagine con troppi pixel.")
    except Exception:
        raise ImageRejected("Immagine illeggibile o danneggiata.")

    if image.format not in ALLOWED_FORMATS:
        raise ImageRejected("Formato non supportato: usa JPEG, PNG o WebP.")

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
