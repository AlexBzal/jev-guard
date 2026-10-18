// Cliente mínimo de la API de JEV Guard.

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    keepalive: method !== "GET", // una revisión enviada al cerrar la pestaña no se pierde
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const detail = data && data.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => `${(d.loc || []).slice(1).join(".") || "acción"}: ${d.msg}`).join(" · ")
      : detail || `Error ${res.status}`;
    const err = new Error(message);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  health: () => request("GET", "/health"),
  policy: () => request("GET", "/v1/policy"),
  profile: () => request("GET", "/v1/profile"),
  scenarios: () => request("GET", "/v1/scenarios"),
  metrics: () => request("GET", "/v1/metrics"),
  decisions: (limit = 40) => request("GET", `/v1/decisions?limit=${limit}`),
  decision: (id) => request("GET", `/v1/decisions/${encodeURIComponent(id)}`),
  pending: () => request("GET", "/v1/reviews/pending?limit=100"),
  review: (id, approve, reviewer, note) =>
    request("POST", `/v1/reviews/${encodeURIComponent(id)}`, { approve, reviewer, note }),
  check: (action, sandbox = false) => request("POST", `/v1/guard/check${sandbox ? "?sandbox=true" : ""}`, action),
  trafficStatus: () => request("GET", "/v1/demo/traffic"),
  traffic: (running, rate) => request("POST", "/v1/demo/traffic", { running, rate }),
  reset: () => request("DELETE", "/v1/decisions"),
};
