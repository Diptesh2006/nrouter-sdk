import type { AgentEvent } from './types.js';

/** One event → one `data: …\n\n` frame in the widget wire format. */
export function encodeEvent(ev: AgentEvent): string {
  switch (ev.type) {
    case 'tool_call':
      return `data: ${JSON.stringify({
        nrouter_event: 'tool_call',
        tool: ev.tool,
        title: ev.title,
        status: ev.status
      })}\n\n`;
    case 'confidence':
      return `data: ${JSON.stringify({
        nrouter_event: 'confidence',
        level: ev.level,
        score: ev.score,
        webSearched: ev.webSearched
      })}\n\n`;
    case 'citations':
      return `data: ${JSON.stringify({
        nrouter_event: 'citations',
        citations: ev.citations.map(c => ({ title: c.title, url: c.url }))
      })}\n\n`;
    case 'token':
      return `data: ${JSON.stringify({
        choices: [{ delta: { content: ev.text } }]
      })}\n\n`;
    case 'suggestions':
      return `data: ${JSON.stringify({
        nrouter_event: 'suggestions',
        questions: ev.questions
      })}\n\n`;
    case 'action':
      return `data: ${JSON.stringify({
        nrouter_event: 'action',
        action: ev.action,
        url: ev.url,
        label: ev.label
      })}\n\n`;
    case 'cost':
      if (ev.status === 'exact') {
        const payload: any = { nrouter_event: 'cost', costUsd: ev.costUsd, status: 'exact' };
        if (ev.requestId !== undefined) payload.requestId = ev.requestId;
        return `data: ${JSON.stringify(payload)}\n\n`;
      } else {
        const payload: any = { nrouter_event: 'cost', status: 'unpriced' };
        if (ev.requestId !== undefined) payload.requestId = ev.requestId;
        return `data: ${JSON.stringify(payload)}\n\n`;
      }
    case 'error':
      return `data: ${JSON.stringify({
        nrouter_event: 'error',
        code: ev.code,
        message: ev.message
      })}\n\n`;
    case 'done':
      return 'data: [DONE]\n\n';
  }
}

/** Stream of frames ending with `data: [DONE]\n\n`. Cancel aborts via `abort`. */
export function toSSE(events: AsyncIterable<AgentEvent>, abort?: AbortController): ReadableStream<Uint8Array> {
  let iterator: AsyncIterator<AgentEvent>;
  let emittedDone = false;
  const encoder = new TextEncoder();

  return new ReadableStream({
    async start() {
      iterator = events[Symbol.asyncIterator]();
    },
    async pull(controller) {
      try {
        const result = await iterator.next();
        if (result.done) {
          if (!emittedDone) {
            emittedDone = true;
            controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          }
          controller.close();
        } else {
          const ev = result.value;
          if (ev.type === 'done') {
            emittedDone = true;
          }
          controller.enqueue(encoder.encode(encodeEvent(ev)));
        }
      } catch (err) {
        controller.enqueue(encoder.encode(encodeEvent({
          type: 'error',
          code: 'internal_error',
          message: 'Internal error'
        })));
        if (!emittedDone) {
          emittedDone = true;
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        }
        controller.close();
      }
    },
    async cancel() {
      abort?.abort();
      if (iterator && typeof iterator.return === 'function') {
        // Suppress any error that might happen when terminating the upstream generator
        await iterator.return().catch(() => {});
      }
    }
  });
}
