"""Cross-registry release-train invariants.

Package managers store versions differently, but one nRouter SDK generation
must have one public version.  This gate reads the actual distribution
metadata rather than a hand-maintained documentation table.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]


def _property(path: Path, name: str) -> str:
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            return value.strip()
    raise AssertionError(f"{path.relative_to(ROOT)} has no {name}= property")


def _matched(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(), flags=re.MULTILINE)
    if match is None:
        raise AssertionError(f"{path.relative_to(ROOT)} has no release version")
    return match.group(1)


def test_sdk_version_1_all_release_metadata_matches_contract() -> None:
    canonical = json.loads((ROOT / "spec/nrouter-sdk-spec.json").read_text())["version"]
    with (ROOT / "sdks/python/pyproject.toml").open("rb") as handle:
        python_version = tomllib.load(handle)["project"]["version"]
    with (ROOT / "sdks/rust/Cargo.toml").open("rb") as handle:
        rust_version = tomllib.load(handle)["package"]["version"]

    pom = ET.parse(ROOT / "sdks/java/pom.xml").getroot()
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}

    versions = {
        "javascript": json.loads((ROOT / "sdks/js/package.json").read_text())[
            "version"
        ],
        "python": python_version,
        "java": pom.findtext("m:version", namespaces=namespace),
        "kotlin": _property(ROOT / "sdks/kotlin/gradle.properties", "version"),
        "android": _property(ROOT / "sdks/android/gradle.properties", "version"),
        "android dependency lock": _matched(
            ROOT / "sdks/android/gradle.lockfile",
            r"^ai\.nrouter:nrouter-sdk-kotlin:([^=]+)=",
        ),
        "go": (ROOT / "sdks/go/VERSION").read_text().strip()
        if (ROOT / "sdks/go/VERSION").exists()
        else "<missing>",
        "rust": rust_version,
        "swift": (ROOT / "sdks/swift/VERSION").read_text().strip()
        if (ROOT / "sdks/swift/VERSION").exists()
        else "<missing>",
        "dart": _matched(ROOT / "sdks/dart/pubspec.yaml", r"^version:\s*([^\s]+)$"),
        "r": _matched(ROOT / "sdks/r/DESCRIPTION", r"^Version:\s*([^\s]+)$"),
    }

    assert versions == dict.fromkeys(versions, canonical), versions


def test_sdk_version_2_go_module_path_carries_the_release_major() -> None:
    version = (ROOT / "sdks/go/VERSION").read_text().strip()
    major = int(version.split(".", 1)[0])
    module = (
        (ROOT / "sdks/go/go.mod").read_text().splitlines()[0].removeprefix("module ")
    )

    if major >= 2:
        assert module.endswith(
            f"/v{major}"
        ), f"Go {version} requires a /v{major} module path; got {module}"


def test_sdk_version_3_source_only_workflows_cannot_publish() -> None:
    """Unsupported previews must verify packages without registry credentials."""
    for sdk in ("kotlin", "android"):
        workflow = (ROOT / f".github/workflows/publish-{sdk}.yml").read_text()
        assert "publishToMavenLocal" in workflow
        assert "secrets." not in workflow, f"{sdk} workflow accepts release credentials"
        assert "Publish to Maven Central" not in workflow
        assert "Already published?" not in workflow
        assert "Wait for matching Kotlin core on Maven Central" not in workflow

    for sdk in ("kotlin", "android"):
        build = (ROOT / f"sdks/{sdk}/build.gradle.kts").read_text()
        assert "ossrh-staging-api.central.sonatype.com" not in build
        assert "signing {" not in build

    with (ROOT / "sdks/rust/Cargo.toml").open("rb") as handle:
        assert tomllib.load(handle)["package"]["publish"] is False
    assert _matched(ROOT / "sdks/dart/pubspec.yaml", r"^publish_to:\s*([^\s]+)$") == "none"
