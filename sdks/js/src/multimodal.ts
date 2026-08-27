// The non-text modality helpers: speech, transcription, translation, images,
// video and embeddings.
//
// These endpoints are the ones the OpenAI-shaped client handles worst, and
// each way it handles them badly costs the caller money:
//
//   - `/audio/speech` and `/videos/{id}/content` return BYTES. Parsing a
//     binary body as JSON yields `{}`, so the call reports success and hands
//     back nothing for a request that was billed.
//   - `/audio/transcriptions` and `/audio/translations` publish FOUR success
//     media types — JSON, plain text, SRT and VTT. Collapsing them to JSON
//     throws away the subtitle track the caller asked for.
//   - Multipart uploads put a caller-supplied filename into a MIME header,
//     and MIME header parameters have no escape for a line break.
//
// Every guard below names the failure it prevents. Nothing here reaches the
// network on its own: the transport is injected (see `Transport`), so all of
// it is unit-testable with no server and no global `fetch`.
//
// Rule #14: the endpoint list is closed and comes from
// spec/nrouter-sdk-spec.json. `MULTIMODAL_ENDPOINTS` below is that subset,
// spelled out so a conformance check can compare it to the spec instead of
// reading it back out of string concatenation.

import { metaFromHeaders } from './meta';
import {
  classifyError,
  configurationError,
  transportError,
  parseErrorBody,
  parseRetryAfter,
  nRouterError,
  createError,
  errorEnvelopeOnSuccess,
} from './errors';
import type {
  ChatContentPart,
  NRouterResponse,
  ResponseMeta,
} from './types';

// ---------------------------------------------------------------------------
// The transport seam
// ---------------------------------------------------------------------------

/**
 * An abort signal, structurally.
 *
 * Deliberately not the DOM `AbortSignal`: this package compiles under
 * `lib: ["ES2020"]` with no DOM, so naming `AbortSignal` would make the SDK
 * depend on the caller's ambient type environment. The value is carried
 * through opaquely and only the transport ever inspects it.
 */
export interface AbortSignalLike {
  readonly aborted: boolean;
}

/**
 * One outbound request, fully encoded.
 *
 * `body` is already bytes and `contentType` already describes them. This
 * module owns JSON serialization and multipart framing precisely so the
 * bytes on the wire are a deterministic function of the arguments — which is
 * what makes the CR/LF injection guard provable rather than dependent on
 * whichever `FormData` implementation the host happens to ship.
 */
export interface TransportRequest {
  readonly method: 'GET' | 'POST';
  /**
   * Path BELOW the gateway's `/v1` root, with a leading slash and already
   * percent-encoded — e.g. `/audio/speech`, `/videos/vid_123/content`.
   *
   * The transport joins it to the base URL. Keeping the base URL out of this
   * module is deliberate: it is a dynamic value (prod, stage, a local run)
   * and nothing here should be able to hardcode one.
   */
  readonly path: string;
  /** Content-Type describing `body`. Absent exactly when `body` is absent. */
  readonly contentType?: string;
  readonly body?: Uint8Array;
  readonly signal?: AbortSignalLike;
}

/**
 * One inbound response, undecoded.
 *
 * `bytes()` and nothing else. A transport that also offered `json()` would
 * invite the exact bug this module exists to prevent — deciding at the
 * transport layer that a response is JSON, before anyone has looked at its
 * content type.
 */
export interface TransportResponse {
  readonly status: number;
  /**
   * The response headers, as either a WHATWG-style bag with a
   * case-insensitive `get`, or a plain object keyed by lowercase name (what
   * Node hands back). Both are accepted; see `metaFromHeaders`.
   */
  readonly headers: HeaderSource;
  /** The complete response body. Called at most once per response. */
  bytes(): Promise<Uint8Array>;
}

/** A WHATWG-style header bag: anything with a case-insensitive `get`. */
export interface HeadersLike {
  get(name: string): string | null | undefined;
}

/** A Node `IncomingHttpHeaders`-style bag, or any plain object of headers. */
export type HeaderRecord = Record<string, string | string[] | undefined>;

/** Anything this module knows how to read headers out of. */
export type HeaderSource = HeadersLike | HeaderRecord;

/**
 * The one thing an integrator must implement.
 *
 * The transport owns the base URL, the `Authorization: Bearer sk-nrouter-…`
 * header, timeouts, retries and connection pooling. This module never sees
 * the API key — which is how Rule #5 ("never log, print or serialize the
 * key") is a structural property here rather than a habit: there is no field
 * on any type in this file that could hold one, so no thrown error, no
 * `toJSON` and no console dump can leak it.
 */
export interface Transport {
  request(request: TransportRequest): Promise<TransportResponse>;
}

/** Per-call knobs that are not part of the request body. */
export interface CallOptions {
  readonly signal?: AbortSignalLike;
}

// ---------------------------------------------------------------------------
// JSON, without `any`
// ---------------------------------------------------------------------------

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type JsonObject = { [key: string]: JsonValue };

// ---------------------------------------------------------------------------
// The closed endpoint list (Rule #14)
// ---------------------------------------------------------------------------

/**
 * Exactly the `supported_endpoints` paths this module calls.
 *
 * Exported as data so a conformance test can intersect it with the spec.
 * Adding a key here that the spec does not list is the defect this constant
 * is meant to make visible.
 */
export const MULTIMODAL_ENDPOINTS = {
  speech: 'POST /v1/audio/speech',
  transcribe: 'POST /v1/audio/transcriptions',
  translate: 'POST /v1/audio/translations',
  image: 'POST /v1/images/generations',
  video: 'POST /v1/videos',
  videoStatus: 'GET /v1/videos/{id}',
  videoContent: 'GET /v1/videos/{id}/content',
  embeddings: 'POST /v1/embeddings',
} as const;

// ---------------------------------------------------------------------------
// Parameter and result shapes
// ---------------------------------------------------------------------------

