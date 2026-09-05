"""Input validation and dataset utilities for MCADS."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
from typing import Iterable, Iterator

try:
    from PIL import Image
except ImportError:
    Image = None


ALLOWED_IMAGE_TYPES = {"jpeg", "png", "gif", "bmp", "webp"}
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
)


@dataclass(frozen=True)
class MultimodalRecord:
    record_id: str
    text: str
    image_bytes: bytes
    image_type: str
    image_sha256: str
    label: int | None = None


def validate_multimodal_input(
    text: str,
    image_bytes: bytes,
    *,
    max_text_length: int = 5000,
    max_image_size: int = 15 * 1024 * 1024,
) -> tuple[str, str]:
    """Validate user input and return normalized text and detected image type."""
    normalized = " ".join(text.split())
    if not normalized:
        raise ValueError("text_content must not be empty")
    if len(normalized) > max_text_length:
        raise ValueError(f"text_content exceeds {max_text_length} characters")
    if not image_bytes:
        raise ValueError("image_file must not be empty")
    if len(image_bytes) > max_image_size:
        raise ValueError(f"image_file exceeds {max_image_size} bytes")
    image_type = detect_image_type(image_bytes)
    if image_type not in ALLOWED_IMAGE_TYPES:
        raise ValueError("unsupported or invalid image file")
    if Image is not None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
        except Exception as exc:
            raise ValueError("corrupted or incomplete image file") from exc
    return normalized, image_type


def detect_image_type(image_bytes: bytes) -> str | None:
    """Detect supported images without relying on the removed imghdr module."""
    for signature, image_type in IMAGE_SIGNATURES:
        if image_bytes.startswith(signature):
            return image_type
    if (
        len(image_bytes) >= 12
        and image_bytes.startswith(b"RIFF")
        and image_bytes[8:12] == b"WEBP"
    ):
        return "webp"
    return None


def build_record(
    record_id: str,
    text: str,
    image_bytes: bytes,
    label: int | None = None,
) -> MultimodalRecord:
    normalized, image_type = validate_multimodal_input(text, image_bytes)
    return MultimodalRecord(
        record_id=record_id,
        text=normalized,
        image_bytes=image_bytes,
        image_type=image_type,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
        label=label,
    )


def load_manifest(path: str | Path) -> Iterator[MultimodalRecord]:
    """Load a tab-separated manifest: id, text, image_path, optional label."""
    manifest_path = Path(path)
    for line_number, raw_line in enumerate(
        manifest_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        fields = raw_line.split("\t")
        if len(fields) not in (3, 4):
            raise ValueError(f"invalid manifest line {line_number}")
        record_id, text, image_path = fields[:3]
        label = int(fields[3]) if len(fields) == 4 else None
        resolved = (manifest_path.parent / image_path).resolve()
        yield build_record(record_id, text, resolved.read_bytes(), label)


def batch_records(
    records: Iterable[MultimodalRecord], batch_size: int = 32
) -> Iterator[list[MultimodalRecord]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    batch: list[MultimodalRecord] = []
    for record in records:
        batch.append(record)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
