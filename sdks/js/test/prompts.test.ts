// Managed prompts — the ergonomics layer over the two prompt wire fields.
//
// Every case below pins a behaviour where the "obvious simplification" is a
// silent behaviour change rather than a visible failure. The gateway is the
// oracle for all of them (`http/prompt_runtime.rs`), not this SDK's taste:
//
//   * `take_controls` removes `nrouter_prompt_template_id` and
//     `nrouter_prompt_variables` from the body INDEPENDENTLY, so variables
//     without a template id are meaningful — they render the key/team/org
//     prompt ASSIGNMENT. Dropping them client-side breaks the common case.
//   * `variables.extend(caller_variables)` merges the caller's map OVER the
//     assignment's, so caller precedence is the wire's rule, not ours.
//   * four system variables — org_name, model, timestamp, user_id — are
//     inserted LAST, so a caller variable of the same name never reaches the
//     template. Silently. That is what `systemVariableConflicts` reports.

const { test } = require('node:test');
const assert = require('node:assert/strict');

const {
  PROMPT_TEMPLATE_ID_FIELD,
  PROMPT_VARIABLES_FIELD,
  PROMPT_WIRE_FIELDS,
  SYSTEM_VARIABLE_NAMES,
  promptTemplate,
  promptVariables,
  withVariables,
  promptExtraBody,
  applyPrompt,
  systemVariableConflicts,
} = require('../dist/prompts');

const { buildExtraBody } = require('../dist/options');
const { nRouterConfigurationError } = require('../dist/errors');

const TEMPLATE = '11111111-1111-1111-1111-111111111111';

// ---------------------------------------------------------------------------
// The field names are the contract
// ---------------------------------------------------------------------------

test('the two wire field names are exactly what the gateway removes from the body', () => {
  assert.equal(PROMPT_TEMPLATE_ID_FIELD, 'nrouter_prompt_template_id');
  assert.equal(PROMPT_VARIABLES_FIELD, 'nrouter_prompt_variables');
  assert.deepEqual([...PROMPT_WIRE_FIELDS], [
    'nrouter_prompt_template_id',
    'nrouter_prompt_variables',
  ]);
});

test('this module INVENTS no wire field — every name it emits is one options.ts already emits', () => {
  // The extra_body set is CLOSED (spec extra_body_fields). A field invented
  // here would not be an error a caller ever sees: the gateway forwards what
  // it does not recognise to the provider, so it is a dead option that looks
  // live. Pin it against the one function that owns the mapping.
  const mine = Object.keys(
    promptExtraBody({ templateId: TEMPLATE, variables: { tone: 'terse' } })
  );
  const theirs = Object.keys(
    buildExtraBody({ promptTemplateId: TEMPLATE, promptVariables: { tone: 'terse' } })
  );
  assert.deepEqual(mine.sort(), theirs.sort());
});

// ---------------------------------------------------------------------------
// promptTemplate / promptVariables
// ---------------------------------------------------------------------------

test('promptTemplate names a template and carries its variables', () => {
  assert.deepEqual(promptTemplate(TEMPLATE, { tone: 'terse' }), {
    templateId: TEMPLATE,
    variables: { tone: 'terse' },
  });
});

test('promptTemplate with no variables omits the key rather than sending an empty map', () => {
  assert.deepEqual(promptTemplate(TEMPLATE), { templateId: TEMPLATE });
});

test('an EMPTY template id THROWS rather than silently switching to the assignment lane', () => {
  // This is the case worth a client-side refusal. `buildExtraBody` tests the
  // id for truthiness, so `''` is dropped from the body — and a body carrying
  // variables and NO template id is not an error at the gateway, it resolves
  // the org/team/key ASSIGNMENT instead. So an uninitialised id does not fail:
  // it quietly runs a DIFFERENT prompt. Refusing here is the only place that
  // difference is still visible.
  assert.throws(() => promptTemplate(''), nRouterConfigurationError);
  assert.throws(() => promptTemplate('   '), nRouterConfigurationError);
});

