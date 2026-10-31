const SESSION_KEY = 'tracepilot.session_id';

export const sessionId = sessionStorage.getItem(SESSION_KEY) || crypto.randomUUID();
sessionStorage.setItem(SESSION_KEY, sessionId);

export class ApiError extends Error {
  constructor(message, { status, traceId, field }) {
    super(message);
    this.status = status;
    this.traceId = traceId;
    this.field = field;
  }
}

export async function api(path, { method = 'GET', body } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionId },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('falha de rede', { status: 0 });
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`, {
      status: response.status,
      traceId: data.trace_id || response.headers.get('X-Trace-Id'),
      field: data.field,
    });
  }
  return data;
}

/** Evento de jornada (RUM). detail aceita até 10 valores primitivos. */
export function track(type, detail = {}) {
  fetch('/rum/events', {
    method: 'POST',
    keepalive: true,
    headers: { 'Content-Type': 'application/json', 'X-Session-Id': sessionId },
    body: JSON.stringify({ session_id: sessionId, type, page: location.hash || '#/', detail }),
  }).catch(() => {});
}
