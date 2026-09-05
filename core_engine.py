"""MCADS core multimodal anomaly detection engine.

The module provides a deterministic baseline that can run without model
weights, plus an optional PyTorch cross-attention network for trained models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from feature_extractor import MultimodalFeatureExtractor
from risk_policy import RiskPolicy

try:
    import torch
    from torch import nn
except ImportError:  # The baseline remains usable in lightweight deployments.
    torch = None
    nn = None


@dataclass(frozen=True)
class AuditResult:
    """Normalized result returned by every inference backend."""

    risk_score: float
    action: str
    labels: tuple[str, ...]
    explanation: tuple[str, ...]
    model_version: str
    risk_level: str = "LOW"
    feature_summary: dict | None = None

    def to_dict(self) -> dict:
        return {
            "risk_score": round(self.risk_score, 4),
            "action": self.action,
            "labels": list(self.labels),
            "explanation": list(self.explanation),
            "model_version": self.model_version,
            "risk_level": self.risk_level,
            "feature_summary": self.feature_summary or {},
        }


if nn is not None:
    class CrossModalFusionEngine(nn.Module):
        """Bidirectional cross-attention classifier for trained embeddings."""

        def __init__(
            self,
            text_dim: int = 768,
            vision_dim: int = 512,
            embed_dim: int = 256,
            num_heads: int = 4,
            dropout: float = 0.2,
        ) -> None:
            super().__init__()
            self.text_projection = nn.Linear(text_dim, embed_dim)
            self.vision_projection = nn.Linear(vision_dim, embed_dim)
            self.text_to_image = nn.MultiheadAttention(
                embed_dim, num_heads, dropout=dropout, batch_first=True
            )
            self.image_to_text = nn.MultiheadAttention(
                embed_dim, num_heads, dropout=dropout, batch_first=True
            )
            self.classifier = nn.Sequential(
                nn.LayerNorm(embed_dim * 2),
                nn.Linear(embed_dim * 2, 256),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(256, 2),
            )

        def forward(self, text_features, vision_features):
            text = self.text_projection(text_features)
            vision = self.vision_projection(vision_features)
            text_context, _ = self.text_to_image(text, vision, vision)
            vision_context, _ = self.image_to_text(vision, text, text)
            fused = torch.cat(
                [text_context.mean(dim=1), vision_context.mean(dim=1)], dim=-1
            )
            return self.classifier(fused)
else:
    class CrossModalFusionEngine:  # pragma: no cover - dependency message only
        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PyTorch is required for neural network inference")


class MultimodalRiskEngine:
    """Hybrid feature-fusion backend for demos, tests and CPU deployment."""

    def __init__(self, block_threshold: float = 0.75) -> None:
        if not 0.0 < block_threshold < 1.0:
            raise ValueError("block_threshold must be between 0 and 1")
        self.block_threshold = block_threshold
        review_threshold = min(0.35, block_threshold * 0.7)
        self.extractor = MultimodalFeatureExtractor()
        self.policy = RiskPolicy(block_threshold, review_threshold)

    def predict(self, text: str, image_bytes: bytes) -> AuditResult:
        text_features = self.extractor.extract_text(text)
        image_features = self.extractor.extract_image(image_bytes)
        decision = self.policy.evaluate(text, text_features, image_features, len(image_bytes))
        return AuditResult(
            risk_score=decision.score,
            action=decision.action,
            labels=decision.labels,
            explanation=decision.explanations,
            model_version="MCADS-HybridFusion-1.0",
            risk_level=decision.level,
            feature_summary={"text": text_features.to_dict(), "image": image_features.to_dict()},
        )

    @staticmethod
    def _byte_entropy(data: bytes) -> float:
        return MultimodalFeatureExtractor.byte_entropy(data)


def neural_predict(model, text_features, vision_features) -> Sequence[float]:
    """Return anomaly probabilities for pre-computed encoder features."""
    if torch is None:
        raise RuntimeError("PyTorch is required for neural network inference")
    model.eval()
    with torch.no_grad():
        logits = model(text_features, vision_features)
        return torch.softmax(logits, dim=-1)[:, 1].cpu().tolist()
