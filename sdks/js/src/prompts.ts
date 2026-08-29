// Managed prompts — ergonomics over the two prompt fields the gateway reads.
//
// This module INVENTS NOTHING on the wire. The nRouter request-field set is
// CLOSED (`extra_body_fields` in spec/nrouter-sdk-spec.json, Rule #14), and the
// gateway forwards a field it does not recognise straight to the provider — so
// an invented field is not an error a caller ever sees, it is a dead option
// that looks live. Everything here maps onto exactly two names:
//
//   nrouter_prompt_template_id   — name ONE template for this request
//   nrouter_prompt_variables     — the values to render it with
//
// `options.ts` owns that mapping and this module DELEGATES to it rather than
// re-deriving it, so the omission rules cannot drift into two versions.
//
// # The one relationship worth a module
//
// The two fields look like a pair and are not. The gateway takes them off the
// body INDEPENDENTLY (`http::prompt_runtime::take_controls`), so there are
// three meaningful selections, not two:
//
//   template id + variables  — run THIS template, rendered with these values
//   variables only           — run the template ASSIGNED to this key/team/org,
//                              rendered with these values. The common case in
//                              production, and the one a "variables need a
//                              template id" simplification silently deletes.
//   template id only         — run THIS template with the assignment's own
//                              variables and the system ones
//
// # What this module deliberately does NOT do
//
// It does not validate a template id's UUID shape, does not check that the
// template exists, and does not refuse a variable name. Each of those is a
// server-side fact this process cannot know, and a client-side guess about one
// refuses requests that work. The single exception is documented at
// `promptTemplate`, where an empty id does not fail — it silently changes which
// prompt runs.
//
// Nothing here touches tenancy. The gateway resolves the organization, team and
// user from the authenticated virtual key alone; a body-supplied tenancy field
// is the spend-attribution spoof that gateway gate 5 exists to stop, and the
// four system variables below are how the gateway keeps that true even inside a
// rendered prompt.

import { configurationError } from './errors';
import { buildExtraBody } from './options';
import type { NRouterExtraBody, NRouterFeatureOptions } from './types';

/** The request field naming one template. Exported as data, never retyped. */
export const PROMPT_TEMPLATE_ID_FIELD = 'nrouter_prompt_template_id';

/** The request field carrying that template's variables. */
export const PROMPT_VARIABLES_FIELD = 'nrouter_prompt_variables';

/**
 * Both prompt fields, in the order the gateway removes them from the body.
 *
 * A caller filtering or logging a request body needs the same two names this
 * SDK writes; retyping them is how a logger starts leaking a field it meant to
 * strip, or stripping one that was never there.
 */
export const PROMPT_WIRE_FIELDS = [PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD] as const;

/**
 * The variable names the gateway fills in itself, in the order it inserts them.
 *
 * They are written LAST, after the assignment's variables and after the
 * caller's, so a caller value under one of these names never reaches the
 * template. That is a security property, not a quirk: it is what stops a
 * request body from spoofing the authenticated org, user or model inside a
 * prompt the operator wrote. There is no error and no header when it happens,
 * which is exactly why `systemVariableConflicts` exists.
 */
export const SYSTEM_VARIABLE_NAMES = ['org_name', 'model', 'timestamp', 'user_id'] as const;

export type SystemVariableName = (typeof SYSTEM_VARIABLE_NAMES)[number];

/**
 * One request's prompt choice: a template, some variables, or both.
 *
 * Both fields are optional and the three populated combinations are all
 * meaningful — see the module comment. An empty selection is meaningful too: it
 * asks for whatever the organization already configured.
 */
export interface PromptSelection {
  /** The template to run for this request (UUID). Omit to use the assignment. */
  templateId?: string;
  /** Values to render with. Applied over the assignment's own variables. */
  variables?: Record<string, string>;
}

/** Copy a variables map, dropping nothing and sharing nothing with the source. */
function copyVariables(variables: Record<string, string>): Record<string, string> {
  return { ...variables };
}

/**
 * Name a template for this request, optionally with its variables.
 *
 * REFUSES an empty or whitespace-only id, and this is the one client-side
 * refusal in the module. An empty id is not rejected by the gateway: the
 * mapping in `options.ts` tests the id for truthiness, so `''` never reaches
 * the body, and a body carrying variables and NO template id is a valid
 * request — it resolves the key/team/org ASSIGNMENT instead. So an
 * uninitialised id does not fail loudly, it quietly runs a DIFFERENT prompt and
 * bills for it. This is the last place that difference is still visible.
 *
 * `undefined` is not refused here because it cannot be typed into this
 * parameter; a caller who genuinely has no template wants `promptVariables`.
 */