/**
 * The container the gateway will hand back from `/audio/speech`.
 *
 * `pcm` is deliberately absent: it is headerless raw samples, so a caller
 * writing the returned bytes to a `.pcm` file gets something no player opens
 * without being told the sample rate out of band. Pass it through `extra` if
 * you genuinely want it and know what to do with it.
 */
export type SpeechResponseFormat = 'mp3' | 'wav' | 'opus' | 'aac' | 'flac';

export interface SpeechParams {
  readonly model: string;
  /** The text to speak. */
  readonly input: string;
  readonly voice: string;
  readonly response_format?: SpeechResponseFormat;
  readonly speed?: number;
  readonly instructions?: string;
  /**
   * Anything else, merged into the body FIRST so a named field above always
   * wins. `extra` cannot silently clobber `model`.
   */
  readonly extra?: JsonObject;
}

/** A binary success: the bytes, what they are, and what the request cost. */
export interface BinaryResult {
  /** The complete response body. Never empty — an empty 2xx is refused. */
  readonly bytes: Uint8Array;
  /**
   * The response `Content-Type`, e.g. `audio/mpeg`. `null` when the gateway
   * did not say — write the file with the extension you asked for rather
   * than guessing from the bytes.
   */
  readonly contentType: string | null;
  readonly meta: ResponseMeta;
}

/** The five formats `/audio/transcriptions` accepts. */
export type TranscriptionFormat = 'json' | 'verbose_json' | 'text' | 'srt' | 'vtt';

export interface TranscriptionParams {
  /** The audio bytes. */
  readonly file: Uint8Array | ArrayBuffer;
  /**
   * The filename sent with the upload. It MUST carry the real extension —
   * `speech.mp3`, not `audio` — because upstream providers pick their decoder
   * from it and reject an extensionless name outright.
   */
  readonly fileName: string;
  readonly model: string;
  /** ISO-639-1 hint. Improves accuracy and latency; not a filter. */
  readonly language?: string;
  /** A style/vocabulary hint for the transcriber. */
  readonly prompt?: string;
  readonly temperature?: number;
  /** Defaults to `json` at the provider when omitted. */
  readonly response_format?: TranscriptionFormat;
  /** Sent as a repeated `timestamp_granularities[]` field. */
  readonly timestampGranularities?: ReadonlyArray<'word' | 'segment'>;
  /** Extra form fields, stringified. Named fields above win on conflict. */
  readonly extra?: Readonly<Record<string, string | number | boolean>>;
}

/**
 * `/audio/translations` translates INTO English, so there is no `language`
 * input to declare — omitting it here rather than accepting and dropping it
 * is the difference between a compile error and a silently ignored argument.
 */
export type TranslationParams = Omit<TranscriptionParams, 'language'>;

/**
 * A transcription result, discriminated by what actually came back.
 *
 * Two arms, not one, because the four published media types do not share a
 * shape: JSON has fields, SRT and VTT are cue tracks whose line breaks and
 * ordering are the payload. Flattening them into `{ text }` would make a
 * subtitle request indistinguishable from a plain one.
 */
export type TranscriptionResult =
  | {
      readonly kind: 'json';
      readonly format: 'json' | 'verbose_json';
      /** The parsed body — segments, words and timings live here. */
      readonly body: JsonObject;
      /** The `text` field when the provider sent one; `null` otherwise. */
      readonly text: string | null;
      readonly meta: ResponseMeta;
    }
  | {
      readonly kind: 'text';
      readonly format: 'text' | 'srt' | 'vtt';
      /** The body verbatim. For `srt`/`vtt` the line breaks are the format. */
      readonly text: string;
      readonly meta: ResponseMeta;
    };

export interface ImageParams {
  readonly model: string;
  readonly prompt: string;
  readonly n?: number;
  readonly size?: string;
  readonly quality?: string;
  readonly style?: string;
  /**
   * `url` returns a link, `b64_json` returns base64 INSIDE the JSON body.
   * Neither makes this a binary endpoint — there is no image-bytes route in
   * the spec, so `image()` always returns JSON.
   */
  readonly response_format?: 'url' | 'b64_json';
  readonly user?: string;
  readonly extra?: JsonObject;
}

export interface VideoParams {
  readonly model: string;
  readonly prompt: string;
  readonly seconds?: number | string;
  readonly size?: string;
  readonly extra?: JsonObject;
}

export interface EmbeddingsParams {
  readonly model: string;
  readonly input: string | ReadonlyArray<string> | ReadonlyArray<number> | ReadonlyArray<ReadonlyArray<number>>;
  readonly dimensions?: number;
  readonly encoding_format?: 'float' | 'base64';
  readonly user?: string;
  readonly extra?: JsonObject;
}

// ---------------------------------------------------------------------------
// The helper surface
// ---------------------------------------------------------------------------

/**
 * The non-text modality endpoints, bound to one transport.
 *
 * A class rather than free functions because there is exactly one dependency
 * and it is the same for every call: binding it once at construction beats
 * threading it through eight signatures. `dataUrlToPart` stays a free
 * function for the mirror-image reason — it performs no I/O, and making it a
 * method would imply it does.
 */
export class Multimodal {
  private readonly transport: Transport;

  constructor(transport: Transport) {
    // A missing transport is a wiring mistake, and catching it here turns
    // "cannot read property 'request' of undefined" on the first call into a
    // sentence naming what is missing.
    if (!transport || typeof transport.request !== 'function') {
      throw configurationError('Multimodal requires a Transport with a request() method');
    }
    this.transport = transport;
  }

