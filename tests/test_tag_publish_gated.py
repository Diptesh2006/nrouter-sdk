"""SDKCI-003 — the tag that PUBLISHES must be the thing that gets tested.

Go and Swift do not publish through a workflow at all. proxy.golang.org and the
Swift Package Index resolve straight from this repo's git tags:

    curl https://proxy.golang.org/github.com/!n!router!a!i/nrouter-sdk/sdks/go/v2/@latest
    -> {"Version":"v2.2.1","Origin":{"VCS":"git","Ref":"refs/tags/sdks/go/v2.2.1",...}}

`Origin.VCS` is `git`, not a CI upload. Their workflows only VERIFY readiness —
publish-go.yml greps the module path and echoes; publish-swift.yml dumps the
package manifest and echoes.

So the publish trigger is `git push --tags`, and before this gate NO workflow in
the repo had a tag trigger at all (`grep -n "tags:" .github/workflows/*.yml`
returned nothing). Every check ran against the main-branch commit that PRECEDED
the tag. That predates the 2026-09-02 Actions billing lock and would have
outlived it, so it is a structural hole, not an outage symptom.

TWO THINGS THIS FILE DELIBERATELY DOES NOT ASSERT, both because a reviewer
proved the first version wrong:

  * That `push:` carries no `paths:` filter. The first version removed the path
    filters and pinned their absence, on the belief that GitHub evaluates them
    for tag pushes. It does not — the workflow-syntax reference states plainly
    "Path filters are not evaluated for pushes of tags." The filters are
    restored; asserting their absence would have encoded a false invariant and
    cost every main push a full lane run for nothing.
  * A shared tag pattern. Go and Swift use DIFFERENT conventions and
    PUBLISHING.md is the source of truth for each (:34 and :33).

This is a text gate on the workflow files by design: the thing under test is
which events GitHub will dispatch on, which no local run can exercise. It parses
the YAML rather than scanning it, because a text scan for `"tags:"` matches a
comment saying `# remember to add tags:`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# The SDKs whose registry resolves from a git tag rather than a CI upload, with
# the tag pattern PUBLISHING.md documents for each. npm/PyPI/Maven are
# deliberately absent: those publish from inside a workflow, so the workflow
# already runs on the thing it is publishing.
#
# Swift is the one that bites. It uses a BARE SemVer tag (`2.2.1`), not an
# `sdks/swift/*` one — `git tag` returns `2.1.0 2.1.1 2.2.1` plus three
# `sdks/go/*` and ZERO swift-namespaced tags, so a namespaced pattern is a
# trigger that fires never. Caught by the gpt-5.6-sol review of this slice.
TAG_PUBLISHED = {
    "go": "sdks/go/v*",
    "swift": "[0-9]+.[0-9]+.[0-9]+",
}


def _on(sdk: str) -> dict:
    path = WORKFLOWS / f"publish-{sdk}.yml"
    assert path.is_file(), f"{path.relative_to(ROOT)} is missing"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML parses the bare key `on` as the boolean True.
    return doc[True] if True in doc else doc["on"]


@pytest.mark.parametrize("sdk", sorted(TAG_PUBLISHED))
def test_tag_published_sdk_workflow_triggers_on_tags(sdk: str) -> None:
    push = _on(sdk)["push"]
    assert "tags" in push, (
        f"publish-{sdk}.yml has no `tags:` trigger, but {sdk} publishes from a git tag. "
        f"Without it, `git push --tags` publishes a tree no workflow ever checked."
    )


@pytest.mark.parametrize("sdk", sorted(TAG_PUBLISHED))
def test_the_tag_pattern_is_the_one_publishing_md_documents(sdk: str) -> None:
    """A trigger that fires on the WRONG tags is not coverage.

    Too narrow and it never fires (an `sdks/swift/v*` pattern against bare
    Swift tags). Too wide and the Go lane runs on a Swift release, reading as
    green coverage of something it never built.
    """
    patterns = _on(sdk)["push"]["tags"]
    assert patterns == [TAG_PUBLISHED[sdk]], (
        f"publish-{sdk}.yml tag patterns are {patterns!r}; PUBLISHING.md documents "
        f"{TAG_PUBLISHED[sdk]!r}. Change both together, or the gate drifts from the "
        f"convention that actually publishes."
    )


@pytest.mark.parametrize("sdk", sorted(TAG_PUBLISHED))
def test_the_main_branch_trigger_survived(sdk: str) -> None:
    """The duplicate-key trap, and it is silent.

    `tags:` must be a key inside the existing `push:` mapping. Written as a
    second `push:` block the YAML still parses and the last one wins, so
    `branches: [main]` disappears and every main-branch check stops running —
    measured while writing this change.
    """
    push = _on(sdk)["push"]
    assert push.get("branches") == ["main"], (
        f"publish-{sdk}.yml lost its `branches: [main]` push trigger — the signature "
        f"of a second `push:` block overwriting the first."
    )
