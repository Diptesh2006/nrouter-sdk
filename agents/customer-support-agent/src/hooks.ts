import type { SupportAgentHooks } from './types.js';

type HookName = Exclude<keyof SupportAgentHooks, 'onError'>;

/** Call a hook without ever throwing or blocking the caller; failures go to onError. */
export function callHook<K extends HookName>(
  hooks: SupportAgentHooks,
  name: K,
  payload: Parameters<NonNullable<SupportAgentHooks[K]>>[0],
): void {
  const hook = hooks[name];
  if (!hook) return;

  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Promise.resolve((hook as any)(payload)).catch(() => {
      reportError(hooks, name);
    });
  } catch (err) {
    reportError(hooks, name);
  }
}

function reportError(hooks: SupportAgentHooks, name: string) {
  if (hooks.onError) {
    try {
      hooks.onError({ code: 'internal_error', message: `hook ${name} failed` });
    } catch (e) {
      // ignore
    }
  }
}
