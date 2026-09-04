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


# ---------------------------------------------------------------------------
# SDKENUM-001 — the SAME staleness, one level harder: a COMPLETENESS PROMISE
# followed by an ENUMERATION.
# ---------------------------------------------------------------------------
#
# The count gate above refuses "all fourteen `x-nr-*` headers". `5f05390`
# obeyed it by writing "every `x-nr-*` header:" — and left the fourteen-item
# list standing underneath. That is STRICTLY WORSE than the count it replaced:
# "fourteen" was wrong but self-consistent, while "every" over a list of
# fourteen is an exhaustiveness claim a customer will act on, on the only
# PUBLIC repo in the workspace. `94d608c` repaired those five documents by
# hand; nothing stopped the sixth, and there WAS a sixth — `sdks/kotlin`'s
# table omitted `x-nr-guardrails` while `ResponseMeta.kt:44` exposed it.
#
# THIS GATE NEVER COMPARES HEADER NAMES, and that is the whole design.
# A first implementation did, and mis-fired two ways:
#
#   1. the Go README separates its promise from its table by a blank line and
#      an intervening sentence, so a same-paragraph window saw an empty list
#      and reported every header missing;
#   2. every SDK spells the fields its own way — `x-nr-request-cost` is `cost`
#      in dart/rust/r/swift and `Cost` in go — so a suffix match reported
#      headers missing from lists that DID contain them.
#
# Both are legitimate text. A gate that fires on correct text trains people to
# ignore it, which is the failure this repo already carries a card for. So the
# gate refuses the SHAPE instead: a completeness promise about the `x-nr-*` set
# with an enumeration under it. The shape is decidable from the document alone,
# so neither spelling nor layout can make it wrong.
#
# Either half may go, and the choice is editorial:
#
#   * a list that only restates field names carries nothing the naming rule and
#     `spec/gateway-response-headers.json` do not -> DROP THE LIST, keep the
#     promise. The promise is not a snapshot: `check_conformance.py` holds every
#     SDK to the derived header set, so "every" is machine-checked;
#   * a table that carries per-header SEMANTICS (what nil means, which status
#     narrows an error) is real documentation -> KEEP THE TABLE, drop the
#     completeness claim and cite the spec as authoritative. It then documents
#     what it documents and cannot rot into a lie when header sixteen ships.

# A quantifier that GOVERNS the header set. It must appear BEFORE the `x-nr-`
# marker: "every `x-nr-*` header" is a claim about the set, while "`x-nr-*`
# headers with every response" is a claim about frequency and is honest.
# "the following" is deliberately ABSENT and its absence is the rule, not an
# oversight. It is a DEICTIC pointer -- "these ones" -- not a quantifier over
# the set, so "The following `x-nr-*` headers are relevant to billing:" over a
# two-row table is honest PARTIAL documentation and refusing it is the
# false-positive failure this gate exists to avoid. "only the following" stays,
# because "only" is the quantifier that turns the pointer into a closed set.
_COMPLETENESS = (
    r"(?:every|all|each|only the following|the full set of|"
    r"the complete set of|the entire set of|exhaustive|complete list of)"
)
# The `|` exclusion is inherited from the count patterns above and for the same
# reason: a markdown cell boundary ends the clause, so a quantifier in one cell
# cannot be dragged into the next one's header noun.
PROMISE_RE = re.compile(
    rf"\b{_COMPLETENESS}\b[^|]{{0,45}}?x-nr-[^|]{{0,45}}?\b(?:headers?|metadata|fields?)\b",
    re.IGNORECASE,
)
_BACKTICKED = re.compile(r"`[^`\n]+`")
# An ORDERED list enumerates exactly as a bulleted one does. Recognising only
# `-*+` let a numbered list walk past the gate, and "the headers are:" over
# `1.` `2.` `3.` is exactly the shape an author reaches for.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)])\s")
_FENCE = re.compile(r"^\s*(```|~~~)")
# A SETEXT heading bounds a section exactly as an ATX `#` one does. Without it a
# promise in the section above keeps scanning into the section below, widening
# the window past the author's intent -- a false-positive source.
_SETEXT = re.compile(r"^\s*(?:={2,}|-{2,})\s*$")
# `x-nr-` appearing IN a block is what makes that block self-evidently about the
# header set. This is a relatedness test, never a NAME comparison: it never asks
# which headers are listed, only whether the block is talking about them at all.
_XNR = re.compile(r"x-nr-", re.IGNORECASE)


