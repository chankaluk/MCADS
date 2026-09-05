"""Configurable scoring and action policy for multimodal audit results."""

from __future__ import annotations

from dataclasses import dataclass

from feature_extractor import ImageFeatures, TextFeatures


@dataclass(frozen=True)
class PolicyDecision:
    score: float
    action: str
    level: str
    labels: tuple[str, ...]
    explanations: tuple[str, ...]


class RiskPolicy:
    """Convert extracted signals into stable risk decisions."""

    TERM_WEIGHTS = {
        "点击": 0.08, "扫码": 0.14, "二维码": 0.18, "验证账户": 0.20,
        "立即处理": 0.10, "中奖": 0.16, "退款": 0.10, "转账": 0.18,
        "密码": 0.13, "验证码": 0.15, "http://": 0.12, "https://": 0.05,
    }

    def __init__(self, block_threshold: float = 0.75, review_threshold: float = 0.35) -> None:
        if not 0.0 < review_threshold < block_threshold < 1.0:
            raise ValueError("thresholds must satisfy 0 < review < block < 1")
        self.block_threshold = block_threshold
        self.review_threshold = review_threshold

    def evaluate(
        self,
        text: str,
        text_features: TextFeatures,
        image_features: ImageFeatures,
        image_size: int,
    ) -> PolicyDecision:
        normalized = "".join(text.lower().split())
        score = 0.08
        labels: list[str] = []
        reasons: list[str] = []
        for term, weight in self.TERM_WEIGHTS.items():
            if term in normalized:
                score += weight
                reasons.append(f"文本包含风险线索：{term}")
        if text_features.url_count:
            score += min(0.18, text_features.url_count * 0.06)
            labels.append("SUSPICIOUS_LINK")
        if text_features.urgency_count >= 2:
            score += 0.08
            labels.append("URGENCY_INDUCEMENT")
        if image_size > 2 * 1024 * 1024:
            score += 0.08
            labels.append("LARGE_IMAGE")
            reasons.append("图像文件体积较大")
        if image_features.byte_entropy > 7.75:
            score += 0.08
            labels.append("HIGH_ENTROPY_IMAGE")
            reasons.append("图像字节熵较高，建议进行人工复核")
        if any(term in normalized for term in ("扫码", "二维码")):
            labels.append("QR_CODE_PHISHING")
        if text_features.credential_count:
            labels.append("CREDENTIAL_PHISHING")
        score = round(max(0.0, min(score, 0.99)), 4)
        action = "BLOCK" if score >= self.block_threshold else "REVIEW" if score >= self.review_threshold else "PASS"
        level = "HIGH" if action == "BLOCK" else "MEDIUM" if action == "REVIEW" else "LOW"
        if not labels:
            labels.append("NO_EXPLICIT_ANOMALY")
        if not reasons:
            reasons.append("未发现明确的高风险文本或图像统计特征")
        return PolicyDecision(score, action, level, tuple(dict.fromkeys(labels)), tuple(reasons[:8]))

