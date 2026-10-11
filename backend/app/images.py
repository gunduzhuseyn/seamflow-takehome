"""Image checks and resizes with Pillow. The worker runs them on the upload."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}
# Longest side, in pixels. A smaller image keeps its size.
MODEL_INPUT_SIDE = 1024
THUMBNAIL_SIDE = 320


class InvalidImage(Exception):  # noqa: N818  # the name the plan uses
    """The bytes are not a JPEG, PNG, WebP, or GIF image."""


@dataclass(frozen=True)
class ImageInfo:
    mime: str
    width: int
    height: int


def _open(data: bytes) -> tuple[Image.Image, str]:
    """The image and its mime type. Reads the header only."""
    try:
        image = Image.open(BytesIO(data))
    except (OSError, Image.DecompressionBombError) as exc:
        # UnidentifiedImageError for an unknown header, OSError for a
        # header that ends early, DecompressionBombError for a header that
        # declares more pixels than MAX_IMAGE_PIXELS.
        raise InvalidImage("not an image") from exc
    mime = MIME_BY_FORMAT.get(image.format or "")
    if mime is None:
        image.close()
        raise InvalidImage(f"unsupported format {image.format}")
    return image, mime


def inspect(data: bytes) -> ImageInfo:
    image, mime = _open(data)
    with image:
        return ImageInfo(mime=mime, width=image.width, height=image.height)


def _resize(data: bytes, side: int, format: str, quality: int) -> bytes:
    image, _ = _open(data)
    with image:
        try:
            # The first frame of a GIF. RGB drops alpha, which neither
            # output needs.
            converted = (ImageOps.exif_transpose(image) or image).convert("RGB")
            converted.thumbnail((side, side))
            out = BytesIO()
            converted.save(out, format=format, quality=quality)
        except OSError as exc:
            # A file that is damaged past the header fails here, not in `open`.
            raise InvalidImage("damaged image") from exc
    return out.getvalue()


def model_input(data: bytes) -> bytes:
    """A JPEG with the longest side at most 1024 px, for the vision model."""
    return _resize(data, MODEL_INPUT_SIDE, "JPEG", quality=85)


def thumbnail(data: bytes) -> bytes:
    """A WebP with the longest side at most 320 px, for the result card."""
    return _resize(data, THUMBNAIL_SIDE, "WEBP", quality=80)
