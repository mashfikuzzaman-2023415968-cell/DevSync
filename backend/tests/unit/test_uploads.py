"""Upload pipeline (spec §14.9, §16.4 uploads): signatures, polyglots, active content, image
re-encoding (metadata stripped, bomb guard, size), signed URLs, storage and names."""

from __future__ import annotations

import asyncio
import io
import os
import stat
import struct
import zlib
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from pathlib import Path

import pytest
from PIL import Image

from app.models.profiles import FileKind
from app.uploads import detect, images, pipeline, signing
from app.uploads.errors import UploadRejectedError, UploadTooLargeError
from app.uploads.storage import Storage, sanitize_name

pytestmark = [pytest.mark.unit, pytest.mark.security]

SECRET = "test-secret-key-" * 4
NOW = datetime(2026, 10, 18, 5, 0, tzinfo=UTC)
MB = 1024 * 1024


class Source:
    """An UploadFile-like async reader."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)


def image_bytes(
    fmt: str = "JPEG", size: tuple[int, int] = (64, 48), mode: str = "RGB", **kw: object
) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, (20, 120, 110) if mode == "RGB" else None).save(buf, fmt, **kw)
    return buf.getvalue()


def jpeg_with_gps() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"  # camera make
    exif[0x0112] = 6  # orientation: rotate 90°
    exif.get_ifd(0x8825)[2] = (Fraction(23), Fraction(48), Fraction(30))  # GPS latitude
    return image_bytes("JPEG", (80, 40), exif=exif.tobytes())


def minimal_pdf(body: bytes = b"1 0 obj<</Type/Catalog>>endobj\n") -> bytes:
    return b"%PDF-1.7\n" + body + b"trailer<<>>\n%%EOF\n"


def write(tmp_path: Path, data: bytes, name: str = "f") -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


async def accept(
    tmp_path: Path,
    data: bytes,
    kind: FileKind = FileKind.PORTFOLIO_IMAGE,
    name: str | None = "photo.jpg",
    limit: int = 20 * MB,
) -> pipeline.StoredUpload:
    return await pipeline.accept_upload(
        Storage(str(tmp_path / "store")), Source(data), kind=kind, filename=name,
        max_upload_bytes=limit,
    )  # fmt: skip


# --------------------------------------------------------------------------- detection


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (image_bytes("PNG"), "image/png"),
        (image_bytes("JPEG"), "image/jpeg"),
        (image_bytes("WEBP"), "image/webp"),
        (minimal_pdf(), "application/pdf"),
        (b"plain review text\n", "text/plain"),
    ],
)
def test_sniff_uses_content_not_name(tmp_path: Path, data: bytes, mime: str) -> None:
    assert detect.sniff(write(tmp_path, data, "misleading.exe")) == mime


def test_sniff_rejects_empty_file(tmp_path: Path) -> None:
    with pytest.raises(UploadRejectedError, match="empty"):
        detect.sniff(write(tmp_path, b""))


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_clean_images_pass_structure_check(tmp_path: Path, fmt: str) -> None:
    data = image_bytes(fmt)
    detect.check_structure(write(tmp_path, data), detect.sniff(write(tmp_path, data, "g")))


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_appended_archive_is_rejected(tmp_path: Path, fmt: str) -> None:
    data = image_bytes(fmt) + b"PK\x03\x04" + b"\x00" * 200
    mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
    with pytest.raises(UploadRejectedError, match="extra data"):
        detect.check_structure(write(tmp_path, data), mime)


def test_jpeg_polyglot_ending_in_an_end_marker_is_still_rejected(tmp_path: Path) -> None:
    data = image_bytes("JPEG") + b"PK\x03\x04" + b"x" * 64 + b"\xff\xd9"
    with pytest.raises(UploadRejectedError, match="another file"):
        detect.check_structure(write(tmp_path, data), "image/jpeg")


def test_html_hidden_in_an_image_is_rejected(tmp_path: Path) -> None:
    png = image_bytes("PNG")
    # A tEXt chunk carrying a script, inserted before IEND (structure stays valid).
    payload = b"Comment\x00<script>alert(1)</script>"
    chunk = (
        struct.pack(">I", len(payload))
        + b"tEXt"
        + payload
        + struct.pack(">I", zlib.crc32(b"tEXt" + payload))
    )
    data = png[:-12] + chunk + png[-12:]
    with pytest.raises(UploadRejectedError, match="web page or script"):
        detect.check_structure(write(tmp_path, data), "image/png")


def test_small_padding_after_an_image_is_tolerated(tmp_path: Path) -> None:
    detect.check_structure(write(tmp_path, image_bytes("JPEG") + b"\x00" * 8), "image/jpeg")


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR", "image/png"),  # no IEND
        (b"RIFX\x00\x00\x00\x00WEBP", "image/webp"),
        (b"\xff\xd8\xff\xe0 no end marker", "image/jpeg"),
    ],
)
def test_truncated_images_are_rejected(tmp_path: Path, data: bytes, mime: str) -> None:
    with pytest.raises(UploadRejectedError, match="damaged"):
        detect.check_structure(write(tmp_path, data), mime)


@pytest.mark.parametrize(
    "body",
    [
        b"1 0 obj<</OpenAction 2 0 R>>endobj\n",
        b"1 0 obj<</S/JavaScript/JS(app.alert(1))>>endobj\n",
        b"1 0 obj<</J#61vaScript 2 0 R>>endobj\n",  # hex-escaped name
        b"1 0 obj<</Type/EmbeddedFile>>endobj\n",
        b"1 0 obj<</S/Launch/F(cmd.exe)>>endobj\n",
        b"1 0 obj<</AA<<>>>>endobj\n",
        b"1 0 obj<</XFA 3 0 R>>endobj\n",
        b"1 0 obj<</S/SubmitForm>>endobj\n",
    ],
)
def test_pdf_with_actions_is_rejected(tmp_path: Path, body: bytes) -> None:
    with pytest.raises(UploadRejectedError, match="scripts, actions or attachments"):
        detect.check_structure(write(tmp_path, minimal_pdf(body)), "application/pdf")


def test_pdf_action_hidden_in_a_compressed_object_stream_is_rejected(tmp_path: Path) -> None:
    stream = zlib.compress(b"<</Type/Catalog/OpenAction 3 0 R>>")
    body = b"1 0 obj<</Type/ObjStm/Filter/FlateDecode>>stream\n" + stream + b"\nendstream endobj\n"
    with pytest.raises(UploadRejectedError, match="scripts, actions"):
        detect.check_structure(write(tmp_path, minimal_pdf(body)), "application/pdf")


def test_pdf_with_html_or_archive_inside_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(UploadRejectedError):
        detect.check_structure(
            write(tmp_path, minimal_pdf(b"<html><script>x</script>")), "application/pdf"
        )
    with pytest.raises(UploadRejectedError, match="another file"):
        detect.check_structure(write(tmp_path, minimal_pdf(b"PK\x03\x04zip")), "application/pdf")
    inner = zlib.compress(b"PK\x03\x04 zipped inside a stream")
    body = b"1 0 obj<<>>stream\n" + inner + b"\nendstream\n"
    with pytest.raises(UploadRejectedError, match="another file"):
        detect.check_structure(write(tmp_path, minimal_pdf(body)), "application/pdf")


def test_pdf_with_links_and_image_streams_is_accepted(tmp_path: Path) -> None:
    link = (
        b"1 0 obj<</Type/Annot/Subtype/Link/A<</S/URI/URI(https://example.com/verify)>>>>endobj\n"
    )
    raw = b"2 0 obj<</Filter/DCTDecode>>stream\n\x00\x01not-flate\nendstream\n"
    flate = (
        b"3 0 obj<</Filter/FlateDecode>>stream\n"
        + zlib.compress(b"BT /F1 12 Tf ET")
        + b"\nendstream\n"
    )
    detect.check_structure(write(tmp_path, minimal_pdf(link + raw + flate)), "application/pdf")


def test_pdf_compression_bomb_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detect, "PDF_INFLATE_BUDGET", 1000)
    stream = zlib.compress(b"\x00" * 50_000)
    body = b"1 0 obj<<>>stream\n" + stream + b"\nendstream\n"
    with pytest.raises(UploadRejectedError, match="too complex"):
        detect.check_structure(write(tmp_path, minimal_pdf(body)), "application/pdf")


@pytest.mark.parametrize("data", [b"%PDF-1.7\nno end", b"not a pdf %%EOF"])
def test_broken_pdf_is_rejected(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(UploadRejectedError, match="damaged"):
        detect.check_structure(write(tmp_path, data), "application/pdf")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"text\x00with nul", "binary"),
        (b"caf\xe9 latin-1", "UTF-8"),
        (b"see <script>alert(1)</script>", "web page or script"),
    ],
)
def test_text_files_must_be_plain_utf8(tmp_path: Path, data: bytes, message: str) -> None:
    with pytest.raises(UploadRejectedError, match=message):
        detect.check_structure(write(tmp_path, data), "text/plain")


def test_utf8_text_is_accepted(tmp_path: Path) -> None:
    detect.check_structure(write(tmp_path, "চমৎকার কাজ — 5/5\n".encode()), "text/plain")


# --------------------------------------------------------------------------- re-encoding


def test_reencode_strips_exif_and_gps_and_applies_orientation() -> None:
    raw = jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif().get_ifd(0x8825)  # the input has GPS
    out = images.reencode(raw, "image/jpeg")
    clean = Image.open(io.BytesIO(out.data))
    assert dict(clean.getexif()) == {}
    assert "exif" not in clean.info
    assert "icc_profile" not in clean.info
    assert (out.width, out.height) == (40, 80)  # rotated by the orientation tag, then dropped


def test_reencode_limits_the_longest_side(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(images, "MAX_SIDE", 100)
    out = images.reencode(image_bytes("PNG", (400, 200)), "image/png")
    assert (out.width, out.height) == (100, 50)


@pytest.mark.parametrize(
    ("fmt", "mode", "mime"),
    [("PNG", "P", "image/png"), ("PNG", "RGBA", "image/png"), ("PNG", "LA", "image/png"),
     ("WEBP", "RGBA", "image/webp"), ("PNG", "1", "image/png")],
)  # fmt: skip
def test_reencode_normalises_colour_modes(fmt: str, mode: str, mime: str) -> None:
    out = images.reencode(image_bytes(fmt, (16, 16), mode), mime)
    assert Image.open(io.BytesIO(out.data)).format == fmt


def test_reencode_converts_cmyk_jpeg_to_rgb() -> None:
    out = images.reencode(image_bytes("JPEG", (8, 8), "CMYK"), "image/jpeg")
    assert Image.open(io.BytesIO(out.data)).mode == "RGB"


def test_reencode_rejects_a_type_mismatch() -> None:
    with pytest.raises(UploadRejectedError, match="doesn't match"):
        images.reencode(image_bytes("PNG"), "image/jpeg")


def test_reencode_rejects_a_decompression_bomb(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(images, "MAX_PIXELS", 1000)
    with pytest.raises(UploadRejectedError, match="too many pixels"):
        images.reencode(image_bytes("PNG", (100, 100)), "image/png")


def test_reencode_rejects_pillow_bomb_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)  # Pillow's own guard trips first
    with pytest.raises(UploadRejectedError, match="too many pixels"):
        images.reencode(image_bytes("PNG", (100, 100)), "image/png")


def test_reencode_rejects_damaged_images() -> None:
    raw = image_bytes("PNG", (32, 32))
    with pytest.raises(UploadRejectedError, match="damaged or not supported"):
        images.reencode(raw[:60] + b"\x00" * 40, "image/png")


# --------------------------------------------------------------------------- signing


def signed(expires: int | None = None) -> signing.SignedFile:
    exp = signing.expiry(NOW) if expires is None else expires
    return signing.SignedFile("0b7d4c1e-2f3a-4b5c-8d9e-0f1a2b3c4d5e", "image/png", "a.png", exp)


def _sig(url: str) -> str:
    return url.rsplit("s=", 1)[1]


def test_signed_url_verifies_within_five_minutes() -> None:
    f = signed()
    url = signing.sign_url(SECRET, f)
    assert url.startswith(f"/api/v1/files/blob/{f.storage_key}?")
    assert signing.verify(SECRET, f, _sig(url), NOW + timedelta(minutes=4, seconds=59))


def test_signed_url_expires() -> None:
    f = signed()
    assert not signing.verify(
        SECRET, f, _sig(signing.sign_url(SECRET, f)), NOW + timedelta(minutes=5, seconds=1)
    )


@pytest.mark.parametrize("field", ["storage_key", "mime_type", "name", "expires"])
def test_tampered_signed_url_is_refused(field: str) -> None:
    f = signed()
    sig = _sig(signing.sign_url(SECRET, f))
    changed = {"storage_key": "11111111-2222-4333-8444-555555555555", "mime_type": "text/html",
               "name": "a.html", "expires": f.expires + 60}[field]  # fmt: skip
    tampered = signing.SignedFile(**{**f.__dict__, field: changed})
    assert not signing.verify(SECRET, tampered, sig, NOW)


def test_signature_from_another_key_is_refused() -> None:
    f = signed()
    assert not signing.verify(SECRET, f, _sig(signing.sign_url("other-secret-" * 5, f)), NOW)


def test_expiry_far_in_the_future_is_refused() -> None:
    f = signed(int((NOW + timedelta(days=1)).timestamp()))
    assert not signing.verify(SECRET, f, _sig(signing.sign_url(SECRET, f)), NOW)


# --------------------------------------------------------------------------- storage and names


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\photo.jpg", "photo.jpg"),
        ("<img src=x onerror=alert(1)>.png", "img src_x onerror_alert(1)_.png"),
        ("re\u202esume\u0000.pdf", "resume.pdf"),
        ("   ", "file"),
        (None, "file"),
        ("a" * 300 + ".png", "a" * 120),
    ],
)
def test_sanitize_name(raw: str | None, expected: str) -> None:
    assert sanitize_name(raw) == expected


async def test_receive_streams_to_a_private_temp_file_and_cleans_up(tmp_path: Path) -> None:
    store = Storage(str(tmp_path))
    async with store.receive(Source(b"x" * 200_000), limit=MB) as path:
        assert path.stat().st_size == 200_000
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.parent == tmp_path / ".incoming"
    assert not path.exists()


async def test_receive_enforces_the_size_limit_while_streaming(tmp_path: Path) -> None:
    store = Storage(str(tmp_path))
    with pytest.raises(UploadTooLargeError):
        async with store.receive(Source(b"x" * (MB + 1)), limit=MB):
            pass  # pragma: no cover - never reached
    assert list((tmp_path / ".incoming").iterdir()) == []


def test_save_uses_a_random_key_and_restrictive_modes(tmp_path: Path) -> None:
    store = Storage(str(tmp_path / "uploads"))
    key = store.save(b"data")
    path = store.path_for(key)
    assert path.read_bytes() == b"data"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert stat.S_IMODE(os.stat(tmp_path / "uploads").st_mode) & 0o007 == 0
    store.delete(key)
    store.delete(key)  # idempotent
    assert not path.exists()


# --------------------------------------------------------------------------- pipeline


async def test_pipeline_stores_a_clean_image(tmp_path: Path) -> None:
    up = await accept(tmp_path, jpeg_with_gps(), name="../../holiday.PNG")
    assert up.mime_type == "image/jpeg"
    assert up.original_name == "holiday.jpg"  # extension from the detected type
    stored = (tmp_path / "store" / up.storage_key).read_bytes()
    assert len(stored) == up.size_bytes
    assert Image.open(io.BytesIO(stored)).getexif() == {}
    assert len(up.sha256) == 64
    assert (up.width, up.height) == (40, 80)


@pytest.mark.parametrize(
    ("kind", "data", "ok"),
    [
        (FileKind.PORTFOLIO_IMAGE, minimal_pdf(), False),
        (FileKind.PORTFOLIO_IMAGE, b"just text", False),
        (FileKind.PORTFOLIO_IMAGE, b"<svg xmlns='http://www.w3.org/2000/svg'/>", False),
        (FileKind.PORTFOLIO_IMAGE, b"PK\x03\x04" + b"\x00" * 100, False),
        (FileKind.CERTIFICATE, minimal_pdf(), True),
        (FileKind.CERTIFICATE, b"just text", False),
        (FileKind.EXTERNAL_REVIEW, b"Great work, 5 stars\n", True),
        (FileKind.EXTERNAL_REVIEW, image_bytes("WEBP"), True),
    ],
)
async def test_pipeline_allows_only_the_types_of_each_kind(
    tmp_path: Path, kind: FileKind, data: bytes, ok: bool
) -> None:
    if ok:
        up = await accept(tmp_path, data, kind, name="x")
        assert up.width is None or up.mime_type.startswith("image/")
    else:
        with pytest.raises(UploadRejectedError, match="Only"):
            await accept(tmp_path, data, kind)
    assert not list((tmp_path / "store" / ".incoming").iterdir())


async def test_pipeline_limits_by_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "PDF_MAX_BYTES", 100)
    monkeypatch.setattr(pipeline, "TEXT_MAX_BYTES", 10)
    with pytest.raises(UploadTooLargeError, match="at most"):
        await accept(tmp_path, minimal_pdf(b"x" * 200), FileKind.CERTIFICATE)
    with pytest.raises(UploadTooLargeError):
        await accept(tmp_path, b"more than ten bytes of text", FileKind.EXTERNAL_REVIEW)
    with pytest.raises(UploadTooLargeError):
        await accept(tmp_path, image_bytes("PNG"), limit=50)
    assert not (tmp_path / "store").exists() or not [
        p for p in (tmp_path / "store").iterdir() if p.name != ".incoming"
    ]


def test_type_limit_never_exceeds_the_upload_limit() -> None:
    assert pipeline.type_limit("application/pdf", 5 * MB) == 5 * MB
    assert pipeline.type_limit("application/pdf", 50 * MB) == 10 * MB
    assert pipeline.type_limit("text/plain", 50 * MB) == MB
    assert pipeline.type_limit("image/png", 20 * MB) == 20 * MB


def test_pipeline_is_usable_from_sync_code(tmp_path: Path) -> None:
    up = asyncio.run(accept(tmp_path, image_bytes("PNG"), name=None))
    assert up.original_name == "file.png"