export function promptTemplate(
  templateId: string,
  variables?: Record<string, string>,
): PromptSelection {
  if (typeof templateId !== 'string' || templateId.trim() === '') {
    // No interpolation of the value: the message must stay safe to log, and a
    // caller who passed the wrong variable could otherwise print a secret
    // through it. The remedy is what the reader needs, not the empty string.
    throw configurationError(
      'promptTemplate requires a template id. An empty id is not an error at ' +
        'the gateway — it is dropped from the request, which silently runs the ' +
        'template assigned to this key, team or organization instead. Pass the ' +
        'template id, or call promptVariables() if the assignment is what you want.',
    );
  }

  const selection: PromptSelection = { templateId };
  // Omitted rather than defaulted to `{}`: the mapping already drops an empty
  // map, so a default would be invisible on the wire and misleading in a log.
  if (variables) selection.variables = copyVariables(variables);
  return selection;
}

/**
 * Render the template already ASSIGNED to this key, team or organization.
 *
 * This is a first-class selection, not a degraded one. The gateway resolves the
 * assignment whenever no template id was sent and merges the caller's variables
 * into it, so an application that lets its operator swap the prompt from the
 * dashboard — without a deploy — sends variables and nothing else.
 */
export function promptVariables(variables: Record<string, string>): PromptSelection {
  return { variables: copyVariables(variables) };
}

/**
 * Add variables to a selection, later values winning.
 *
 * NON-MUTATING, and that is the whole point. A selection is the natural thing
 * to build once at module scope and reuse per request; a merge that wrote into
 * it would carry one request's variables into every later request made through
 * the same selection — including, in a shared server process, another tenant's.
 * The caller's `more` map is copied for the same reason.
 *
 * Later-wins matches the gateway, which merges the caller's map over the
 * assignment's (`variables.extend(caller_variables)`), so a value added closer
 * to the call site behaves the same way here and there.
 */
export function withVariables(
  selection: PromptSelection,
  more: Record<string, string>,
): PromptSelection {
  const merged: PromptSelection = { ...selection, variables: { ...selection.variables, ...more } };
  return merged;
}

/**
 * Map a selection onto the request fields.
 *
 * Delegated to `buildExtraBody` rather than reimplemented: it is the single
 * place in this SDK that knows the wire shape, including that an empty
 * variables map is OMITTED rather than sent as `{}`. Two implementations of an
 * omission rule is how the SDK and the hosted playground start disagreeing
 * about what a request means.
 *
 * The result carries the prompt fields and nothing else — no cache field, no
 * tenancy field, nothing this selection did not ask for.
 */
export function promptExtraBody(selection: PromptSelection): NRouterExtraBody {
  return buildExtraBody({
    promptTemplateId: selection.templateId,
    promptVariables: selection.variables,
  });
}

/**
 * Fold a selection into an options bag for `nr.chat` and friends.
 *
 * Returns a NEW object; the caller's options are never written to, because an
 * options bag is as reusable as a selection and the same cross-request leak
 * applies.
 *
 * Variables already on the options are PRESERVED and the selection's win on a
 * collision, matching `withVariables` and the gateway's own merge direction. An
 * empty selection therefore clears nothing: applying "no opinion" must not
 * delete a template the caller set two lines earlier.
 */
export function applyPrompt<T extends NRouterFeatureOptions>(
  options: T,
  selection: PromptSelection,
): T {
  const next: T = { ...options };

  if (selection.templateId) {
    next.promptTemplateId = selection.templateId;
  }

  if (selection.variables) {
    next.promptVariables = { ...options.promptVariables, ...selection.variables };
  }

  return next;
}

/**
 * Which of these variable names the gateway will overwrite before rendering.
 *
 * The four system variables are inserted after the caller's map, so a value
 * supplied under one of those names is discarded — with no error, no header and
 * no log line the caller can see. A template reading `{{model}}` renders the
 * authenticated request's model, never the caller's string.
 *
 * Reported in the gateway's insertion order rather than the caller's, so two
 * runs over the same map read the same way.
 *
 * OWN keys only. A plain `name in variables` walks the prototype chain, which
 * would report a conflict for an options bag built with `Object.create(...)`
 * over defaults — a false positive on a map whose own keys collide with
 * nothing.
 */
export function systemVariableConflicts(
  variables: Record<string, string> | undefined | null,
): SystemVariableName[] {
  if (!variables) return [];
  return SYSTEM_VARIABLE_NAMES.filter((name) =>
    Object.prototype.hasOwnProperty.call(variables, name),
  );
}