  /**
   * POST /v1/audio/speech — text to audio.
   *
   * Returns BYTES, always. This endpoint is billed on the call, so parsing
   * its body as JSON would charge the caller and hand back `{}` while
   * reporting success. There is no JSON-returning variant to fall back to.
   */
  async speech(params: SpeechParams, options?: CallOptions): Promise<BinaryResult> {
    requireNonEmpty(params.model, 'model');
    requireNonEmpty(params.input, 'input');
    requireNonEmpty(params.voice, 'voice');

    // `defined()` around the named fields, not a bare spread. A property whose
    // value is `undefined` still OVERWRITES an earlier one in an object
    // literal, so a caller using the documented escape hatch —
    // `extra: { response_format: 'pcm' }` — and leaving the typed
    // `response_format` unset had their value replaced by `undefined` and
    // dropped by jsonBody. The request then silently used the provider default
    // instead of PCM: no error, just the wrong audio format.
    const body = jsonBody({
      ...(params.extra ?? {}),
      ...defined({
        model: params.model,
        input: params.input,
        voice: params.voice,
        response_format: params.response_format,
        speed: params.speed,
        instructions: params.instructions,
      }),
    });

    const raw = await this.send('POST', '/audio/speech', body, options);
    return requireBinary(raw, 'speech()');
  }

  /**
   * POST /v1/audio/transcriptions — audio to text in the SAME language.
   *
   * The caller's `response_format` decides the media type, and all four
   * published ones are returned faithfully; see `TranscriptionResult`.
   */
  async transcribe(params: TranscriptionParams, options?: CallOptions): Promise<TranscriptionResult> {
    return this.audioUpload('/audio/transcriptions', params, params.language, options);
  }

  /**
   * POST /v1/audio/translations — audio in any language to ENGLISH text.
   *
   * Same four media types as `transcribe`.
   */
  async translate(params: TranslationParams, options?: CallOptions): Promise<TranscriptionResult> {
    return this.audioUpload('/audio/translations', params, undefined, options);
  }

  /** POST /v1/images/generations. */
  async image(params: ImageParams, options?: CallOptions): Promise<NRouterResponse<JsonObject>> {
    requireNonEmpty(params.model, 'model');
    requireNonEmpty(params.prompt, 'prompt');

    const body = jsonBody({
      ...(params.extra ?? {}),
      ...defined({
        model: params.model,
        prompt: params.prompt,
        n: params.n,
        size: params.size,
        quality: params.quality,
        style: params.style,
        response_format: params.response_format,
        user: params.user,
      }),
    });

    const raw = await this.send('POST', '/images/generations', body, options);
    return requireJson(raw, 'image()');
  }

  /**
   * POST /v1/videos — start a generation job.
   *
   * THIS is the billed call. Polling with `videoStatus` and downloading with
   * `videoContent` are free (gateway `src/http/videos.rs`: "Create bills;
   * collection is free"), so a retry loop around *this* method spends real
   * credits per attempt while a poll loop does not.
   */
  async video(params: VideoParams, options?: CallOptions): Promise<NRouterResponse<JsonObject>> {
    requireNonEmpty(params.model, 'model');
    requireNonEmpty(params.prompt, 'prompt');

    const body = jsonBody({
      ...(params.extra ?? {}),
      ...defined({
        model: params.model,
        prompt: params.prompt,
        seconds: params.seconds,
        size: params.size,
      }),
    });

    const raw = await this.send('POST', '/videos', body, options);
    return requireJson(raw, 'video()');
  }

  /**
   * GET /v1/videos/{id} — poll a job. Free; see `video()`.
   */
  async videoStatus(id: string, options?: CallOptions): Promise<NRouterResponse<JsonObject>> {
    const raw = await this.send('GET', `/videos/${encodePathSegment(id, 'video id')}`, undefined, options);
    return requireJson(raw, 'videoStatus()');
  }

  /**
   * GET /v1/videos/{id}/content — the rendered video BYTES. Free; see
   * `video()`.
   *
   * Binary for the same reason as `speech()`: JSON-parsing an MP4 produces an
   * empty object that looks like a successful, empty result.
   */
  async videoContent(id: string, options?: CallOptions): Promise<BinaryResult> {
    const raw = await this.send('GET', `/videos/${encodePathSegment(id, 'video id')}/content`, undefined, options);
    return requireBinary(raw, 'videoContent()');
  }

  /** POST /v1/embeddings. */
  async embeddings(params: EmbeddingsParams, options?: CallOptions): Promise<NRouterResponse<JsonObject>> {
    requireNonEmpty(params.model, 'model');
    if (params.input === undefined || params.input === null) {
      throw configurationError('embeddings() requires `input`');
    }
    if (typeof params.input === 'string' && params.input.length === 0) {
      throw configurationError('embeddings() `input` must not be an empty string');
    }
    if (Array.isArray(params.input) && params.input.length === 0) {
      // An empty array is billed as a request and returns an empty data set:
      // a caller sees "success, no embeddings" and cannot tell it from a
      // model that produced nothing.
      throw configurationError('embeddings() `input` must not be an empty array');
    }

    const body = jsonBody({
      ...(params.extra ?? {}),
      ...defined({
        model: params.model,
        input: params.input as JsonValue,
        dimensions: params.dimensions,
        encoding_format: params.encoding_format,
        user: params.user,
      }),
    });

    const raw = await this.send('POST', '/embeddings', body, options);
    return requireJson(raw, 'embeddings()');
  }

  // -------------------------------------------------------------------------
  // internals
  // -------------------------------------------------------------------------