def _is_table_delim(line: str) -> bool:
    """A markdown table's separator row, piped or pipe-less.

    Requires a `|`, so a `---` horizontal rule and a setext underline are not
    mistaken for one. This is what makes a PIPE-LESS table (`Field | Header`
    over `--- | ---`) detectable: the delimiter row, not a leading `|`, is what
    actually distinguishes a table from a paragraph in GFM.
    """
    stripped = line.strip()
    return "|" in stripped and "-" in stripped and set(stripped) <= set("|-: \t")


def _blocks(text: str) -> list[tuple[str, int, list[str]]]:
    """Split a document into (kind, first_lineno, lines) blocks.

    Blank lines are separators and are dropped. The kinds that matter are
    `heading` (ATX `#` or SETEXT underline -- either bounds a promise's
    section, and either can itself CARRY the promise), `table` (piped or
    pipe-less) and `list` (bulleted or numbered) -- either of which can BE the
    enumeration -- `fence` (skipped over -- Kotlin puts a code example between
    its promise and its table, so a fence must not end the scan) and `para`.
    """
    lines = text.splitlines()
    out: list[tuple[str, int, list[str]]] = []
    i, n = 0, len(lines)

    def starts_table(k: int) -> bool:
        return (
            lines[k].strip().startswith("|")
            or (k + 1 < n and "|" in lines[k] and _is_table_delim(lines[k + 1]))
        )

    def starts_setext(k: int) -> bool:
        # The underline alone is not a heading; it needs the text line above it,
        # and that text line must not itself be a table row or a fence.
        return (
            k + 1 < n
            and _SETEXT.match(lines[k + 1]) is not None
            and not _is_table_delim(lines[k + 1])
            and bool(lines[k].strip())
        )

    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if _FENCE.match(lines[i]):
            marker = stripped[:3]
            j = i + 1
            while j < n and not lines[j].strip().startswith(marker):
                j += 1
            out.append(("fence", i + 1, lines[i : min(j + 1, n)]))
            i = j + 1
            continue
        if stripped.startswith("#"):
            out.append(("heading", i + 1, [lines[i]]))
            i += 1
            continue
        # Table BEFORE setext: `--- | ---` is a delimiter row, not an underline.
        if starts_table(i):
            j = i
            while j < n and lines[j].strip() and "|" in lines[j]:
                j += 1
            out.append(("table", i + 1, lines[i:j]))
            i = j
            continue
        if starts_setext(i):
            out.append(("heading", i + 1, [lines[i], lines[i + 1]]))
            i += 2
            continue
        kind = "list" if _LIST_ITEM.match(lines[i]) else "para"
        j = i + 1
        while j < n:
            nxt = lines[j]
            if not nxt.strip() or nxt.strip().startswith("#") or _FENCE.match(nxt):
                break
            if starts_table(j) or starts_setext(j):
                break
            if kind == "para" and _LIST_ITEM.match(nxt):
                break
            j += 1
        out.append((kind, i + 1, lines[i:j]))
        i = j
    return out


def _is_enumeration(kind: str, lines: list[str]) -> bool:
    """A table, or a bullet list of three or more backticked items."""
    if kind == "table":
        # A one-row table is a shape, not a list. Header + separator + a row.
        return len(lines) >= 3
    if kind == "list":
        items = [ln for ln in lines if _LIST_ITEM.match(ln) and "`" in ln]
        return len(items) >= 3
    return False


