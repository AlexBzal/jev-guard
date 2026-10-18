// Vista "En vivo": ver que el sistema funciona ahora. Acción primaria: simular o detener.

import { api } from "../api.js";
import { sparkline } from "../charts.js";
import { decisionDetail, icon, metaChips, openDrawer, relTime, skeleton, term, topReason, tween, verdictBadge } from "../components.js";
import { VERDICT, companyName, compact, esc, int, ms, pct, usd } from "../format.js";
import { emit, on, store } from "../state.js";

const MAX_ITEMS = 50;
const RATES = [1, 3, 10, 25];
const SPARK_BUCKETS = 12; // 12 tramos de 5 s = último minuto
let rate = 3;

export function mount(el) {
  const demo = !!store.health?.demo;
  el.innerHTML = `
    <div class="page-head">
      <div>
        <div class="eyebrow">En vivo</div>
        <h1>Los agentes de ${esc(companyName())}, vigilados en tiempo real</h1>
        <p class="lead">Antes de cada correo, cambio en el CRM, publicación o acción propia, el agente le pregunta al guardián. Aquí ves cada decisión en el momento en que ocurre.</p>
      </div>
      <div class="controls">
        ${demo ? `
          <div class="seg" role="group" aria-label="Acciones por segundo" id="rates">${RATES.map((r) => `<button type="button" data-rate="${r}">${r}/s</button>`).join("")}</div>
          <button class="btn primary" id="traffic-btn" type="button"></button>` : ""}
      </div>
    </div>
    <div id="tiles">${skeleton.tiles(4)}</div>
    <div class="card flow" id="flow"></div>
    <div class="row small ink2" style="margin:-4px 0 16px" id="projection-row">
      <span id="projection"></span><span class="spacer"></span>
      ${demo ? `<button class="btn ghost" id="reset-btn" type="button" title="Borra el registro de la demo">${icon("trash")}Reiniciar demo</button>` : ""}
    </div>
    <div class="card feed-wrap">
      <div class="feed-head">
        <h2 style="font-size:15px;margin:0">Decisiones recientes</h2>
        <div class="seg" role="group" aria-label="Filtrar por veredicto" id="filter">
          <button type="button" data-f="all" aria-pressed="true">Todas</button>
          ${Object.entries(VERDICT).map(([k, v]) => `<button type="button" data-f="${k}" aria-pressed="false">${v.label}s</button>`).join("")}
        </div>
        <span class="spacer"></span>
        <span class="paused" id="paused" hidden>${icon("pause")}<span></span></span>
      </div>
      <div class="feed" id="feed" aria-live="off"></div>
    </div>`;

  const $ = (s) => el.querySelector(s);
  const feed = $("#feed");
  const items = [];
  let filter = "all";
  let metrics = null;
  let queue = [];
  let raf = 0;
  let hovering = false;
  const arrivals = [];

  // -- cifras -------------------------------------------------------------------------
  function buckets() {
    const now = Date.now();
    const out = new Array(SPARK_BUCKETS).fill(0);
    for (const t of arrivals) {
      const i = SPARK_BUCKETS - 1 - Math.floor((now - t) / 5000);
      if (i >= 0) out[i] += 1;
    }
    return out;
  }

  function renderTiles() {
    const m = metrics || {};
    const now = Date.now();
    while (arrivals.length && now - arrivals[0] > SPARK_BUCKETS * 5000) arrivals.shift();
    const perSec = arrivals.filter((t) => now - t <= 10000).length / 10;
    const wrap = $("#tiles");
    if (!wrap.querySelector(".tile")) {
      wrap.innerHTML = `<div class="tiles">
        <div class="card tile hero"><div class="label">Decisiones tomadas</div>
          <div class="value" id="t-dec">0</div><div class="detail" id="t-rate"></div><div id="t-spark"></div></div>
        <div class="card tile"><div class="label">Resueltas sin persona</div>
          <div class="value" id="t-auto">—</div><div class="detail" id="t-auto-d"></div></div>
        <div class="card tile"><div class="label">Latencia del guardián (p95)</div>
          <div class="value" id="t-lat">—</div><div class="detail" id="t-lat-d"></div></div>
        <div class="card tile"><div class="label">Costo acumulado de ${term("JEV", "jev")}</div>
          <div class="value" id="t-cost">—</div><div class="detail" id="t-cost-d"></div></div>
      </div>`;
    }
    tween($("#t-dec"), m.decisions || 0, int);
    $("#t-rate").textContent = perSec ? `${perSec.toLocaleString("es-CO", { maximumFractionDigits: 1 })} por segundo ahora` : "en espera de acciones";
    const sparkEl = $("#t-spark");
    sparkEl.innerHTML = sparkline(buckets(), Math.max(120, sparkEl.clientWidth || 260), 34, { label: "Decisiones cada 5 segundos en el último minuto" });
    $("#t-auto").textContent = pct(m.automation_rate);
    $("#t-auto-d").textContent = m.decisions ? `${int(m.pending_review || 0)} esperan a una persona` : "—";
    $("#t-lat").textContent = ms(m.latency_ms?.p95);
    $("#t-lat-d").textContent = m.decisions ? `p50 ${ms(m.latency_ms?.p50)}` : "—";
    $("#t-cost").textContent = usd(m.cost_usd);
    $("#t-cost-d").textContent = m.decisions ? `con un LLM como juez: ${usd(m.llm_judge_cost_usd)}` : "—";
    renderFlow();
    renderProjection();
  }

  function renderFlow() {
    const m = metrics || {};
    const n = m.decisions || 0;
    const r = m.by_route || {};
    const v = m.by_verdict || {};
    const step = (num, title, value, detail, key) => `<div class="flow-step">
      <div class="k"><span class="n">${num}</span><b>${key ? term(title, key) : esc(title)}</b></div>
      <div class="v">${value}</div><div class="d">${detail}</div></div>`;
    const share = (x) => (n ? pct(x / n) : "—");
    const bar = n ? `<div class="splitbar" role="img" aria-label="${esc(`Permitidas ${int(v.allow || 0)}, retenidas ${int(v.hold || 0)}, frenadas ${int(v.block || 0)}`)}">
        ${["allow", "hold", "block"].map((k) => `<span class="${k}" style="flex-grow:${v[k] || 0}" data-tip="${esc(`${VERDICT[k].label}s: ${int(v[k] || 0)} (${share(v[k] || 0)})`)}"></span>`).join("")}
      </div>` : '<div class="splitbar"></div>';
    $("#flow").innerHTML = `
      ${step(1, "Agentes", int(n), "acciones propuestas")}
      ${step(2, "Reglas", int(r.rules || 0), `${share(r.rules || 0)} resueltas sin llamar a JEV`, "reglas")}
      ${step(3, "JEV", int(r.jev || 0), `${share(r.jev || 0)} decididas solo`, "jev")}
      ${step(4, "LLM", int(r.llm || 0), r.llm ? `${share(r.llm)} con segunda opinión` : "sin LLM configurado")}
      <div class="flow-step">
        <div class="k"><span class="n">5</span><b>Veredicto</b></div>
        <div class="v">${int(v.allow || 0)} <span class="small ink2">permitidas</span></div>
        ${bar}
      </div>`;
  }

  function renderProjection() {
    const p = $("#projection");
    const perDay = rate * 86400;
    const perDecision = metrics?.decisions ? metrics.cost_usd / metrics.decisions : null;
    const llmPer = metrics?.decisions ? metrics.llm_judge_cost_usd / metrics.decisions : null;
    p.innerHTML = !demo ? "" : perDecision
      ? `A ${rate}/s son <b>${compact(perDay)}</b> decisiones al día: unos <b>${usd(perDay * perDecision)}</b> con JEV, frente a ${usd(perDay * llmPer)} con un LLM juez.`
      : `A ${rate}/s serían ${compact(perDay)} decisiones al día.`;
  }

  async function loadMetrics() {
    try { metrics = await api.metrics(); renderTiles(); } catch (e) { /* reintenta */ }
  }

  // -- flujo de decisiones ---------------------------------------------------------------
  function itemHtml(it, fresh) {
    const d = it.decision;
    const resolved = it.final ? `<div class="resolved">Resuelta por una persona: ${verdictBadge(it.final)}</div>` : "";
    return `<button class="feed-item${fresh ? " enter" : ""}" type="button" data-id="${esc(d.decision_id)}">
      <div>${verdictBadge(d.verdict)}</div>
      <div style="min-width:0">
        <div class="title">${esc(d.summary || d.action_type)}</div>
        <div class="why">${esc(topReason(d))}</div>
        <div class="meta">${metaChips(d)}</div>${resolved}
      </div>
      <div class="lat">${ms(d.latency_ms)}<small data-rel="${esc(d.created_at)}">${relTime(d.created_at)}</small></div>
    </button>`;
  }

  function emptyHtml() {
    if (items.length) return `<div class="empty">No hay decisiones con ese veredicto.</div>`;
    return `<div class="empty"><strong>Todavía no hay decisiones</strong>
      ${demo ? "Arranca a los agentes simulados para ver al guardián trabajar." : "Conecta un agente con <code>POST /v1/guard/check</code>."}
      ${demo ? `<div><button class="btn primary" type="button" data-start>${icon("play")}Simular agentes</button></div>` : ""}</div>`;
  }

  function renderFeed(freshIds = new Set()) {
    const shown = items.filter((it) => filter === "all" || it.decision.verdict === filter);
    feed.innerHTML = shown.length ? shown.map((it) => itemHtml(it, freshIds.has(it.decision.decision_id))).join("") : emptyHtml();
  }

  function setPausedNote() {
    const note = $("#paused");
    note.hidden = !(hovering && queue.length);
    note.lastElementChild.textContent = `En pausa mientras lees: ${queue.length} nueva${queue.length === 1 ? "" : "s"}`;
  }

  function flush() {
    raf = 0;
    if (hovering) { setPausedNote(); return; }
    const fresh = new Set(queue.map((d) => d.decision_id));
    for (const d of queue) items.unshift({ decision: d, final: null });
    queue = [];
    items.splice(MAX_ITEMS);
    renderFeed(fresh);
    setPausedNote();
  }

  feed.addEventListener("mouseenter", () => { hovering = true; });
  feed.addEventListener("mouseleave", () => { hovering = false; if (queue.length && !raf) raf = requestAnimationFrame(flush); });
  feed.addEventListener("click", async (e) => {
    if (e.target.closest("[data-start]")) { toggleTraffic(true); return; }
    const btn = e.target.closest(".feed-item");
    if (!btn) return;
    try {
      const row = await api.decision(btn.dataset.id);
      openDrawer(decisionDetail(row), (body) => {
        body.querySelector("[data-open-lab]")?.addEventListener("click", () => emit("open-lab", row.action));
      });
    } catch (err) { emit("toast", err.message); }
  });

  $("#filter").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-f]");
    if (!b) return;
    filter = b.dataset.f;
    el.querySelectorAll("#filter button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderFeed();
  });

  // -- controles de la demo ------------------------------------------------------------------
  function renderTraffic(running) {
    const btn = $("#traffic-btn");
    if (!btn) return;
    btn.dataset.running = running ? "1" : "";
    btn.innerHTML = running ? `${icon("stop")}Detener agentes <kbd>Espacio</kbd>` : `${icon("play")}Simular agentes <kbd>Espacio</kbd>`;
    el.querySelectorAll("[data-rate]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.rate) === rate)));
  }

  async function toggleTraffic(force) {
    const running = force ?? !$("#traffic-btn")?.dataset.running;
    try {
      const st = await api.traffic(running, rate);
      store.health.traffic = st;
      renderTraffic(st.running);
    } catch (err) { emit("toast", err.message); }
  }

  if (demo) {
    if (RATES.includes(store.health?.traffic?.rate)) rate = store.health.traffic.rate;
    renderTraffic(store.health?.traffic?.running);
    $("#traffic-btn").addEventListener("click", () => toggleTraffic());
    $("#rates").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-rate]");
      if (!b) return;
      rate = Number(b.dataset.rate);
      if ($("#traffic-btn").dataset.running) await toggleTraffic(true);
      renderTraffic(!!$("#traffic-btn").dataset.running);
      renderProjection();
    });
    $("#reset-btn").addEventListener("click", async () => {
      if (!confirm("¿Borrar todas las decisiones de la demo?")) return;
      try { await api.reset(); } catch (err) { emit("toast", err.message); }
    });
  }

  async function syncTraffic() {
    if (!demo) return;
    try {
      const st = await api.trafficStatus();
      if (store.health) store.health.traffic = st;
      renderTraffic(st.running);
    } catch (e) { /* reintenta */ }
  }

  // -- datos iniciales y suscripciones -----------------------------------------------------------
  feed.innerHTML = `<div style="padding:16px">${skeleton.lines(5)}</div>`;
  api.decisions(MAX_ITEMS).then((rows) => {
    for (const r of rows) {
      items.push({ decision: r.decision, final: r.decision.verdict === "hold" && r.status === "final" ? r.final_verdict : null });
    }
    renderFeed();
  }).catch(() => renderFeed());
  loadMetrics();

  const offs = [
    on("decision", (ev) => {
      queue.push(ev.decision);
      arrivals.push(Date.now());
      if (metrics) metrics.decisions = (metrics.decisions || 0) + 1;
      if (!raf) raf = requestAnimationFrame(flush);
    }),
    on("review", (ev) => {
      const it = items.find((x) => x.decision.decision_id === ev.decision_id);
      if (it) { it.final = ev.final_verdict; renderFeed(); }
    }),
    on("reset", () => { items.length = 0; queue = []; arrivals.length = 0; renderFeed(); loadMetrics(); }),
    on("key", (e) => { if (e.key === " " && demo) { e.preventDefault(); toggleTraffic(); } }),
  ];
  const timer = setInterval(() => { loadMetrics(); syncTraffic(); }, 2000);
  const tick = setInterval(() => {
    renderTiles();
    feed.querySelectorAll("[data-rel]").forEach((s) => { s.textContent = relTime(s.dataset.rel); });
  }, 1000);

  return () => {
    offs.forEach((off) => off());
    clearInterval(timer);
    clearInterval(tick);
    if (raf) cancelAnimationFrame(raf);
  };
}
