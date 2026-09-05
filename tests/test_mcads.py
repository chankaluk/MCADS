import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import api_gateway
from api_gateway import _demo_png, audit_content, read_audit_history
from audit_repository import AuditRepository
from core_engine import MultimodalRiskEngine
from dataset_loader import build_record, detect_image_type, validate_multimodal_input
from feature_extractor import MultimodalFeatureExtractor
from risk_policy import RiskPolicy


class InputValidationTests(unittest.TestCase):
    def test_detect_png(self):
        self.assertEqual(detect_image_type(_demo_png()), "png")

    def test_empty_text_rejected(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            validate_multimodal_input("", _demo_png())

    def test_invalid_image_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            validate_multimodal_input("测试", b"not-an-image")

    def test_oversized_image_rejected_before_decode(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            validate_multimodal_input("测试", _demo_png() + b"x" * 100, max_image_size=20)

    def test_record_hash_is_stable(self):
        first = build_record("A", "  普通   通知 ", _demo_png())
        second = build_record("B", "普通 通知", _demo_png())
        self.assertEqual(first.text, "普通 通知")
        self.assertEqual(first.image_sha256, second.image_sha256)


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = MultimodalRiskEngine(block_threshold=0.50)

    def test_normal_content_passes(self):
        result = self.engine.predict("普通会议通知", _demo_png())
        self.assertEqual(result.action, "PASS")
        self.assertLess(result.risk_score, 0.50)

    def test_phishing_content_blocks(self):
        result = self.engine.predict("请立即扫码验证账户密码", _demo_png())
        self.assertEqual(result.action, "BLOCK")
        self.assertIn("CREDENTIAL_PHISHING", result.labels)

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ValueError):
            MultimodalRiskEngine(block_threshold=1.0)

    def test_result_contains_feature_summary(self):
        result = self.engine.predict("普通通知", _demo_png()).to_dict()
        self.assertIn("text", result["feature_summary"])
        self.assertIn("image", result["feature_summary"])


class FeatureExtractorTests(unittest.TestCase):
    def setUp(self):
        self.extractor = MultimodalFeatureExtractor()

    def test_text_features_count_links_and_credentials(self):
        features = self.extractor.extract_text("立即登录 https://example.test 输入密码123")
        self.assertEqual(features.url_count, 1)
        self.assertGreaterEqual(features.credential_count, 2)
        self.assertGreater(features.digit_ratio, 0)

    def test_image_features_support_single_pixel(self):
        features = self.extractor.extract_image(_demo_png())
        self.assertEqual((features.width, features.height), (1, 1))
        self.assertGreaterEqual(features.byte_entropy, 0)

    def test_empty_entropy_is_zero(self):
        self.assertEqual(self.extractor.byte_entropy(b""), 0.0)


class RiskPolicyTests(unittest.TestCase):
    def test_invalid_threshold_order_rejected(self):
        with self.assertRaises(ValueError):
            RiskPolicy(block_threshold=0.4, review_threshold=0.5)

    def test_medium_score_can_request_review(self):
        engine = MultimodalRiskEngine(block_threshold=0.8)
        result = engine.predict("请扫码验证账户", _demo_png())
        self.assertEqual(result.action, "REVIEW")
        self.assertEqual(result.risk_level, "MEDIUM")


class RepositoryTests(unittest.TestCase):
    def test_corrupt_lines_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            path.write_text('{"record_id":"A","action":"PASS","risk_score":0.1}\ninvalid\n', encoding="utf-8")
            records = AuditRepository(path).latest()
        self.assertEqual([item["record_id"] for item in records], ["A"])

    def test_statistics_aggregate_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = AuditRepository(Path(directory) / "audit.jsonl")
            repository.append({"action": "PASS", "risk_score": 0.1})
            repository.append({"action": "BLOCK", "risk_score": 0.9})
            stats = repository.statistics()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["block_count"], 1)
        self.assertEqual(stats["average_risk_score"], 0.5)

    def test_repository_limit_validation(self):
        with self.assertRaises(ValueError):
            AuditRepository("unused.jsonl").latest(0)


class StaticAssetTests(unittest.TestCase):
    def test_css_has_no_corrupted_spacing_patterns(self):
        css = Path("static/styles.css").read_text(encoding="utf-8")
        for invalid in (": root", "var (", " px", "box - sizing"):
            self.assertNotIn(invalid, css)

    def test_frontend_references_statistics_endpoint(self):
        script = Path("static/app.js").read_text(encoding="utf-8")
        self.assertIn("/api/v1/audit/statistics", script)


class GatewayTests(unittest.TestCase):
    def test_invalid_trace_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "trace_id"):
            audit_content("普通通知", _demo_png(), "含 空格")

    def test_audit_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "audit.jsonl"
            with patch.object(api_gateway, "AUDIT_LOG", log_path):
                report = audit_content("普通通知", _demo_png(), "TEST-001")
                history = read_audit_history(10)
            self.assertEqual(report["record_id"], "TEST-001")
            self.assertEqual(history[0]["record_id"], "TEST-001")
            self.assertNotIn("text_content", history[0])

    def test_history_limit_validation(self):
        with self.assertRaises(ValueError):
            read_audit_history(101)


if __name__ == "__main__":
    unittest.main()
