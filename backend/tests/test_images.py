"""Pillow checks and resizes on generated images."""

from io import BytesIO

import pytest
from PIL import Image

from app.images import ImageInfo, InvalidImage, inspect, model_input, thumbnail


def make(format: str, size: tuple[int, int] = (64, 48)) -> bytes:
    image = Image.new("RGB", size, color=(200, 80, 20))
    out = BytesIO()
    image.save(out, format=format)
    return out.getvalue()


@pytest.mark.parametrize(
    ("format", "mime"),
    [
        ("JPEG", "image/jpeg"),
        ("PNG", "image/png"),
        ("WEBP", "image/webp"),
        ("GIF", "image/gif"),
    ],
)
def test_inspect_reports_mime_and_size(format: str, mime: str) -> None:
    assert inspect(make(format)) == ImageInfo(mime=mime, width=64, height=48)


def test_inspect_rejects_a_non_image_payload() -> None:
    with pytest.raises(InvalidImage):
        inspect(b"%PDF-1.4 not an image at all")


def test_inspect_rejects_an_image_of_another_format() -> None:
    with pytest.raises(InvalidImage, match="BMP"):
        inspect(make("BMP"))


def test_model_input_is_a_jpeg_with_the_longest_side_1024() -> None:
    data = model_input(make("PNG", size=(3000, 1500)))

    with Image.open(BytesIO(data)) as image:
        assert image.format == "JPEG"
        assert image.size == (1024, 512)


def test_model_input_keeps_a_small_image_at_its_size() -> None:
    data = model_input(make("GIF", size=(300, 200)))

    with Image.open(BytesIO(data)) as image:
        assert image.format == "JPEG"
        assert image.size == (300, 200)


def test_thumbnail_is_a_webp_with_the_longest_side_320() -> None:
    data = thumbnail(make("JPEG", size=(800, 1600)))

    with Image.open(BytesIO(data)) as image:
        assert image.format == "WEBP"
        assert image.size == (160, 320)


def test_resize_rejects_a_truncated_image() -> None:
    truncated = make("JPEG", size=(500, 500))[:200]

    with pytest.raises(InvalidImage):
        model_input(truncated)


def test_inspect_rejects_a_header_that_declares_too_many_pixels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same error Pillow raises for a real bomb, without a huge file.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(InvalidImage):
        inspect(make("PNG", size=(64, 48)))
