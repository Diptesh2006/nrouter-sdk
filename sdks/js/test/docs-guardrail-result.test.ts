// PGSDK-122. `docs/guardrails.md` explains at length how the gateway RESOLVES
// which guardrails run — scope precedence, the disabling assignment, caching —
// and then never tells the reader how to READ the outcome. It mentions neither
// `x-nr-guardrails` nor `meta.guardrails`, and none of the statuses the
// gateway publishes.
//
// The cost of that omission is a specific wrong belief, and the doc actively
// teaches it: "failures refuse; they do not fall through" plus a Billing
// section about blocks reads as a two-state world — blocked is an error,
// anything else means you were protected. Two of the seven statuses mean you
// were NOT protected:
//
//   none    — no guardrail was resolved for this request at all
//   monitor — the chain ran in observe-only mode and COULD NOT have refused
//
// A caller treating either as "pass" believes a policy is enforcing something
// it is not. That is the same class of defect as a fake surface: a control the
// dashboard shows as on, that changes nothing, with no way to tell from the
// response.
//
// docs/audio.md, docs/images.md and docs/video.md all already carry
// the `none | monitor | redacted | pass | partial | blocked` token, so the guardrails doc
// was the one place a reader looking specifically for guardrail semantics would
// land and find the least. Gateway source: preflight.rs documents the
// distinction.

const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const DOC = path.join(__dirname, '..', 'docs', 'guardrails.md');
const STATUSES = ['none', 'monitor', 'redacted', 'pass', 'partial', 'blocked', 'unavailable'];

test('guardrails.md documents where the result is published', () => {
  const doc = fs.readFileSync(DOC, 'utf8');
  assert.ok(
    doc.includes('x-nr-guardrails'),
    'guardrails.md must name the response header the status is read from',
  );
  assert.ok(
    doc.includes('meta.guardrails'),
    'guardrails.md must name the SDK field carrying the status',
  );
});

test('guardrails.md documents all seven statuses', () => {
  const doc = fs.readFileSync(DOC, 'utf8');
  const missing = STATUSES.filter((s) => !new RegExp(`\`${s}\``).test(doc));
  assert.deepEqual(
    missing,
    [],
    `guardrails.md omits status(es): ${missing.join(', ')} — a caller cannot ` +
      'distinguish outcomes it does not know exist',
  );
});

test('guardrails.md calls out monitor and none as NON-protection', () => {
  const doc = fs.readFileSync(DOC, 'utf8');
  // The whole point of the section: it is not enough to LIST the statuses, the
  // doc has to say that two of them mean nothing refused. Folding them into
  // "fine" is the belief this card exists to correct.
  const section = doc.slice(doc.indexOf('meta.guardrails'));
  assert.ok(section.length > 0, 'no meta.guardrails section to check');
  assert.match(
    section,
    /not protection|no protection|did not protect|non-protection|could not (have )?(refuse|block)/i,
    'the doc must state that `monitor` and `none` are not protection, not merely list them',
  );
});

test('the sibling modality docs still carry the same token (the shape being mirrored)', () => {
  // If audio.md ever loses this, the mirror above is copying a dead pattern.
  //
  // Matched as the ONE code span audio.md actually publishes, not as five bare
  // substrings. `audio.includes('pass')` is satisfied by "passes", "bypass" or
  // "password" and `includes('none')` by "none of the" — so the loop this
  // replaces would have gone on passing after the status token was deleted
  // outright, as long as ordinary English survived anywhere in the file. That is
  // the false green: the assertion cannot distinguish the contract from prose.
  // All three modality docs carry the token, and all seven values: a list
  // that drops `unavailable` tells a reader a 503 posture does not exist.
  for (const doc of ['audio.md', 'images.md', 'video.md']) {
    const text = fs.readFileSync(path.join(__dirname, '..', 'docs', doc), 'utf8');
    assert.match(
      text,
      /`none \| monitor \| redacted \| pass \| partial \| blocked \| unavailable`/,
      `docs/${doc} no longer carries the seven-value status token verbatim — the ` +
        'mirror in guardrails.md is then copying a pattern its sibling dropped',
    );
  }
});