test('the refusal is a CONFIGURATION error and its message echoes no credential', () => {
  // `assert.fail` throws too, so the instanceof check is what makes this case
  // die when the refusal is removed — without it the catch block swallows the
  // assertion failure and the test passes against a guard that no longer runs.
  try {
    promptTemplate('');
    assert.fail('expected a refusal');
  } catch (err) {
    assert.ok(err instanceof nRouterConfigurationError, 'a removed refusal must not read as a pass');
    // Configuration kind: permanent, never retried. A caller's generic
    // `if (isRetryable(e)) retry` loop must not spin on a caller-side mistake.
    assert.equal(err.kind, 'configuration');
    assert.equal(/sk-/.test(err.message), false);
  }
});

test('a selection does NOT alias the variables map it was built from', () => {
  // A caller who reuses one mutable bag across requests — the ordinary shape
  // of a per-request context object — would otherwise see every earlier
  // selection change under them, long after the call that built it.
  const vars = { tone: 'terse' };
  const fromVariables = promptVariables(vars);
  const fromTemplate = promptTemplate(TEMPLATE, vars);
  vars.tone = 'warm';
  vars.leaked = 'yes';
  assert.deepEqual(fromVariables.variables, { tone: 'terse' });
  assert.deepEqual(fromTemplate.variables, { tone: 'terse' });
});

test('promptVariables alone is a supported selection, not an error', () => {
  assert.deepEqual(promptVariables({ tone: 'terse' }), { variables: { tone: 'terse' } });
});

// ---------------------------------------------------------------------------
// promptExtraBody — the mapping, delegated to the one owner of the wire shape
// ---------------------------------------------------------------------------

test('a template id alone maps to the template field only', () => {
  assert.deepEqual(promptExtraBody({ templateId: TEMPLATE }), {
    nrouter_prompt_template_id: TEMPLATE,
  });
});

test('VARIABLES ALONE ARE SENT — they render the org/team/key assignment', () => {
  // The regression this pins: "variables are only meaningful with a template
  // id, so drop them otherwise". `prompt_runtime.rs` takes the two fields off
  // the body independently and merges the caller's map in BOTH branches, so
  // dropping them here breaks every org-assigned-template caller.
  assert.deepEqual(promptExtraBody({ variables: { tone: 'terse' } }), {
    nrouter_prompt_variables: { tone: 'terse' },
  });
});

test('an empty variables map is OMITTED, not sent as {}', () => {
  assert.deepEqual(promptExtraBody({ templateId: TEMPLATE, variables: {} }), {
    nrouter_prompt_template_id: TEMPLATE,
  });
});

test('an empty selection produces an empty body — no nulls, no placeholders', () => {
  assert.deepEqual(promptExtraBody({}), {});
});

test('promptExtraBody emits NO tenancy field, whatever it is handed', () => {
  // Gate 5: tenancy comes from the authenticated key alone. A body-supplied
  // organization_id/team_id/user_id is the spend-attribution spoof.
  const body = promptExtraBody({
    templateId: TEMPLATE,
    variables: { organization_id: 'other-org', team_id: 'other-team', user_id: 'someone' },
  });
  for (const forbidden of ['organization_id', 'team_id', 'org_id', 'user_id']) {
    assert.equal(forbidden in body, false, `${forbidden} must never be a top-level body field`);
  }
  // The names above are legal VARIABLE names; they just are not authoritative.
  assert.equal(body.nrouter_prompt_variables.team_id, 'other-team');
});

// ---------------------------------------------------------------------------
// withVariables — merge order and non-mutation
// ---------------------------------------------------------------------------

test('withVariables merges, with the LATER value winning', () => {
  const base = promptTemplate(TEMPLATE, { tone: 'terse', lang: 'en' });
  assert.deepEqual(withVariables(base, { tone: 'warm' }), {
    templateId: TEMPLATE,
    variables: { tone: 'warm', lang: 'en' },
  });
});

test('withVariables NEVER mutates the selection it was given', () => {
  // A selection is the natural thing to hoist to module scope and reuse. A
  // mutating merge leaks one request's variables into every later request on
  // that selection — including into another tenant's call in a shared process.
  const base = promptTemplate(TEMPLATE, { tone: 'terse' });
  withVariables(base, { secret: 'leaked' });
  assert.deepEqual(base.variables, { tone: 'terse' });
});

