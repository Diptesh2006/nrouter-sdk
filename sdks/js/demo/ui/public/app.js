'use strict';

const statusEl = document.getElementById('status');
const outputEl = document.getElementById('output');
const modelsEl = document.getElementById('models');
const form = document.getElementById('chatForm');
const modelInput = document.getElementById('model');

function setStatus(kind, text) {
  statusEl.className = `status ${kind || ''}`.trim();
  statusEl.querySelector('span:last-child').textContent = text;
}

function write(value) {
  outputEl.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { 'content-type': 'application/json', ...(options.headers || {}) },
  });
  const body = await res.json();
  if (!res.ok) {
    throw body;
  }
  return body;
}

function bodyFromForm() {
  return {
    model: modelInput.value,
    systemPrompt: document.getElementById('systemPrompt').value,
    prompt: document.getElementById('prompt').value,
    maxTokens: Number.parseInt(document.getElementById('maxTokens').value, 10),
  };
}

async function runButton(button, fn) {
  const old = button.textContent;
  button.disabled = true;
  button.textContent = 'Running...';
  try {
    const result = await fn();
    setStatus('ok', 'Last request succeeded');
    write(result);
  } catch (error) {
    setStatus('bad', 'Last request failed');
    write(error);
  } finally {
    button.disabled = false;
    button.textContent = old;
  }
}

document.getElementById('healthBtn').addEventListener('click', (event) => {
  runButton(event.currentTarget, async () => {
    const health = await api('/api/health');
    setStatus(health.hasKey ? 'ok' : 'bad', health.hasKey ? 'API key loaded on server' : 'API key missing on server');
    return health;
  });
});

document.getElementById('modelsBtn').addEventListener('click', (event) => {
  runButton(event.currentTarget, async () => {
    const result = await api('/api/models');
    modelsEl.className = 'list';
    modelsEl.textContent = '';
    for (const model of result.models) {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'modelItem';
      item.textContent = model.id;
      item.addEventListener('click', () => {
        modelInput.value = model.id;
      });
      modelsEl.appendChild(item);
    }
    return result;
  });
});

form.addEventListener('submit', (event) => {
  event.preventDefault();
  runButton(event.submitter, () =>
    api('/api/chat', {
      method: 'POST',
      body: JSON.stringify(bodyFromForm()),
    }),
  );
});

document.getElementById('messagesBtn').addEventListener('click', (event) => {
  runButton(event.currentTarget, () =>
    api('/api/messages', {
      method: 'POST',
      body: JSON.stringify(bodyFromForm()),
    }),
  );
});

document.getElementById('guardrailBtn').addEventListener('click', (event) => {
  runButton(event.currentTarget, () =>
    api('/api/guardrail-check', {
      method: 'POST',
      body: '{}',
    }),
  );
});

document.getElementById('healthBtn').click();
