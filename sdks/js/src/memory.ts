// Conversation memory — CLIENT-SIDE ONLY.
//
// ===========================================================================
// THE GATEWAY REMEMBERS NOTHING BETWEEN REQUESTS.
// ===========================================================================
//
// MEASURED 2026-08-28: the string `memory` appears ZERO times in
// spec/nrouter-sdk-spec.json, and no route in the Rust gateway's fifteen-route
// `/v1/*` surface accepts, returns, or persists a conversation. Every request
// is independent and stateless at the server; the entire history is whatever
// the caller puts in `messages`.
//
// So this module is a local convenience for holding an array of turns between
// calls. It is NOT a "memory feature", it does not talk to nRouter, and it
// sends nothing anywhere. Anything in this file that implied otherwise — a
// `sync()`, a `sessionId` the gateway would recognise, a "server-side history"
// option — would be a lie to the user about a surface that does not exist.
//
// ---------------------------------------------------------------------------
// TWO DESIGN CHOICES THAT LOOK LIKE MISSING FEATURES
// ---------------------------------------------------------------------------
//
// 1. NOTHING IS PERSISTED BY DEFAULT. The default store is a plain in-process
//    array: no file, no `localStorage`, no `~/.nrouter`. Prompt and completion
//    text is usually personal data, so writing it to durable storage is a GDPR
//    decision with a retention and erasure obligation attached — the caller's
//    to make, never a convenience this SDK takes on their behalf. Supplying a
//    `MemoryStore` backed by Redis, a file or a database is exactly how a
//    caller makes it, deliberately and in their own code.
//
// 2. IT IS EXPLICIT AT THE CALL SITE. There is no client hook and no implicit
//    injection:
//
//        await mem.add({ role: 'user', content: 'hi' });
//        const res = await client.nr.chat({
//          model: 'anthropic/claude-sonnet-4-5-20250929',
//          messages: await mem.messages(),
//        });
//        await mem.add({ role: 'assistant', content: client.nr.text(res) });
//
//    The request body stays exactly what the caller passed. A memory that
//    silently appended turns would make the billed token count depend on
//    hidden state — and token count is money (gateway rules §4f gates 1-3).
//
// 3. HISTORY GROWS WITHOUT BOUND. Every turn in `messages()` is passed whole
//    to the provider, so turn N re-sends and will re-bill turns 1..N-1 on every
//    request. Token count is money, so pruning turns or applying a summary is
//    an application concern.
//
// Every method returns a Promise even though the default store is synchronous.
// That is deliberate: a caller who later swaps in Redis changes ONE line (the
// store) instead of every call site, and an API that were sync-by-default
// could not honestly express an async store at all.

import { configurationError } from './errors';
import type { ChatMessage, ChatRole } from './types';

/**
 * Where a `Memory` keeps its turns.
 *
 * Both methods may be synchronous or return a Promise; the memory awaits
 * either. Implement this against Redis, a file, a database row — anywhere the
 * caller has decided it is lawful to keep conversation text.
 *
 * The contract the memory relies on, and the one an implementation must not
 * break: `load()` returns the messages a previous `save()` was given. The
 * memory keeps NO cache of its own, so the store is the single system of
 * record and a store that answers from somewhere else is what the caller gets.
 */
export interface MemoryStore {
  load(): ChatMessage[] | Promise<ChatMessage[]>;
  save(messages: ChatMessage[]): void | Promise<void>;
}

export interface WindowOptions {
  /** Maximum number of messages to keep. Non-positive returns empty. */
  maxMessages?: number;
  /** Keep the leading system/developer message (at index 0) even when window truncates. Defaults to true. */
  preserveSystem?: boolean;
}

export interface MemoryOptions extends WindowOptions {
  /** Defaults to `createArrayStore()` — in-process, never written anywhere. */
  store?: MemoryStore;
}

/** A conversation history held on THIS machine. See the file header. */
export interface Memory {
  /** Append one turn. Rejects a malformed message or a tenancy field. */
  add(message: ChatMessage): Promise<void>;
  /** The history, in order, as a copy safe to mutate and to pass as `messages`. */
  messages(options?: WindowOptions): Promise<ChatMessage[]>;
  /** Forget everything. Reaches the store, not just a local view. */
  clear(): Promise<void>;
}

/**
 * The default store: a plain array in this process.
 *
 * It writes to no disk, no browser storage and no network. State lives as long
 * as the object does and dies with the process — which is the only default
 * that cannot create a personal-data retention obligation nobody chose.
 *
 * `seed` is COPIED, not aliased: a caller who seeds from an array they keep
 * using would otherwise see their own array grow behind them.
 */
export function createArrayStore(seed: ChatMessage[] = []): MemoryStore {
  let rows: ChatMessage[] = seed.map(cloneMessage);
  return {
    load: () => rows.map(cloneMessage),
    save: (messages) => {
      rows = messages.map(cloneMessage);
    },
  };
}

/**
 * Prune a message array to the most recent `maxMessages`, preserving the index 0
 * system/developer message by default.
 */