  private async audioUpload(
    path: string,
    params: TranscriptionParams | TranslationParams,
    language: string | undefined,
    options?: CallOptions,
  ): Promise<TranscriptionResult> {
    requireNonEmpty(params.model, 'model');

    const fields: MultipartField[] = [];
    // MULTIPART IS NOT JSON, and "last one wins" does not hold here.
    //
    // In a JSON body a later key overwrites an earlier one, so emitting
    // `extra` first genuinely lets the named field win. The gateway settles a
    // multipart target from the FIRST part carrying that name
    // (nrouter-rust-gateway src/http/audio.rs), so the identical ordering
    // does the OPPOSITE: `extra.model` would be the one preflight authorizes
    // and prices, while `params.model` — the value the caller passed and the
    // one this SDK validated — is ignored. A caller could route and bill
    // against a model they never named.
    //
    // So a reserved name is DROPPED from `extra` rather than emitted ahead of
    // its named parameter, and the named parameter is written first.
    pushField(fields, 'model', params.model);
    pushField(fields, 'language', language);
    pushField(fields, 'prompt', params.prompt);
    pushField(fields, 'temperature', params.temperature);
    pushField(fields, 'response_format', params.response_format);
    for (const [name, value] of Object.entries(params.extra ?? {})) {
      if (MULTIPART_RESERVED_FIELDS.has(name)) continue;
      fields.push({ name, value: String(value) });
    }
    for (const granularity of params.timestampGranularities ?? []) {
      // Repeated field, not a comma-joined one: the provider reads
      // `timestamp_granularities[]` as a list and a joined string matches no
      // enum value, so it is dropped and word timings never appear.
      fields.push({ name: 'timestamp_granularities[]', value: granularity });
    }

    const body = multipartBody(fields, {
      name: 'file',
      fileName: params.fileName,
      bytes: toBytes(params.file, 'file'),
    });

    const raw = await this.send('POST', path, body, options);
    return decodeTranscription(raw, params.response_format);
  }

  private async send(
    method: 'GET' | 'POST',
    path: string,
    body: EncodedBody | undefined,
    options?: CallOptions,
  ): Promise<RawResult> {
    const response = await this.transport.request({
      method,
      path,
      contentType: body?.contentType,
      body: body?.bytes,
      signal: options?.signal,
    });

    // Metadata is read BEFORE the body, so a body-read failure still carries
    // the request id that identifies the billed request.
    const meta = metaFromHeaders(response.headers as never);
    const contentType = readHeader(response.headers, 'content-type');
    const retryAfter = parseRetryAfter(readHeader(response.headers, 'retry-after'));
    const status = response.status;

    let bytes: Uint8Array;
    try {
      bytes = await response.bytes();
    } catch (cause) {
      // The request DID reach the gateway and may have been billed. Carry the
      // status and request id rather than raising a bare I/O error with no
      // way to correlate it to a spend row.
      throw transportError(`could not read the response body: ${describe(cause)}`, {
        status,
        meta,
        retryAfter,
        cause,
      });
    }

    const raw: RawResult = { status, meta, bytes, contentType, retryAfter };
    if (status < 200 || status >= 300) {
      throw gatewayError(raw);
    }
    return raw;
  }
}

// ---------------------------------------------------------------------------
// Chat image attachments
// ---------------------------------------------------------------------------

/**
 * Fold an image reference into a chat turn as an `image_url` content part.
 *
 * Validates the shape BEFORE it is sent, because the failure mode otherwise is
 * opaque: the gateway forwards the string, the provider rejects it with its
 * own wording ("invalid image", "unsupported url"), the caller is billed for
 * the attempt, and nothing in the message says the URL was malformed on the
 * way out.
 *
 * Two forms are accepted and no others:
 *
 *   - `data:image/<type>;base64,<payload>` — an inline image. The `;base64`
 *     marker is required: a percent-encoded data URL carries binary that
 *     survives no round trip the providers make.
 *   - `https://…` — a fetchable image. Plain `http://` is refused: the
 *     provider would fetch it in the clear, and most reject it outright, so
 *     accepting it here just moves the failure somewhere harder to read.
 */
export function dataUrlToPart(url: string): ChatContentPart {
  if (typeof url !== 'string') {
    throw configurationError('image reference must be a string');
  }
  const trimmed = url.trim();
  if (trimmed.length === 0) {
    throw configurationError('image reference must not be empty');
  }
  // A line break inside a URL that later lands in a header or a log line is
  // the same injection class the multipart guard below refuses.
  if (/[\r\n]/.test(trimmed)) {
    throw configurationError('image reference must not contain a carriage return or line feed');
  }

  const lower = trimmed.slice(0, 5).toLowerCase();

  if (lower === 'data:') {
    const match = /^data:image\/([A-Za-z0-9.+-]+)((?:;[A-Za-z0-9-]+=[^;,]*)*);base64,(.*)$/.exec(trimmed);
    if (!match) {
      throw configurationError(
        'a data: image reference must look like "data:image/<type>;base64,<payload>" ' +
          '(the media type must be image/*, and ";base64" is required)',
      );
    }
    const payload = match[3];
    if (payload.length === 0) {
      throw configurationError('data: image reference carries an empty base64 payload');
    }
    if (/\s/.test(payload)) {
      // A wrapped payload (base64 split across lines) is not a valid data
      // URL and is silently truncated by some parsers at the first newline —
      // producing a corrupt image rather than an error.
      throw configurationError('data: image payload contains whitespace; strip line breaks before sending');
    }
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(payload)) {
      throw configurationError(
        'data: image payload is not standard base64 (base64url with "-" and "_" is not accepted here)',
      );
    }
    // LENGTH, not just the alphabet. Base64 encodes in 4-character groups, so
    // a payload whose length mod 4 is 1 cannot decode no matter what it
    // contains — `data:image/png;base64,A` passed the character check and then
    // failed at the provider, AFTER the request was billed. Refusing locally
    // is free; refusing at the provider is not.
    // Padding implies a COMPLETE final group. `A=` is length 2 and `AA=` is 3,
    // so both slipped past a remainder-of-1 check while being invalid standard
    // base64 — and then failed at the provider, after the request was billed.
    if (/=/.test(payload) && payload.length % 4 !== 0) {
      throw configurationError(
        `data: image payload is padded but not a multiple of 4 (${payload.length} characters); ` +
          'padding only appears on a complete final group, so this cannot decode',
      );
    }
    if (payload.length % 4 === 1) {
      throw configurationError(
        `data: image payload is not a valid base64 length (${payload.length} characters; ` +
          'base64 encodes in groups of 4 and can never leave a remainder of 1)',
      );
    }
    return { type: 'image_url', image_url: { url: trimmed } };
  }

  if (/^https:\/\//i.test(trimmed)) {
    // PARSE it, do not prefix-match it. The old regex only checked the start,
    // so `https://example.com bad` — a whitespace-bearing string no fetcher
    // will accept — passed and failed at the provider after a billed request.
    // `new URL` is the only honest way to know a URL is a URL.
    try {
      const parsed = new URL(trimmed);
      if (parsed.protocol !== 'https:' || !parsed.hostname) {
        throw new Error('not an https URL with a host');
      }
    } catch {
      throw configurationError(
        `image URL is not a well-formed https URL: ${quote(trimmed)}. ` +
          'A stray space or a missing host is not fetchable by the model, and the request would ' +
          'be billed before the provider said so.',
      );
    }
    return { type: 'image_url', image_url: { url: trimmed } };
  }

  if (/^http:\/\//i.test(trimmed)) {
    throw configurationError(
      'plain http:// image URLs are refused: the provider would fetch the image in the clear, ' +
        'and most reject it — use https:// or an inline data:image/…;base64 URL',
    );
  }

  throw configurationError(
    'image reference must be an https:// URL or a data:image/…;base64 URL; ' +
      'a bare file path or a provider file id is not fetchable by the model',
  );
}

