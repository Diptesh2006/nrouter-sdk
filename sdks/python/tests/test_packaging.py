"""The manifest is load-bearing and has broken before.

- The distribution name (`nrouter-sdk`) differs from the import package
  (`nroutersdk`), so `[tool.hatch.build.targets.wheel] packages` is REQUIRED —
  without it the wheel builds with no package in it at all.
- `requires-python` must not promise an interpreter the dependency tree cannot
  satisfy. openai 3.x requires >=3.10; promising 3.8 made pip resolve openai
  silently backwards instead of refusing.
"""

from __future__ import annotations

import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

MANIFEST = pathlib.Path(__file__).resolve().parent.parent / "pyproject.toml"


def manifest() -> dict:
    return tomllib.loads(MANIFEST.read_text())


def test_the_wheel_names_the_import_package_explicitly():
    assert manifest()["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["nroutersdk"]


def test_the_python_floor_is_at_least_what_openai_requires():
    assert manifest()["project"]["requires-python"] == ">=3.10"


def test_no_classifier_promises_an_unsupported_interpreter():
    classifiers = manifest()["project"]["classifiers"]
    for retired in ("3.8", "3.9"):
        assert f"Programming Language :: Python :: {retired}" not in classifiers


def test_every_dependency_is_bounded_above():
    """An unbounded floor is how this client ended up running against an
    untested openai major."""
    for spec in manifest()["project"]["dependencies"]:
        assert "<" in spec, f"{spec} has no upper bound"


def test_the_version_matches_the_package():
    from nroutersdk import __version__

    assert manifest()["project"]["version"] == __version__
