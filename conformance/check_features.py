"""Report offline SDK feature evidence from the canonical manifest.

This deliberately does not make network calls and does not replace each SDK's
tests. It catches a feature disappearing from a public source surface while
allowing language-specific method names and documented delegation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from check_conformance import SDK_SOURCES

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "conformance" / "feature_manifest.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def report(root: Path = ROOT) -> list[dict[str, str]]:
    manifest = load_manifest()
    rows: list[dict[str, str]] = []
    for feature, definition in manifest["features"].items():
        patterns = definition["patterns"]
        for sdk, paths in SDK_SOURCES.items():
            delegated = manifest.get("delegated", {}).get(sdk)
            delegated_reason = delegated if isinstance(delegated, str) else (delegated or {}).get(feature)
            if delegated_reason:
                rows.append({"feature": feature, "sdk": sdk, "status": "NOT APPLICABLE", "evidence": delegated_reason})
                continue
            source = "\n".join((root / path).read_text(encoding="utf-8") for path in paths if (root / path).exists())
            found = [pattern for pattern in patterns if pattern in source]
            rows.append({"feature": feature, "sdk": sdk, "status": "PASS" if found else "MISSING", "evidence": ", ".join(found) or "none"})
    return rows


def main() -> int:
    rows = report()
    print("FEATURE | SDK | STATUS | EVIDENCE")
    for row in rows:
        print(f"{row['feature']} | {row['sdk']} | {row['status']} | {row['evidence']}")
    return 0 if all(row["status"] != "MISSING" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