// ---------------------------------------------------------------------------
// Response decoding
// ---------------------------------------------------------------------------

interface RawResult {
  readonly status: number;
  readonly meta: ResponseMeta;
  readonly bytes: Uint8Array;
  readonly contentType: string | null;
  /** `Retry-After` in whole seconds, already parsed. Null when absent. */
  readonly retryAfter: number | null;
}

/** How much of a failed or unexpected body is quoted back in a message. */
const MAX_SNIPPET = 500;

function requireJson(raw: RawResult, method: string): NRouterResponse<JsonObject> {
  if (!isJsonContentType(raw.contentType)) {
    // A 2xx that is not JSON is a REAL response the caller was billed for.
    // Parsing it as JSON yields `{}` — the caller pays and receives nothing
    // while the call reports success. Refuse loudly and name the method that
    // can actually return it.
    // CONFIGURATION, not transport: the wrong METHOD was called for this
    // endpoint and no amount of retrying changes that — but every attempt is
    // billed again. A generic `if (isRetryable(err)) retry` loop around a
    // binary call would spend real credits in a tight loop.
    throw configurationError(
      `${method} received ${raw.status} with content-type ${quote(raw.contentType)}, which is not JSON. ` +
        'Use speech() or videoContent() for the binary endpoints — the JSON path would have ' +
        `reported success with an empty body. First bytes: ${quote(snippet(raw.bytes))}`,
      { status: raw.status, meta: raw.meta },
    );
  }

  const text = decodeUtf8(raw.bytes);
  let parsed: JsonValue;
  try {
    parsed = JSON.parse(text) as JsonValue;
  } catch (cause) {
    // Not an empty response — a truncated or corrupted one, for a request
    // that was billed. Distinct from the wrong-content-type case above
    // because this one CAN succeed on a retry.
    // TRANSPORT, not configuration: unlike the case above this one CAN
    // succeed on a retry — the same request can return an intact body next
    // time. The caller is billed for each attempt, which is why the message
    // says so rather than leaving a retry loop to discover it.
    throw transportError(
      `${method} received ${raw.status} with unparseable JSON (${describe(cause)}); the request was ` +
        'billed but the body did not arrive intact',
      { status: raw.status, meta: raw.meta, cause },
    );
  }

  // SDK-026 — A GUARDRAIL BLOCK ARRIVES AS HTTP 2xx, ON THIS PATH TOO.
  //
  // The gateway replaces a blocked payload with a top-level error envelope and
  // KEEPS the upstream status, and post-call guardrails apply to every JSON
  // modality — image, video, embeddings, transcription — not only to chat.
  // `chat()` already refuses this; without the same check here `nr.media.*`
  // resolved as SUCCESS and handed the caller the withheld document as if it
  // were a result. One implementation, shared from errors.ts, so the two paths
  // cannot drift.
  const envelope = errorEnvelopeOnSuccess(parsed);
  if (envelope) {
    throw createError(envelope.message, {
      code: envelope.code,
      status: raw.status,
      meta: raw.meta,
    });
  }

  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    // Left as the base `other` kind deliberately: this is a condition the
    // SDK does not recognise, and guessing it into a neighbouring class is
    // how a caller ends up handling the wrong failure forever.
    throw classifyError(
      null,
      `${method} received ${raw.status} with a JSON ${Array.isArray(parsed) ? 'array' : typeof parsed} ` +
        'where an object was expected',
      raw.status,
      { meta: raw.meta },
    );
  }

  return { body: parsed as JsonObject, meta: raw.meta };
}

