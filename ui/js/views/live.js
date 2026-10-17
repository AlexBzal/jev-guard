// Vista "En vivo": decisiones en tiempo real, indicadores y control de los agentes simulados.

import { api } from "../api.js";
import { decisionDetail, icon, metaChips, openDrawer, topReason, verdictBadge } from "../components.js";
import { VERDICT, clock, compact, esc, int, ms, pct, usd } from "../format.js";
import { emit, on, store } from "../state.js";

const MAX_ITEMS = 60;
const RATES = [1, 3, 10, 25];
let rate = 3;

export function mount(el) {
  const demo = !!store.health?.demo;
  el.innerHTML = `
    <div class="page-head">
      <div>
        <h1>Los agentes de 30X, vigilados en tiempo real</h1>
        <p>Cada vez que un agente quiere enviar un correo, tocar el CRM o publicar, JEV Guard decide en milisegundos si puede hacerlo. Lo dudoso pasa a un LLM o a una persona.</p>
      </div>
    </div>
    <div class="tiles" id="tiles"></div>
    <div class="controls card" style="padding:12px 16px">
      ${demo ? `
        <button class="btn primary" id="traffic-btn" type="button"></button>
        <div class="seg" role="group" aria-label="Acciones por segundo">${RATES.map((r) => `<button type="button" data-rate="${r}">${r}/s</button>`).join("")}</div>
        <span class="projection" id="projection"></span>
        <span class="spacer"></span>
        <button class="btn" id="reset-btn" type="button" title="Borra el registro de la demo">${icon("trash")}Reiniciar</button>`
      : `<span class="projection">Conecta a tus agentes con <code>POST /v1/guard/check</code>. Para la simulación integrada, arranca el servidor con <code>JEV_GUARD_DEMO=1</code>.</span>`}
    </div>
    <div class="row" style="margin-bottom:10px">
      <div class="seg" role="group" aria-label="Filtrar por veredicto" id="filter">
        <button type="button" data-f="all" aria-pressed="true">Todas</button>
        ${Object.entries(VERDICT).map(([k, v]) => `<button type="button" data-f="${k}" aria-pressed="false">${v.label}s</button>`).join("")}
      </div>
      <span class="muted small" id="feed-note"></span>
    </div>
    <div class="feed" id="feed"><div class="card empty">Todavía no hay decisiones. ${demo ? "Pulsa «Simular agentes» para empezar." : ""}</div></div>`;

  const feed = el.querySelector("#feed");
  const items = []; // {decision, final}
  let filter = "all";
  let metrics = null;
  let queue = [];
  let raf = 0;
  const arrivals = [];

  // -- indicadores ------------------------------------------------------------
  function renderTiles() {
    const m = metrics || {};
    const now = Date.now();
    while (arrivals.length && now - arrivals[0] > 10000) arrivals.shift();
    const perSec = arrivals.length / 10;
    el.querySelector("#tiles").innerHTML = `
      <div class="card tile hero"><div class="label">Decisiones tomadas</div>
        <div class="value">${int(m.decisions || 0)}</div>
        <div class="detail">${perSec ? `${perSec.toLocaleString("es-CO", { maximumFractionDigits: 1 })} por segundo ahora mismo` : "en espera de acciones"}</div></div>
      <div class="card tile"><div class="label">Resueltas sin persona</div>
        <div class="value">${pct(m.automation_rate)}</div>
        <div class="detail">${m.decisions ? `reglas ${pct(m.resolved_by_rules_rate)} · el resto JEV o LLM` : "—"}</div></div>
      <div class="card tile"><div class="label">Latencia del guardián (p95)</div>
        <div class="value">${ms(m.latency_ms?.p95)}</div>
        <div class="detail">p50 ${ms(m.latency_ms?.p50)}</div></div>
      <div class="card tile"><div class="label">Costo acumulado de JEV</div>
        <div class="value">${usd(m.cost_usd)}</div>
        <div class="detail">con un LLM como juez: ${usd(m.llm_judge_cost_usd)}</div></div>
      <div class="card tile"><div class="label">Esperan a una persona</div>
        <div class="value">${int(m.pending_review || 0)}</div>
        <div class="detail"><a href="#/bandeja">Ir a la bandeja</a></div></div>`;
    renderProjection();
  }

  function renderProjection() {
    const p = el.querySelector("#projection");
    if (!p) return;
    const perDay = rate * 86400;
    const perDecision = metrics?.decisions ? metrics.cost_usd / metrics.decisions : null;
    const llmPer = metrics?.decisions ? metrics.llm_judge_cost_usd / metrics.decisions : null;
    p.innerHTML = perDecision
      ? `A ${rate}/s son <b>${compact(perDay)}</b> decisiones al día: unos <b>${usd(perDay * perDecision)}</b> con JEV, frente a ${usd(perDay * llmPer)} con un LLM juez.`
      : `A ${rate}/s serían ${compact(perDay)} decisiones al día.`;
  }

  async function loadMetrics() {
    try { metrics = await api.metrics(); renderTiles(); } catch (e) { /* reintenta */ }
  }

  // -- flujo --------------------------------------------------------------------
  function itemHtml(it, fresh) {
    const d = it.decision;
    const resolved = it.final
      ? `<div class="resolved">Resuelta por una persona: ${verdictBadge(it.final)}</div>` : "";
    return `<button class="feed-item${fresh ? " enter" : ""}" type="button" data-id="${esc(d.decision_id)}">
      <div>${verdictBadge(d.verdict)}</div>
      <div style="min-width:0">
        <div class="title">${esc(d.summary || d.action_type)}</div>
        <div class="why">${esc(topReason(d))}</div>
        <div class="meta">${metaChips(d)}</div>${resolved}
      </div>
      <div class="lat">${ms(d.latency_ms)}<small>${clock(d.created_at)}</small></div>
    </button>`;
  }

  function renderFeed(freshIds = new Set()) {
    const shown = items.filter((it) => filter === "all" || it.decision.verdict === filter);
    feed.innerHTML = shown.length
      ? shown.map((it) => itemHtml(it, freshIds.has(it.decision.decision_id))).join("")
      : `<div class="card empty">No hay decisiones ${filter === "all" ? "todavía" : "con ese veredicto"}.</div>`;
    el.querySelector("#feed-note").textContent = items.length ? `Últimas ${items.length} decisiones` : "";
  }

  function flush() {
    raf = 0;
    const fresh = new Set(queue.map((d) => d.decision_id));
    for (const d of queue) items.unshift({ decision: d, final: null });
    queue = [];
    items.splice(MAX_ITEMS);
    renderFeed(fresh);
  }

  feed.addEventListener("click", async (e) => {
    const btn = e.target.closest(".feed-item");
    if (!btn) return;
    try {
      const row = await api.decision(btn.dataset.id);
      openDrawer(decisionDetail(row), (body) => {
        body.querySelector("[data-open-lab]")?.addEventListener("click", () => emit("open-lab", row.action));
      });
    } catch (err) { emit("toast", err.message); }
  });

  el.querySelector("#filter").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    filter = b.dataset.f;
    el.querySelectorAll("#filter button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderFeed();
  });

  // -- controles de la demo ---------------------------------------------------------
  function renderTraffic(running) {
    const btn = el.querySelector("#traffic-btn");
    if (!btn) return;
    btn.dataset.running = running ? "1" : "";
    btn.innerHTML = running ? `${icon("stop")}Detener agentes` : `${icon("play")}Simular agentes`;
    el.querySelectorAll("[data-rate]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.rate) === rate)));
  }

  if (demo) {
    if (RATES.includes(store.health?.traffic?.rate)) rate = store.health.traffic.rate;
    renderTraffic(store.health?.traffic?.running);
    el.querySelector("#traffic-btn").addEventListener("click", async (e) => {
      const running = !e.currentTarget.dataset.running;
      try {
        const st = await api.traffic(running, rate);
        store.health.traffic = st;
        renderTraffic(st.running);
      } catch (err) { emit("toast", err.message); }
    });
    el.querySelector(".seg[aria-label='Acciones por segundo']").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-rate]");
      if (!b) return;
      rate = Number(b.dataset.rate);
      const running = !!el.querySelector("#traffic-btn").dataset.running;
      if (running) { try { store.health.traffic = await api.traffic(true, rate); } catch (err) { emit("toast", err.message); } }
      renderTraffic(running);
      renderProjection();
    });
    el.querySelector("#reset-btn").addEventListener("click", async () => {
      if (!confirm("¿Borrar todas las decisiones de la demo?")) return;
      try { await api.reset(); } catch (err) { emit("toast", err.message); }
    });
  }

  // -- datos iniciales y suscripciones ----------------------------------------------
  api.decisions(MAX_ITEMS).then((rows) => {
    for (const r of rows) {
      items.push({ decision: r.decision, final: r.decision.verdict === "hold" && r.status === "final" ? r.final_verdict : null });
    }
    renderFeed();
  }).catch(() => {});
  loadMetrics();

  const offs = [
    on("decision", (ev) => {
      queue.push(ev.decision);
      arrivals.push(Date.now());
      if (metrics) { metrics.decisions = (metrics.decisions || 0) + 1; }
      if (!raf) raf = requestAnimationFrame(flush);
    }),
    on("review", (ev) => {
      const it = items.find((x) => x.decision.decision_id === ev.decision_id);
      if (it) { it.final = ev.final_verdict; renderFeed(); }
    }),
    on("reset", () => { items.length = 0; queue = []; renderFeed(); loadMetrics(); }),
  ];
  const timer = setInterval(loadMetrics, 2000);
  const tick = setInterval(renderTiles, 1000);

  return () => {
    offs.forEach((off) => off());
    clearInterval(timer);
    clearInterval(tick);
    if (raf) cancelAnimationFrame(raf);
  };
}

