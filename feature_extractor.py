"""Interpretable text and image feature extraction for MCADS."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
import math
import re
import statistics

from PIL import Image, ImageFilter, ImageStat


@dataclass(frozen=True)
class TextFeatures:
    character_count: int
    url_count: int
    digit_ratio: float
    punctuation_ratio: float
    urgency_count: int
    credential_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ImageFeatures:
    width: int
    height: int
    aspect_ratio: float
    brightness: float
    contrast: float
    colorfulness: float
    edge_density: float
    byte_entropy: float

    def to_dict(self) -> dict:
        return asdict(self)


class MultimodalFeatureExtractor:
    """Extract normalized, model-independent features from text and images."""

    URGENCY_TERMS = ("立即", "马上", "尽快", "暂停", "过期", "最后通知")
    CREDENTIAL_TERMS = ("密码", "验证码", "账户", "登录", "身份信息")

    @staticmethod
    def _pixels(image: Image.Image):
        """Read pixels across Pillow versions without changing image content."""
        flattened = getattr(image, "get_flattened_data", None)
        return flattened() if flattened is not None else image.getdata()

    def extract_text(self, text: str) -> TextFeatures:
        compact = re.sub(r"\s+", "", text)
        length = len(compact)
        denominator = max(length, 1)
        return TextFeatures(
            character_count=length,
            url_count=len(re.findall(r"(?:https?://|www\.)", text, flags=re.I)),
            digit_ratio=round(sum(char.isdigit() for char in compact) / denominator, 4),
            punctuation_ratio=round(
                sum(not char.isalnum() and not "\u4e00" <= char <= "\u9fff" for char in compact)
                / denominator,
                4,
            ),
            urgency_count=sum(text.count(term) for term in self.URGENCY_TERMS),
            credential_count=sum(text.count(term) for term in self.CREDENTIAL_TERMS),
        )

    def extract_image(self, image_bytes: bytes) -> ImageFeatures:
        with Image.open(BytesIO(image_bytes)) as source:
            image = source.convert("RGB")
            width, height = image.size
            sample = image.copy()
            sample.thumbnail((256, 256))
            gray = sample.convert("L")
            gray_stat = ImageStat.Stat(gray)
            brightness = gray_stat.mean[0] / 255.0
            contrast = gray_stat.stddev[0] / 127.5
            pixels = list(self._pixels(sample))
            rg = [r - g for r, g, _ in pixels]
            yb = [0.5 * (r + g) - b for r, g, b in pixels]
            colorfulness = (
                math.sqrt(statistics.pvariance(rg) + statistics.pvariance(yb))
                + 0.3 * math.sqrt(statistics.mean(rg) ** 2 + statistics.mean(yb) ** 2)
            ) / 255.0 if len(rg) > 1 else 0.0
            edges = gray.filter(ImageFilter.FIND_EDGES)
            sample_width, sample_height = sample.size
            edge_density = sum(value > 32 for value in self._pixels(edges)) / max(sample_width * sample_height, 1)
        return ImageFeatures(
            width=width,
            height=height,
            aspect_ratio=round(width / max(height, 1), 4),
            brightness=round(brightness, 4),
            contrast=round(min(contrast, 1.0), 4),
            colorfulness=round(min(colorfulness, 1.0), 4),
            edge_density=round(min(edge_density, 1.0), 4),
            byte_entropy=round(self.byte_entropy(image_bytes), 4),
        )

    @staticmethod
    def byte_entropy(data: bytes) -> float:
        if not data:
            return 0.0
        counts = [0] * 256
        for value in data:
            counts[value] += 1
        size = len(data)
        return -sum((count / size) * math.log2(count / size) for count in counts if count)