function requireBinary(raw: RawResult, method: string): BinaryResult {
  if (isJsonContentType(raw.contentType)) {
    // A JSON body on a binary endpoint with a 2xx status is an error envelope
    // that lost its status code somewhere in the chain. Surfacing the text
    // beats handing back a "video file" that is really `{"error":…}`.
    // Classify on the envelope rather than raising a generic failure: a body
    // carrying one of the nine spec codes still deserves its own class even
    // when it arrived with the wrong status, so a caller's `catch
    // (nRouterGuardrailBlockedError)` keeps working.
    const envelope = parseErrorBody(safeParseJson(raw.bytes));
    throw classifyError(
      envelope.code,
      envelope.message ??
        `${method} expected binary but received ${raw.status} with content-type ` +
          `${quote(raw.contentType)}: ${quote(snippet(raw.bytes))}`,
      raw.status,
      { meta: raw.meta, retryAfter: raw.retryAfter },
    );
  }

  if (raw.bytes.length === 0) {
    // Zero bytes with a 2xx is the silent version of the failure this whole
    // module is about: a billed request that returned nothing, reported as a
    // success the caller would write to a zero-byte file.
    // TRANSPORT for the same reason as unparseable JSON above: the media may
    // arrive intact on a retry. The message states the billing consequence so
    // a retry loop is a decision rather than an accident.
    throw transportError(
      `${method} received ${raw.status} with an EMPTY body; the request was billed but no ` +
        'media arrived',
      { status: raw.status, meta: raw.meta },
    );
  }

  return { bytes: raw.bytes, contentType: raw.contentType, meta: raw.meta };
}

/**
 * Decide which of the four transcription media types came back.
 *
 * The RESPONSE content type decides, not the request: `response_format` is
 * what we asked for and the server is what happened. The requested format is
 * used only as the label when the content type is the generic `text/plain`
 * that providers commonly serve SRT and VTT under — otherwise a caller who
 * asked for `srt` and got a cue track back would see it labelled `text`.
 */
function decodeTranscription(raw: RawResult, requested: TranscriptionFormat | undefined): TranscriptionResult {
  if (isJsonContentType(raw.contentType)) {
    const decoded = requireJson(raw, 'transcribe()/translate()');
    const textField = decoded.body['text'];
    return {
      kind: 'json',
      format: requested === 'verbose_json' ? 'verbose_json' : 'json',
      body: decoded.body,
      text: typeof textField === 'string' ? textField : null,
      meta: raw.meta,
    };
  }

  const text = decodeUtf8(raw.bytes);
  if (text.length === 0) {
    throw transportError(
      `transcribe()/translate() received ${raw.status} with an EMPTY body; the request was billed ` +
        'but no transcript arrived',
      { status: raw.status, meta: raw.meta },
    );
  }

  return { kind: 'text', format: textFormatOf(raw.contentType, requested), text, meta: raw.meta };
}

function textFormatOf(
  contentType: string | null,
  requested: TranscriptionFormat | undefined,
): 'text' | 'srt' | 'vtt' {
  const type = (contentType ?? '').toLowerCase();
  if (type.includes('vtt')) return 'vtt';
  if (type.includes('srt') || type.includes('subrip')) return 'srt';
  // `text/plain` tells us nothing about which cue format it holds, so fall
  // back to what was asked for.
  if (requested === 'srt' || requested === 'vtt') return requested;
  return 'text';
}

/**
 * Build a typed error from a non-2xx response.
 *
 * Order matters and is the trap the repo's CLAUDE.md records: the gateway's
 * main error path sends `{"error":{"type":…,"message":…}}` with NO `code`, so
 * `classifyError` must be given `null` rather than a guessed code, and it
 * falls through to status and message. A bare (un-nested) object is accepted
 * too, so a proxy that reshapes the envelope does not downgrade a typed error
 * into a generic one.
 */
function gatewayError(raw: RawResult): nRouterError {
  const parsed = isJsonContentType(raw.contentType) ? safeParseJson(raw.bytes) : null;
  const envelope = parseErrorBody(parsed);

  // A non-JSON or unparseable error body still has to say something useful.
  // The capped snippet beats "JSON parse failed", which describes our reaction
  // rather than the upstream's complaint.
  let message = envelope.message;
  if (message === null || message.length === 0) {
    const body = snippet(raw.bytes);
    message = body.length > 0 ? body : `nRouter request failed with status ${raw.status}`;
  }

  return classifyError(envelope.code, message, raw.status, {
    meta: raw.meta,
    retryAfter: raw.retryAfter,
  });
}

/**
 * Parse a body as JSON, or return null.
 *
 * Returns `unknown` rather than throwing because both callers are already
 * handling a failure and a second exception raised while describing the first
 * would replace a useful gateway error with a meaningless `SyntaxError`.
 */