def _inline_enumeration(tail: str) -> int:
    """Items in an inline list the promise INTRODUCES, else 0.

    The promise must hand off with a colon within a short span, and only the
    clause up to the first sentence end counts. Reading to the end of the block
    instead made "carries every `x-nr-*` header the gateway emits. See
    `docs/cost.md`, `docs/errors.md`, and `docs/routing.md`." look like an
    inline enumeration of headers -- honest prose, refused.

    Three items is the floor: two is a pair, not a list, and `CLAUDE.md`'s
    "`sk-nrouter-` prefix, every `x-nr-*` header and nine error codes" must
    stay clean.
    """
    intro = re.match(r"[^:.\n]{0,40}:\s*(.*)$", tail, re.S)
    if not intro:
        return 0
    clause = intro.group(1)
    stop = re.search(r"\.(?=\s|$)", clause)
    if stop:
        clause = clause[: stop.start()]
    items = _BACKTICKED.findall(clause)
    return len(items) if len(items) >= 3 and clause.count("`,") >= 2 else 0


def check_doc_header_enumeration(root: Path = ROOT) -> list[str]:
    """Return failure strings; empty means no completeness promise is enumerated."""
    failures: list[str] = []
    for path in corpus(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        blocks = _blocks(text)
        for idx, (kind, lineno, lines) in enumerate(blocks):
            # A HEADING carries a promise as readily as a paragraph does --
            # "## All `x-nr-*` headers" over a table is the exact stale
            # exhaustive-list shape, in the most natural place to write one.
            if kind not in ("para", "list", "heading"):
                continue
            # Join the block's lines: markdown hard-wraps, and the Dart/Rust/R
            # promises run their list across three physical lines.
            joined = " ".join(ln.strip() for ln in lines)
            match = PROMISE_RE.search(joined)
            if not match:
                continue

            where = ""
            inline = _inline_enumeration(joined[match.end() :])
            # (a) the enumeration is INLINE, in the same clause the promise
            #     introduces: `... every x-nr-* header: `a`, `b`, `c``.
            if inline:
                where = f"an inline list of {inline} items"
            else:
                # (b) the enumeration is a TABLE or LIST later in the same
                #     section. Bounded by the next heading, so a plans table two
                #     sections down is not dragged in; fences are stepped over,
                #     never treated as a boundary.
                #
                #     RELATEDNESS, not name matching. The gate still never asks
                #     WHICH headers a block lists -- only whether that block is
                #     the promise's enumeration at all. A block qualifies when:
                #
                #       * it mentions `x-nr-` itself, so it is self-evidently
                #         about the header set however its fields are spelled;
                #       * or the promise INTRODUCES it -- the promise block ends
                #         in a colon and nothing but a fence stands between --
                #         which is how the Go and bullet-list shapes read even
                #         though their rows use each SDK's own spelling;
                #       * or the promise is the section HEADING, which scopes the
                #         whole section to the header set.
                #
                #     Without this, ANY later table in the section was assumed to
                #     be the enumeration, so a retry-options table under an
                #     honest sentence failed the build. A gate that fires on
                #     correct writing is the one that gets switched off.
                introduces = joined.rstrip().endswith(":")
                intervening = False
                for nkind, nline, nlines in blocks[idx + 1 :]:
                    if nkind == "heading":
                        break
                    if nkind == "fence":
                        continue
                    is_enum = _is_enumeration(nkind, nlines)
                    if is_enum and (
                        any(_XNR.search(ln) for ln in nlines)
                        or kind == "heading"
                        or (introduces and not intervening)
                    ):
                        where = f"the {nkind} at line {nline}"
                        break
                    # Anything else -- prose, or an enumeration ruled unrelated
                    # -- separates the promise from whatever follows it.
                    intervening = True
            if not where:
                continue
            failures.append(
                f"{path.relative_to(root)}:{lineno}: a COMPLETENESS PROMISE about the "
                f"`x-nr-*` set ({match.group(0).strip()!r}) is followed by {where}. "
                f"The set is derived from the gateway's nr_headers::all_emitted_names() "
                f"and grows, so the enumeration rots and the promise turns it into a "
                f"false exhaustiveness claim. Either drop the enumeration and cite "
                f"spec/gateway-response-headers.json, or keep it and drop the "
                f"completeness claim."
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

    # ---- SDKENUM-001: a completeness PROMISE followed by an ENUMERATION ----
    def ecase(name: str, body: str, expect_hit: bool) -> None:
        nonlocal fails
        with tempfile.TemporaryDirectory() as d:
            box = Path(d)
            (box / "README.md").write_text(body, encoding="utf-8")
            hits = check_doc_header_enumeration(box)
            got = bool(hits)
            if got != expect_hit:
                print(f"  FAIL {name}: expected hit={expect_hit}, got {hits}")
                fails += 1
            else:
                print(f"  ok   {name}")

    # The exact shape 5f05390 shipped into five READMEs: "every" over a list.
    ecase(
        "promise then inline list",
        "`ResponseMeta` carries every `x-nr-*` header: `request_id`, `cost`,\n"
        "`cost_status`, `model`, `input_tokens`, `output_tokens`.\n",
        True,
    )
    # REVERT CASE 1 — the Go shape. The promise is separated from its table by a
    # BLANK LINE and an intervening sentence, so a same-paragraph window sees an
    # empty list and the first implementation reported every header missing.
    ecase(
        "promise, blank line, then a table (the Go shape)",
        "## Response metadata\n\n"
        "`Response.Meta` carries every `x-nr-*` header. Every numeric field is a\n"
        "pointer, deliberately:\n\n"
        "| Field | Header | Nil means |\n"
        "|---|---|---|\n"
        "| `RequestID` | `x-nr-request-id` | - |\n"
        "| `Cost` | `x-nr-request-cost` | **unpriced, not free** |\n",
        True,
    )
    # REVERT CASE 2 — SDK-SPECIFIC SPELLINGS. `x-nr-request-cost` is `cost` here
    # and `Cost` in Go, so any name/suffix match reports it missing from a list
    # that does contain it. This gate never compares names, so the spelling is
    # irrelevant and the promise+enumeration shape still fires.
    ecase(
        "promise then a list in the SDK's own field spelling",
        "`NRouterResponseMeta` carries every `x-nr-*` header: `requestId`,\n"
        "`cost`, `costStatus`, `model`, `inputTokens`.\n",
        True,
    )
    # The Kotlin shape: promise, a fenced example, THEN the table. The fence must
    # not end the scan, or the sixth document stays invisible.
    ecase(
        "promise, fenced example, then a table",
        "## What a call cost\n\n"
        "Every response carries the gateway's `x-nr-*` metadata:\n\n"
        "```kotlin\nval meta = result.meta\n```\n\n"
        "| Property | Header | Meaning |\n"
        "|---|---|---|\n"
        "| `requestId` | `x-nr-request-id` | Always present |\n",
        True,
    )
    # The "only the following" spelling, which is a completeness claim without
    # the word "every".
    ecase(
        "only-the-following then a table",
        "## Response Headers\n\n"
        "The gateway emits only the following public `x-nr-*` response headers.\n\n"
        "| Header | Type |\n|---|---|\n| `x-nr-request-id` | string |\n",
        True,
    )
    # A bulleted enumeration is the same claim in another shape.
    ecase(
        "promise then a bullet list",
        "It exposes all `x-nr-*` headers:\n\n"
        "- `request_id` - the id\n- `cost` - USD\n- `model` - the model\n",
        True,
    )
    # ---- and the honest wordings, which must stay clean --------------------
    # The remedy for an inline list: keep the gated promise, drop the list.
    ecase(
        "promise with no enumeration at all",
        "`ResponseMeta` carries every `x-nr-*` header the gateway emits; the\n"
        "authoritative set is spec/gateway-response-headers.json.\n",
        False,
    )
    # The remedy for a table worth keeping: drop the completeness claim.
    ecase(
        "table with no completeness promise",
        "## Response metadata\n\n"
        "`Response.Meta` exposes the gateway's `x-nr-*` headers as typed fields.\n\n"
        "| Field | Header |\n|---|---|\n| `Cost` | `x-nr-request-cost` |\n",
        False,
    )
    # A quantifier that governs RESPONSES, not the header set, with no list.
    ecase(
        "quantifier after the marker",
        "The gateway emits canonical `x-nr-*` headers with every response.\n",
        False,
    )
    # The prose that says the conformance gate covers every header. It is a
    # gated, true claim and it enumerates nothing.
    ecase(
        "gate prose naming other contract items",
        "It asserts every SDK's source encodes the same base URL, environment\n"
        "variable, key prefix, every `x-nr-*` header and nine error codes.\n",
        False,
    )
    # A table in a DIFFERENT section than the promise is not its enumeration.
    ecase(
        "promise, then a heading, then an unrelated table",
        "## Contract\n\nThe gate covers every `x-nr-*` header.\n\n"
        "## Plans\n\n| Plan | Fee |\n|---|---|\n| Tier 1 | 4% |\n",
        False,
    )

    # ---- SDKENUM-001 review round 2 ---------------------------------------
    # gpt-5.6-sol [HIGH]: a promise written as a HEADING was never examined,
    # which is the most natural place an author puts one.
    ecase(
        "heading promise then a table",
        "## All `x-nr-*` headers\n\n"
        "| Field | Header |\n|---|---|\n"
        "| `requestId` | `x-nr-request-id` |\n| `cost` | `x-nr-request-cost` |\n",
        True,
    )
    # gpt-5.6-sol [MEDIUM]: a pipe-less markdown table is a valid table and was
    # invisible, so the enumeration under a promise went unseen.
    ecase(
        "promise then a pipe-less table",
        "`Response.Meta` carries every `x-nr-*` header:\n\n"
        "Field | Header | Nil means\n"
        "----- | ------ | ---------\n"
        "`RequestID` | `x-nr-request-id` | -\n"
        "`Cost` | `x-nr-request-cost` | unpriced\n",
        True,
    )
    # gpt-5.6-sol [MEDIUM]: an ORDERED list enumerates exactly as a bulleted one
    # does, and only `-*+` were recognised.
    ecase(
        "promise then a numbered list",
        "It exposes all `x-nr-*` headers:\n\n"
        "1. `request_id` - the id\n2. `cost` - USD\n3. `model` - the model\n",
        True,
    )
    # gpt-5.6-sol [MEDIUM], the FALSE-POSITIVE direction: an unrelated table
    # later in the same section is not the promise's enumeration. Honest
    # documentation must stay quiet, or the gate gets switched off.
    ecase(
        "promise, intervening prose, then an UNRELATED table",
        "## Response metadata\n\n"
        "`Response.Meta` carries every `x-nr-*` header the gateway emits; the\n"
        "authoritative set is spec/gateway-response-headers.json.\n\n"
        "Retries are configured separately.\n\n"
        "| Option | Default |\n|---|---|\n| `maxRetries` | `2` |\n| `timeout` | `60s` |\n",
        False,
    )
    # claude-opus-4-6-thinking [MEDIUM]: "the following" SELECTS, it does not
    # quantify. An explicitly partial table is honest partial documentation.
    ecase(
        "'the following' over an honest subset",
        "## Billing\n\n"
        "The following `x-nr-*` headers are relevant to billing:\n\n"
        "| Header | Meaning |\n|---|---|\n"
        "| `x-nr-request-cost` | USD, absent when unpriced |\n"
        "| `x-nr-cost-status` | `exact` or `unpriced` |\n",
        False,
    )
    # claude-opus-4-6-thinking [LOW]: a setext heading bounds a section exactly
    # as an ATX one does.
    ecase(
        "promise, setext heading, then an unrelated table",
        "The gate covers every `x-nr-*` header.\n\n"
        "Plans\n-----\n\n"
        "| Plan | Fee |\n|---|---|\n| Tier 1 | 4% |\n",
        False,
    )
    # claude-opus-4-6-thinking [LOW]: the inline heuristic read to the end of
    # the block, so trailing prose citing three files looked like an inline
    # enumeration of headers.
    ecase(
        "promise then trailing prose naming other backticked things",
        "`ResponseMeta` carries every `x-nr-*` header the gateway emits. See\n"
        "`docs/cost.md`, `docs/errors.md`, and `docs/routing.md` for details.\n",
        False,
    )

    return 1 if fails else 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(self_test())
    counts = check_doc_header_count()
    enums = check_doc_header_enumeration()
    problems = counts + enums
    for item in problems:
        print(f"FAIL {item}")
    print(
        f"doc header set: {len(counts)} hard-coded count(s) and "
        f"{len(enums)} enumerated completeness promise(s) in prose"
        if problems
        else "doc header set: no prose restates or enumerates the derived "
        "x-nr-* header set"
    )
    raise SystemExit(1 if problems else 0)