export function slidingWindow(
  messages: ChatMessage[],
  maxMessages?: number,
  preserveSystem = true
): ChatMessage[] {
  if (maxMessages === undefined || maxMessages === null) {
    return messages.map(cloneMessage);
  }
  if (!Number.isFinite(maxMessages) || maxMessages <= 0) {
    return [];
  }
  const limit = Math.floor(maxMessages);
  if (messages.length <= limit) {
    return messages.map(cloneMessage);
  }
  if (
    preserveSystem &&
    messages.length > 0 &&
    (messages[0].role === 'system' || messages[0].role === 'developer')
  ) {
    if (limit === 1) {
      return [cloneMessage(messages[messages.length - 1])];
    }
    const tailCount = limit - 1;
    const tail = messages.slice(messages.length - tailCount).map(cloneMessage);
    return [cloneMessage(messages[0]), ...tail];
  }
  return messages.slice(messages.length - limit).map(cloneMessage);
}

/**
 * Create a client-side conversation memory.
 *
 * Nothing here reaches nRouter. See the file header for why the default store
 * is volatile and why the call site stays explicit.
 */
export function createMemory(options: MemoryOptions = {}): Memory {
  const store = options.store ?? createArrayStore();

  // Every operation is a read-modify-write across an `await`, which is the
  // textbook lost update: two `add()` calls started together both `load()` the
  // same list, and the second `save()` overwrites the first — one message gone,
  // no error, nothing to see in a log. Serializing through a single chain is
  // the fix. It is invisible with the synchronous default store and very real
  // with any async one, which is exactly how this ships broken without a test.
  let chain: Promise<unknown> = Promise.resolve();

  function serialize<T>(op: () => Promise<T>): Promise<T> {
    const run = chain.then(op);
    // This `catch` does TWO jobs, which is why the chain is a separate promise
    // from the one handed back:
    //
    //   1. It keeps `chain` permanently FULFILLED, so one failed store write
    //      cannot poison it. Chaining the raw `run` instead would wedge every
    //      later call in the process after a single transient Redis blip.
    //   2. It is the only handler `chain` will ever get. Without it the chain
    //      holds a rejected promise nobody awaits, and Node reports an
    //      unhandled rejection even though the CALLER handled `run` correctly.
    //
    // An earlier revision also passed `op` as the rejection handler of the
    // `.then` above. That was redundant with (1) — each masked the other under
    // mutation testing, which is how dead defence hides a real regression.
    chain = run.catch(() => undefined);
    return run;
  }

  async function read(): Promise<ChatMessage[]> {
    let raw: unknown;
    try {
      raw = await store.load();
    } catch (err) {
      throw storeFailure('load', err);
    }
    if (!Array.isArray(raw)) {
      // Failing OPEN here — returning `[]` — would drop the whole conversation
      // and send a bare turn to the provider. The user reads that as a model
      // that forgot, not as a broken store, and the request is billed anyway.
      throw configurationError(
        `MemoryStore.load() must return an array of messages, got ${describe(raw)}.`
      );
    }
    // A store is caller-supplied and can be a shared key another process
    // writes. Validating only on the way IN would leave the read path as the
    // smuggling route that `add()` closes.
    return raw.map((m, i) => validateMessage(m, `MemoryStore.load()[${i}]`));
  }

  async function write(messages: ChatMessage[]): Promise<void> {
    try {
      await store.save(messages);
    } catch (err) {
      throw storeFailure('save', err);
    }
  }

  return {
    // `async` is load-bearing, not stylistic. Validation runs BEFORE the queue
    // so a malformed message never occupies a slot in the chain — but a plain
    // method would then THROW SYNCHRONOUSLY out of a `Promise`-returning API,
    // and a caller's `.catch()` (or `Promise.all`) would never see it. Measured:
    // `assert.rejects` failed on exactly that. `async` turns the throw into the
    // rejection the signature promises.
    async add(message) {
      const clean = validateMessage(message, 'add()');
      return serialize(async () => {
        const current = await read();
        current.push(clean);
        await write(current);
      });
    },
    messages(callOptions?: WindowOptions) {
      // `read()` already rebuilds every message through `validateMessage`,
      // which clones. The caller therefore gets a copy: pushing to the array,
      // sorting it, or editing a message in place cannot reach back into the
      // store. Handing out the live array is how a caller's ordinary
      // `msgs.push(...)` before a call silently adds a turn nobody wrote.
      return serialize(async () => {
        const msgs = await read();
        const max = callOptions?.maxMessages ?? options.maxMessages;
        const preserve = callOptions?.preserveSystem ?? options.preserveSystem ?? true;
        if (max !== undefined) {
          return slidingWindow(msgs, max, preserve);
        }
        return msgs;
      });
    },
    clear() {
      return serialize(() => write([]));
    },
  };
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

/**
 * Mirrors the `ChatRole` union in types.ts. Widening one without the other is
 * how a role this SDK's body builders cannot emit gets into a history.
 */
const ROLES: readonly ChatRole[] = ['system', 'user', 'assistant', 'tool', 'developer'];

/**
 * Keys that would place a tenancy identifier in a request body.
 *
 * Rust gateway rules §4f GATE 5: tenancy is resolved from the authenticated
 * caller ALONE — never a header, body or query param — because a body-supplied
 * org/team id is the spend-attribution spoof, one tenant's usage billed to
 * another. `test/options.test.ts` already pins this for the body builders;
 * memory is the other route a message reaches a body, so the same gate holds
 * here or memory is the hole.
 *
 * Compared normalized (lowercased, underscores dropped) so `organization_id`,
 * `organizationId` and `ORGANIZATION_ID` are all one entry.
 */
const TENANCY_KEYS = new Set(['organizationid', 'orgid', 'teamid', 'userid', 'nrouterorg']);

const normalizeKey = (key: string): string => key.toLowerCase().replace(/_/g, '');

/**
 * Check one message and return a defensive copy of it.
 *
 * A tenancy key is REFUSED rather than stripped. Stripping is the tempting
 * option and it is worse: the caller believes the field was honoured, so a
 * genuine attempt to attribute spend elsewhere fails silently and forever. A
 * loud `configuration` error says the field has no effect and never will.
 */
function validateMessage(message: unknown, where: string): ChatMessage {
  if (typeof message !== 'object' || message === null || Array.isArray(message)) {
    throw configurationError(`${where}: a message must be an object, got ${describe(message)}.`);
  }

  // Clone into plain own data properties FIRST. This freezes getter evaluations
  // so a dynamic getter cannot return valid data during validation and flip
  // afterwards, and prevents __proto__ setters from executing.
  const cloned = cloneMessage(message as ChatMessage);
  const record = cloned as unknown as Record<string, unknown>;

  for (const key of Object.getOwnPropertyNames(record)) {
    if (TENANCY_KEYS.has(normalizeKey(key))) {
      throw configurationError(
        `${where}: a message must not carry the tenancy field "${key}". ` +
          'The gateway resolves the organization, team and user from the ' +
          'authenticated API key alone; a body-supplied identifier is ignored ' +
          'at best and a spend-attribution spoof at worst.'
      );
    }
  }

  if (!ROLES.includes(record.role as ChatRole)) {
    throw configurationError(
      `${where}: role must be one of ${ROLES.join(', ')}, got ${describe(record.role)}.`
    );
  }

  const content = record.content;
  const hasToolCalls = Array.isArray(record.tool_calls) && record.tool_calls.length > 0;
  if (content === null || content === undefined) {
    if (!hasToolCalls && record.role !== 'assistant') {
      throw configurationError(
        `${where}: content must be a string or an array of content parts, got ${describe(content)}.`
      );
    }
  } else if (typeof content !== 'string' && !Array.isArray(content)) {
    throw configurationError(
      `${where}: content must be a string or an array of content parts, got ${describe(content)}.`
    );
  }

  return cloned;
}

// ---------------------------------------------------------------------------
// Copying
// ---------------------------------------------------------------------------

/**
 * A structural copy, deep enough that nothing the caller still holds aliases
 * anything the store holds.
 *
 * Shallow `{ ...message }` is not enough: a multimodal turn's `content` is an
 * array of part objects, so a caller mutating `part.image_url.url` after
 * `add()` would rewrite a message already recorded as sent.
 *
 * Every other key is preserved. Memory is a container, not a message
 * rewriter — dropping an unrecognised field would silently change the request
 * the caller assembled, and the caller can only debug what they can see.
 */
function cloneMessage(message: ChatMessage): ChatMessage {
  return cloneValue(message) as ChatMessage;
}

function cloneValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (typeof value === 'object' && value !== null) {
    // A Date, a Map or a class instance is out of scope by construction: a
    // message is JSON on the wire, so anything that does not survive
    // serialization would not have reached the provider either.
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      Object.defineProperty(out, k, {
        value: cloneValue(v),
        enumerable: true,
        writable: true,
        configurable: true,
      });
    }
    return out;
  }
  return value;
}

// ---------------------------------------------------------------------------
// Failure classification
// ---------------------------------------------------------------------------

/**
 * A store failure is a `configuration` error — PERMANENT — even when the store
 * is a network one and the underlying fault was transient.
 *
 * `isRetryable()` is what a caller's `while (isRetryable(e))` loop reads, and
 * it answers true for `transport`. But retrying is this SDK's answer to a
 * failed GATEWAY request, and no gateway request happened here: re-running the
 * same call re-runs the same broken store against the same broken
 * configuration, so a `transport` classification spins that loop forever
 * without ever reaching the network. The caller's own store is the caller's
 * own retry surface.
 *
 * An error we raised ourselves passes through unwrapped so a validation
 * message is not buried under a second layer.
 */
function storeFailure(operation: 'load' | 'save', err: unknown): unknown {
  if (err instanceof Error && (err as { kind?: unknown }).kind === 'configuration') return err;
  const detail = err instanceof Error ? err.message : describe(err);
  return configurationError(`MemoryStore.${operation}() failed: ${detail}`, { cause: err });
}

function describe(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'an array';
  return typeof value;
}