test('withVariables never mutates the variables object it was given either', () => {
  const more = { tone: 'warm' };
  withVariables(promptTemplate(TEMPLATE, { lang: 'en' }), more);
  assert.deepEqual(more, { tone: 'warm' });
});

test('withVariables on a selection with no variables yet just adds them', () => {
  assert.deepEqual(withVariables({ templateId: TEMPLATE }, { tone: 'terse' }), {
    templateId: TEMPLATE,
    variables: { tone: 'terse' },
  });
});

// ---------------------------------------------------------------------------
// applyPrompt — folding a selection into call options
// ---------------------------------------------------------------------------

test('applyPrompt sets the two prompt options and touches nothing else', () => {
  const opts = { model: 'gpt-4o', prompt: 'hi', maxTokens: 64 };
  const out = applyPrompt(opts, promptTemplate(TEMPLATE, { tone: 'terse' }));
  assert.deepEqual(out, {
    model: 'gpt-4o',
    prompt: 'hi',
    maxTokens: 64,
    promptTemplateId: TEMPLATE,
    promptVariables: { tone: 'terse' },
  });
});

test('applyPrompt does NOT mutate the options it was given', () => {
  const opts = { model: 'gpt-4o' };
  applyPrompt(opts, promptTemplate(TEMPLATE));
  assert.equal('promptTemplateId' in opts, false);
});

test('applyPrompt with variables only leaves promptTemplateId unset', () => {
  const out = applyPrompt({ model: 'gpt-4o' }, promptVariables({ tone: 'terse' }));
  assert.equal('promptTemplateId' in out, false);
  assert.deepEqual(out.promptVariables, { tone: 'terse' });
});

test('applyPrompt MERGES onto variables the options already carried, selection winning', () => {
  const out = applyPrompt(
    { model: 'gpt-4o', promptVariables: { tone: 'terse', lang: 'en' } },
    promptVariables({ tone: 'warm' })
  );
  assert.deepEqual(out.promptVariables, { tone: 'warm', lang: 'en' });
});

test('applyPrompt with an EMPTY selection clears nothing the options already set', () => {
  const out = applyPrompt({ model: 'gpt-4o', promptTemplateId: TEMPLATE }, {});
  assert.equal(out.promptTemplateId, TEMPLATE);
});

// ---------------------------------------------------------------------------
// systemVariableConflicts — the silent-override footgun
// ---------------------------------------------------------------------------

test('the four system variable names are exactly what the gateway inserts last', () => {
  assert.deepEqual([...SYSTEM_VARIABLE_NAMES], ['org_name', 'model', 'timestamp', 'user_id']);
});

test('a caller variable that collides with a system name is REPORTED', () => {
  // The gateway inserts these AFTER the caller's map, so the caller's value is
  // discarded with no error and no header. A template that reads {{model}}
  // renders the authenticated request's model, never the caller's string.
  assert.deepEqual(systemVariableConflicts({ model: 'mine', tone: 'terse' }), ['model']);
});

test('conflicts are reported in the gateway insertion order, not the caller order', () => {
  assert.deepEqual(
    systemVariableConflicts({ user_id: 'x', model: 'y', org_name: 'z' }),
    ['org_name', 'model', 'user_id']
  );
});

test('no collision reports nothing, and undefined is not a crash', () => {
  assert.deepEqual(systemVariableConflicts({ tone: 'terse' }), []);
  assert.deepEqual(systemVariableConflicts(undefined), []);
  assert.deepEqual(systemVariableConflicts({}), []);
});

test('systemVariableConflicts only reports OWN keys, never inherited ones', () => {
  // `'model' in obj` walks the prototype chain, so a plain `in` test reports a
  // conflict for every object on earth — Object.prototype has no `model`, but
  // an options bag built with `Object.create(defaults)` does.
  const inherited = Object.create({ model: 'from-the-prototype' });
  inherited.tone = 'terse';
  assert.deepEqual(systemVariableConflicts(inherited), []);
});
