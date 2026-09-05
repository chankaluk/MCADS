"""Project checks and source-document generation entry point.

Run ``python generate_code.py --check`` to compile project modules and execute
the deterministic smoke test. Document generation is implemented by
``build_documents.py`` so that source and documentation remain synchronized.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import py_compile


PROJECT_FILES = (
    "feature_extractor.py",
    "risk_policy.py",
    "audit_repository.py",
    "core_engine.py",
    "dataset_loader.py",
    "api_gateway.py",
    "generate_code.py",
)


def check_project() -> dict:
    results = {}
    for filename in PROJECT_FILES:
        py_compile.compile(filename, doraise=True)
        results[filename] = "syntax-ok"

    from api_gateway import _demo_png, audit_content

    report = audit_content(
        "请立即扫码验证账户密码，否则将暂停服务。",
        _demo_png(),
        "CHECK-001",
    )
    if not 0.0 <= report["risk_score"] <= 1.0:
        raise AssertionError("risk_score is outside [0, 1]")
    results["smoke_test"] = {
        "action": report["action"],
        "risk_score": report["risk_score"],
    }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="MCADS project utility")
    parser.add_argument("--check", action="store_true", help="run project checks")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(check_project(), ensure_ascii=False, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