function safeParseJson(bytes: Uint8Array): unknown {
  try {
    return JSON.parse(decodeUtf8(bytes)) as unknown;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Request encoding
// ---------------------------------------------------------------------------

interface EncodedBody {
  readonly contentType: string;
  readonly bytes: Uint8Array;
}

interface MultipartField {
  readonly name: string;
  readonly value: string;
}

interface MultipartFile {
  readonly name: string;
  readonly fileName: string;
  readonly bytes: Uint8Array;
}

function jsonBody(fields: Record<string, JsonValue | undefined>): EncodedBody {
  const body: JsonObject = {};
  for (const key of Object.keys(fields)) {
    const value = fields[key];
    // `undefined` means "not set", and JSON has no representation for it.
    // Sending `null` instead would be a different request: several providers
    // read an explicit null as "override the default with nothing".
    if (value === undefined) continue;
    body[key] = value;
  }
  return { contentType: 'application/json', bytes: encodeUtf8(JSON.stringify(body)) };
}

/**
 * Encode a `multipart/form-data` body.
 *
 * Hand-rolled rather than delegating to `FormData` on purpose: the bytes on
 * the wire are then a deterministic function of the arguments, so the guards
 * below are provable in a unit test instead of depending on which `FormData`
 * implementation the host ships (they differ in whether they escape a
 * `Content-Disposition` parameter at all).
 */
function multipartBody(fields: ReadonlyArray<MultipartField>, file: MultipartFile): EncodedBody {
  // GUARD 1 — header injection, refused BEFORE anything is encoded.
  //
  // A MIME header parameter has NO escape for a line break, so a CR or LF in
  // a filename or a field name terminates `Content-Disposition` and every
  // byte after it is parsed as a further MIME header. Filenames routinely
  // come straight from a user upload, which makes this reachable by anyone
  // who can name a file. The Go and Swift SDKs carry the identical guard.
  for (const field of fields) {
    assertNoHeaderInjection('form field name', field.name);
    if (field.name.length === 0) {
      throw configurationError('a multipart form field name must not be empty');
    }
  }
  assertNoHeaderInjection('file name', file.fileName);

  // GUARD 2 — a real extension.
  //
  // Upstream providers select their audio decoder from the filename
  // extension, so `audio` is rejected where `speech.mp3` is accepted. The
  // rejection arrives as an opaque provider error on a billed request, which
  // is why it is worth catching locally.
  assertHasFileExtension(file.fileName);

  const parts: Uint8Array[] = [];
  const boundary = chooseBoundary(fields, file);
  const dashBoundary = `--${boundary}`;

  for (const field of fields) {
    parts.push(encodeUtf8(`${dashBoundary}\r\n`));
    parts.push(encodeUtf8(`Content-Disposition: form-data; name="${quoteParam(field.name)}"\r\n\r\n`));
    // Field VALUES need no line-break guard: they live in the body, not a
    // header, and a value that happens to contain the boundary is handled by
    // chooseBoundary above rather than by refusing legitimate multi-line
    // input such as a transcription prompt.
    parts.push(encodeUtf8(field.value));
    parts.push(encodeUtf8('\r\n'));
  }

  parts.push(encodeUtf8(`${dashBoundary}\r\n`));
  parts.push(
    encodeUtf8(
      `Content-Disposition: form-data; name="${quoteParam(file.name)}"; ` +
        `filename="${quoteParam(file.fileName)}"\r\n` +
        'Content-Type: application/octet-stream\r\n\r\n',
    ),
  );
  parts.push(file.bytes);
  parts.push(encodeUtf8('\r\n'));
  parts.push(encodeUtf8(`${dashBoundary}--\r\n`));

  return {
    contentType: `multipart/form-data; boundary=${boundary}`,
    bytes: concatBytes(parts),
  };
}

/**
 * Pick a boundary that appears in none of the parts.
 *
 * A boundary occurring inside the payload splits the body at the wrong place
 * and the upload arrives truncated — a corrupted file rather than an error.
 * Randomness alone makes that unlikely; verifying makes it impossible, and
 * the check costs one pass over bytes we are about to copy anyway.
 */
function chooseBoundary(fields: ReadonlyArray<MultipartField>, file: MultipartFile): string {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let attempt = 0; attempt < 8; attempt += 1) {
    let candidate = 'nRouterFormBoundary';
    for (let i = 0; i < 24; i += 1) {
      candidate += alphabet[Math.floor(Math.random() * alphabet.length)];
    }
    const collides =
      fields.some((field) => field.value.includes(candidate) || field.name.includes(candidate)) ||
      file.fileName.includes(candidate) ||
      containsSequence(file.bytes, encodeUtf8(candidate));
    if (!collides) return candidate;
  }
  // Eight independent 24-character collisions is not a payload, it is a
  // broken random source. Refusing beats emitting a body we know is unsafe.
  throw configurationError('could not generate a multipart boundary that does not occur in the payload');
}

function containsSequence(haystack: Uint8Array, needle: Uint8Array): boolean {
  if (needle.length === 0 || needle.length > haystack.length) return false;
  const first = needle[0];
  const limit = haystack.length - needle.length;
  outer: for (let i = 0; i <= limit; i += 1) {
    if (haystack[i] !== first) continue;
    for (let j = 1; j < needle.length; j += 1) {
      if (haystack[i + j] !== needle[j]) continue outer;
    }
    return true;
  }
  return false;
}

function assertNoHeaderInjection(label: string, value: string): void {
  if (typeof value !== 'string') {
    throw configurationError(`${label} must be a string`);
  }
  if (/[\r\n]/.test(value)) {
    throw configurationError(
      `${label} must not contain a carriage return or line feed: ${quote(value)} — a MIME header ` +
        'parameter has no escape for a line break, so it would inject further headers',
    );
  }
}

function assertHasFileExtension(fileName: string): void {
  if (fileName.trim().length === 0) {
    throw configurationError('a multipart file name is required');
  }
  if (/[/\\]/.test(fileName)) {
    // A path separator is never valid in a MIME `filename` parameter, and a
    // traversal-shaped one ("../x.mp3") reaches whatever upstream storage
    // takes the name at face value.
    throw configurationError(`file name must not contain a path separator: ${quote(fileName)}`);
  }
  if (!/^.+\.[A-Za-z0-9]{1,8}$/.test(fileName)) {
    throw configurationError(
      `file name ${quote(fileName)} has no usable extension; upstream providers pick their ` +
        'decoder from it, so "audio" is rejected where "speech.mp3" is accepted',
    );
  }
}

/**
 * Escape a value for a quoted MIME header parameter.
 *
 * Only `"` and `\` need it — line breaks cannot be escaped at all, which is
 * why they are refused above rather than encoded here. This mirrors Go's
 * `mime/multipart` escaper exactly, so the two SDKs put identical bytes on
 * the wire for the same filename.
 */
function quoteParam(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

function pushField(fields: MultipartField[], name: string, value: string | number | undefined): void {
  if (value === undefined) return;
  fields.push({ name, value: String(value) });
}

function toBytes(input: Uint8Array | ArrayBuffer, label: string): Uint8Array {
  if (input instanceof Uint8Array) {
    if (input.length === 0) {
      throw configurationError(`${label} is empty; there is nothing to transcribe`);
    }
    return input;
  }
  if (input instanceof ArrayBuffer) {
    const view = new Uint8Array(input);
    if (view.length === 0) {
      throw configurationError(`${label} is empty; there is nothing to transcribe`);
    }
    return view;
  }
  throw configurationError(`${label} must be a Uint8Array or an ArrayBuffer`);
}

function concatBytes(parts: ReadonlyArray<Uint8Array>): Uint8Array {
  let total = 0;
  for (const part of parts) total += part.length;
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Small shared helpers
// ---------------------------------------------------------------------------

/**
 * Read one header from either accepted bag shape.
 *
 * Node hands a repeated header back as an array; the first value is taken,
 * matching Go's `http.Header.Get`. Joining them would turn two content types
 * into `"audio/mpeg, application/json"`, which matches neither branch of the
 * binary-versus-JSON decision.
 */
function readHeader(source: HeaderSource, name: string): string | null {
  const bag = source as Partial<HeadersLike>;
  if (typeof bag.get === 'function') {
    const value = (source as HeadersLike).get(name);
    return typeof value === 'string' ? value : null;
  }
  const record = source as HeaderRecord;
  const wanted = name.toLowerCase();
  for (const key of Object.keys(record)) {
    if (key.toLowerCase() !== wanted) continue;
    const value = record[key];
    const first = Array.isArray(value) ? value[0] : value;
    return typeof first === 'string' ? first : null;
  }
  return null;
}

function isJsonContentType(contentType: string | null): boolean {
  if (contentType === null) return false;
  // Matches `application/json`, `application/problem+json` and the charset
  // suffixed forms, without matching `text/plain` for a body that merely
  // looks like JSON — the header is the contract, not the bytes.
  return contentType.toLowerCase().includes('json');
}

function requireNonEmpty(value: string, field: string): void {
  if (typeof value !== 'string' || value.length === 0) {
    throw configurationError(`\`${field}\` is required and must be a non-empty string`);
  }
}

/**
 * Validate and encode one URL path segment.
 *
 * An id is interpolated into the request path, so an unvalidated one carrying
 * `/`, `?` or `#` reaches a different route than the caller named — a
 * traversal into another endpoint rather than a 404.
 */
function encodePathSegment(value: string, label: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw configurationError(`${label} is required`);
  }
  if (/[\r\n]/.test(value)) {
    throw configurationError(`${label} must not contain a carriage return or line feed`);
  }
  if (/[/?#\s]/.test(value)) {
    throw configurationError(
      `${label} ${quote(value)} contains a path or query character; it would address a different endpoint`,
    );
  }
  if (value.length > 256) {
    throw configurationError(`${label} is implausibly long (${value.length} characters)`);
  }
  return encodeURIComponent(value);
}

function snippet(bytes: Uint8Array): string {
  // Decode only the capped prefix. An upstream returning a megabyte of HTML
  // on a 502 should not be pulled through a decoder in full to build a
  // message nobody reads past the first line.
  const capped = bytes.length > MAX_SNIPPET ? bytes.subarray(0, MAX_SNIPPET) : bytes;
  return decodeUtf8(capped).trim();
}

function quote(value: string | null): string {
  return value === null ? '(absent)' : JSON.stringify(value);
}

function describe(cause: unknown): string {
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

// ---------------------------------------------------------------------------
// UTF-8
// ---------------------------------------------------------------------------

/**
 * `TextEncoder`/`TextDecoder` are read off `globalThis` through a structural
 * type rather than named directly, for the same reason `meta.ts` avoids
 * naming `Headers`: this package compiles under `lib: ["ES2020"]` with no DOM
 * and no assumed Node globals, so naming them would push a type dependency
 * onto every consumer's tsconfig.
 *
 * They are required, not optional. Hand-rolling a UTF-8 codec as a fallback
 * would create a second path that no test ever exercises, and a bug in it
 * corrupts transcripts silently. Both have shipped in every browser and in
 * Node since v11.
 */
interface Utf8EncoderLike {
  encode(input: string): Uint8Array;
}

interface Utf8DecoderLike {
  decode(input: Uint8Array): string;
}

interface Utf8Globals {
  TextEncoder?: new () => Utf8EncoderLike;
  TextDecoder?: new (label?: string) => Utf8DecoderLike;
}

let cachedEncoder: Utf8EncoderLike | null = null;
let cachedDecoder: Utf8DecoderLike | null = null;

function encodeUtf8(text: string): Uint8Array {
  if (cachedEncoder === null) {
    const Ctor = (globalThis as unknown as Utf8Globals).TextEncoder;
    if (Ctor === undefined) {
      throw configurationError('this runtime has no global TextEncoder, which the nRouter SDK requires');
    }
    cachedEncoder = new Ctor();
  }
  return cachedEncoder.encode(text);
}

function decodeUtf8(bytes: Uint8Array): string {
  if (cachedDecoder === null) {
    const Ctor = (globalThis as unknown as Utf8Globals).TextDecoder;
    if (Ctor === undefined) {
      throw configurationError('this runtime has no global TextDecoder, which the nRouter SDK requires');
    }
    // Non-fatal by default: a stray malformed byte becomes U+FFFD rather than
    // throwing away an otherwise complete transcript the caller was billed for.
    cachedDecoder = new Ctor('utf-8');
  }
  return cachedDecoder.decode(bytes);
}

/**
 * Field names this SDK writes itself on a multipart upload.
 *
 * One of these arriving through `extra` would be emitted a second time, and on
 * multipart the FIRST part wins at the gateway — so the caller's own `model`
 * would lose to a stray `extra.model`, and preflight would authorize and price
 * the wrong one.
 */
const MULTIPART_RESERVED_FIELDS = new Set([
  'model',
  'language',
  'prompt',
  'temperature',
  'response_format',
  'timestamp_granularities[]',
  'file',
]);

/**
 * Drop keys whose value is `undefined`.
 *
 * An object literal treats `{ a: undefined }` as PRESENT, so spreading named
 * options over `extra` silently erases anything the caller set through the
 * escape hatch. This keeps "unset" meaning unset.
 */
function defined<T extends Record<string, unknown>>(o: T): Partial<T> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) if (v !== undefined) out[k] = v;
  return out as Partial<T>;
}
