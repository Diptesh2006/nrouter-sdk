#!/usr/bin/env python3
"""Refuse a HARD-CODED response-header count in customer-facing prose.

SDKDOC-001. Seven documents said the gateway emits "fourteen" `x-nr-*` headers.
`ef1805845` shipped `x-nr-guardrails` and made it fifteen, and every one of
those sentences went wrong at once — on the only PUBLIC repo in the workspace.

The defect is not the number. It is that a DERIVED quantity was restated as
prose. The list comes from the gateway's `nr_headers::all_emitted_names()` and
moves whenever a header ships, so any snapshot of it is guaranteed to rot; the
same reactive-staleness pattern as STALEGUARD-001 and as the cron registry
count, which this workspace has now restated wrongly four times.

So this gate does not check that the number is RIGHT — that would just be the
same snapshot one layer down, and it would go green the day someone updates the
prose and stale again the day after. It refuses the number's PRESENCE. The
machine-readable side is already correct and already gated:

  * `spec/gateway-response-headers.json` carries the list and names its source,
  * `conformance/check_conformance.py` enforces list-entry-plus-parse-site per
    SDK,
  * `tests/test_sdk_contract.py` asserts spec parity against the derived list.

Prose that restates a gated, derived number adds nothing it can be trusted for.
Say "every" / "all" / "the full set", or point at the JSON.

    python3 conformance/doc_header_count.py             # check
    python3 conformance/doc_header_count.py --self-test # prove the gate bites
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Customer-facing prose plus the two checker docstrings that shipped the same
# sentence. SDK *source* is out of scope: `check_conformance.py` holds that to
# the spec, and a count in a code comment reaches no customer.
DOC_FILES = (
    "README.md",
    "LANGUAGES.md",
    "CLAUDE.md",
    "conformance/README.md",
    "conformance/check_conformance.py",
)
DOC_GLOBS = ("sdks/*/README.md", "sdks/*/docs/**/*.md")
SKIP_PARTS = {"node_modules", ".git", "target", "build", "dist", ".dart_tool"}

_NUMBER = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
)
# A number that QUALIFIES the header set: the count, then within a short span
# the `x-nr-` marker and the word "header". Bounded to one line so a count in an
# unrelated sentence two paragraphs away cannot be swept in.
#
# The `|` exclusion is load-bearing, not tidiness. Without it this fired on
# `sdks/js/docs/test-coverage-and-issues.md`, whose table row
# `| meta.test.ts | 16 | All \`x-nr-*\` response headers, ... |` counts TESTS,
# not headers. A gate that fires on correct text is the TENANCY-002 failure
# shape — it trains people to ignore it — so a cell boundary ends the span.
# The comma exclusion is the second half of the same lesson. Without it this
# fired on `LANGUAGES.md`'s "the gateway's nine codes, and every x-nr-* header"
# — where `nine` counts ERROR CODES and the header clause is already honest.
# A comma or a `|` ends the clause, so a count belonging to a different noun
# cannot be dragged across into this one.
#
# BOTH ORDERS. The first pattern is the shape that actually shipped ("all
# fourteen `x-nr-*` headers"). The second is its mirror — "the `x-nr-*` headers
# total 15", "x-nr-* headers: 15 of them" — which reads just as naturally and
# which the first pattern cannot see, since it requires the number FIRST. A
# gate that refuses the count's PRESENCE has to refuse it in the order a person
# would actually write it, not only in the order the last defect used.
COUNT_BEFORE_RE = re.compile(
    rf"\b{_NUMBER}\b[^\n|,]{{0,40}}?`?x-nr-[^\n|,]{{0,40}}?header",
    re.IGNORECASE,
)
# The mirror's gap is TEMPERED, not merely bounded. A comma alone is not enough
# here: "every `x-nr-*` header and nine typed gateway errors" has no comma, and
# the `nine` belongs to the ERRORS. A conjunction starts a new noun phrase, so
# it ends the span the same way a comma or a cell boundary does. Caught by
# running this pattern against the corpus it was written for — it went red on
# four honest lines before the temper was added.
# The mirror's gap ALLOWS a comma, unlike the forward one, because a comma is a
# normal separator inside this shape — "the `x-nr-*` headers, 15 in total" is
# the defect, not an unrelated clause. Two narrower tempers do the work the
# comma did in the forward pattern, and they are more precise than it was:
#
#   * a CONJUNCTION ends the span, because it starts a new noun phrase. That is
#     what "every `x-nr-*` header and nine typed gateway errors" is — the `nine`
#     counts the ERRORS, and this pattern went red on four honest lines before
#     the temper was added.
#   * the number must not be immediately followed by a NAMED other noun, so
#     "the `x-nr-*` headers, the nine error codes" stays clean too.
_OTHER_NOUN = r"(?:error|code|operation|wire|endpoint|sdk|test|language|route)"
COUNT_AFTER_RE = re.compile(
    rf"`?x-nr-[^\n|,]{{0,40}}?headers?\b"
    rf"(?:(?!\b(?:and|or|plus)\b)[^\n|]){{0,30}}?\b{_NUMBER}\b"
    rf"(?!\s+{_OTHER_NOUN})",
    re.IGNORECASE,
)
PATTERNS = (COUNT_BEFORE_RE, COUNT_AFTER_RE)


def corpus(root: Path) -> list[Path]:
    seen: list[Path] = []
    for rel in DOC_FILES:
        p = root / rel
        if p.is_file():
            seen.append(p)
    for pattern in DOC_GLOBS:
        for p in sorted(root.glob(pattern)):
            if p.is_file() and not (SKIP_PARTS & set(p.parts)):
                seen.append(p)
    return seen


def check_doc_header_count(root: Path = ROOT) -> list[str]:
    """Return failure strings; empty means no prose restates the header count."""
    failures: list[str] = []
    for path in corpus(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = next(
                (m for m in (p.search(line) for p in PATTERNS) if m),
                None,
            )
            if match:
                failures.append(
                    f"{path.relative_to(root)}:{lineno}: prose states a hard-coded "
                    f"`x-nr-*` header COUNT ({match.group(0)!r}). The set is derived "
                    f"from the gateway's nr_headers::all_emitted_names() and rots on "
                    f"the next header. Say 'every'/'all', or cite "
                    f"spec/gateway-response-headers.json."
                )
    return failures


def self_test(root: Path = ROOT) -> int:
    """Prove the gate bites, and that it does not fire on the honest wording."""
    import tempfile

    fails = 0

    def case(name: str, body: str, expect_hit: bool) -> None:
        nonlocal fails
        with tempfile.TemporaryDirectory() as d:
            box = Path(d)
            (box / "README.md").write_text(body, encoding="utf-8")
            hits = check_doc_header_count(box)
            got = bool(hits)
            if got != expect_hit:
                print(f"  FAIL {name}: expected hit={expect_hit}, got {hits}")
                fails += 1
            else:
                print(f"  ok   {name}")

    # The exact sentences SDKDOC-001 found, in the spellings that shipped.
    case("spelled count", "carries all fourteen `x-nr-*` headers: `requestId`,", True)
    case("digit count", "Response.Meta carries all 15 x-nr-* headers.", True)
    # The number that REPLACED it must not fire again the next time a header ships.
    case("honest wording", "`ResponseMeta` carries every `x-nr-*` header the gateway emits.", False)
    # An unrelated count on the same line must not be swept in.
    case("unrelated count", "nine error codes are classified by the dispatch table.", False)
    # A count of something else that merely mentions headers stays clean.
    case("other noun", "all 15 gateway operations are covered.", False)
    # REGRESSION (real false positive this gate shipped with): a markdown table
    # whose own cell holds a TEST count next to a cell describing headers.
    case(
        "table cell test count",
        "| `meta.test.ts` | 16 | All `x-nr-*` response headers, billing metadata. |",
        False,
    )
    # REGRESSION (the second real false positive): a count belonging to a
    # DIFFERENT noun earlier in the same sentence, with the header clause
    # already using the honest wording.
    case(
        "count of another noun in the same sentence",
        "// Typed errors from the gateway's nine codes, and every x-nr-* header.",
        False,
    )
    # The MIRROR order, which the first pattern alone could not see (found by
    # the gpt-5.6-sol review of this very slice).
    case("count AFTER the marker", "The `x-nr-*` headers total 15.", True)
    case("count after, spelled", "x-nr-* headers: fifteen of them.", True)
    # REGRESSION (the third real false positive, and the reason for the temper):
    # a count after the marker that belongs to a DIFFERENT noun across a
    # conjunction, with the header clause already honest.
    # The comma-separated mirror, which the first temper wrongly blocked. Found
    # by mutation-checking the gate through check_conformance.py rather than by
    # reading it: the mutant "carries the `x-nr-*` headers, 15 in total" came
    # back rc=0, i.e. the gate did not bite on a real defect.
    case("count after, comma-separated", "carries the `x-nr-*` headers, 15 in total.", True)
    # ...and the noun temper keeps that permissiveness from costing a false hit.
    case(
        "count after a comma, but belonging to another noun",
        "carries the `x-nr-*` headers, the nine error codes, and typed errors.",
        False,
    )
    case(
        "count after, across a conjunction, other noun",
        "It hands back every `x-nr-*` header and types the gateway's nine error codes.",
        False,
    )
    # The mirror must not fire on the honest wording either.
    case(
        "honest wording, reversed shape",
        "The `x-nr-*` headers are listed in spec/gateway-response-headers.json.",
        False,
    )
    # ...but the dishonest form must still be caught in that same shape.
    case(
        "count of another noun, header count still hard-coded",
        "Typed errors from nine codes and all fourteen `x-nr-*` headers.",
        True,
    )
    return 1 if fails else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    problems = check_doc_header_count()
    for p in problems:
        print(f"FAIL {p}")
    print(
        f"doc header count: {len(problems)} hard-coded count(s) in prose"
        if problems
        else "doc header count: no prose restates the derived x-nr-* header count"
    )
    raise SystemExit(1 if problems else 0)
