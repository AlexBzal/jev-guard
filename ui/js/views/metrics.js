// Vista "Métricas": cómo se sabe si el guardián funciona.

import { api } from "../api.js";
import { columns, hbars, stacked, tableView } from "../charts.js";
import { skeleton } from "../components.js";
import { ROUTE, actionTypeLabel, dec, esc, int, ms, pct, usd } from "../format.js";
import { on, store } from "../state.js";

const VERDICT_KEYS = [
  { key: "allow", label: "Permitida", cls: "seg-allow", color: "good", icon: "check" },
  { key: "hold", label: "Retenida", cls: "seg-hold", color: "warning", icon: "pause" },
  { key: "block", label: "Frenada", cls: "seg-block", color: "critical", icon: "x" },
];

function binLabel(b) {
  if (b.to == null) return `≥${int(b.from)}`;
  return b.from === 0 ? `<${int(b.to)}` : `${int(b.from)}–${int(b.to)}`;
}

export function mount(el) {
  el.innerHTML = `
    <div class="page-head">
      <div>
        <div class="eyebrow">Métricas</div>
        <h1>¿Podemos confiar en el guardián?</h1>
        <p class="lead">La calidad se mide contra etiquetas: las revisiones de la Bandeja, la auditoría de una muestra de decisiones automáticas y, en la demo, la etiqueta de cada caso simulado.</p>
      </div>
    </div>
    <div id="m-body">${skeleton.card(70)}<div style="height:16px"></div>${skeleton.tiles(4)}${skeleton.card(220)}</div>`;

  const body = el.querySelector("#m-body");
  let data = null;

  function tile(label, value, detail, cls = "") {
    return `<div class="card tile"><div class="label">${esc(label)}</div><div class="value ${cls}">${value}</div><div class="detail">${detail}</div></div>`;
  }

  function render() {
    const m = data;
    if (!m || !m.decisions) {
      body.innerHTML = `<div class="card empty">Aún no hay decisiones. Arranca la simulación en «En vivo» o conecta a un agente.</div>`;
      return;
    }
    const q = m.quality || {};

    const routeRows = ["rules", "jev", "llm", "human"].map((k) => {
      const n = m.by_route?.[k] || 0;
      return { label: ROUTE[k].label, value: n, display: `${int(n)} · ${pct(n / m.decisions)}`, tip: `${ROUTE[k].long}: ${int(n)} (${pct(n / m.decisions)})` };
    });
    const bins = (m.latency_hist || []).map((b) => ({ label: binLabel(b), value: b.count, tip: `${binLabel(b)} ms: ${int(b.count)} decisiones` }));
    const typeRows = Object.keys(m.by_type_verdict || {})
      .map((t) => ({ label: actionTypeLabel(t), values: m.by_type_verdict[t] }));

    const jevPer1000 = m.cost_per_1000_usd;
    const llmPer1000 = m.llm_judge_cost_per_1000_usd;

    const caught = q.unsafe ? `De <b>${int(q.unsafe)}</b> acciones inseguras etiquetadas, el guardián detuvo <b>${pct(q.unsafe_caught)}</b>` : "Todavía no hay acciones inseguras etiquetadas";
    const fa = q.unsafe ? ` y <b>${int(q.false_allow)}</b> ${q.false_allow === 1 ? "pasó sola" : "pasaron solas"}.` : ".";
    const fb = q.false_block_rate != null ? ` Frenó por error el <b>${pct(q.false_block_rate)}</b> de las seguras.` : "";
    const cost = m.cost_per_1000_usd != null ? ` Cada 1.000 decisiones cuestan <b>${usd(m.cost_per_1000_usd)}</b>.` : "";
    body.innerHTML = `
      <div class="card" style="margin-bottom:16px"><p class="headline">${caught}${fa}${fb}${cost}</p>
        ${m.simulated_jev ? '<p class="small muted" style="margin:8px 0 0">Con JEV simulado, estas cifras miden las heurísticas locales, no a JEV. La latencia no incluye la red.</p>' : ""}</div>
      <div class="tiles five">
        ${tile("Inseguras detenidas", pct(q.unsafe_caught), `de ${int(q.unsafe)} inseguras etiquetadas`)}
        ${tile("Inseguras que pasaron solas", int(q.false_allow), "la métrica que más importa", q.false_allow === 0 ? "good" : "")}
        ${tile("Seguras frenadas por error", pct(q.false_block_rate), "falsos bloqueos")}
        ${tile("Precisión de la bandeja", pct(q.review_precision), "de lo retenido, cuánto era riesgoso")}
        ${tile("Aciertos automáticos", pct(q.auto_accuracy), `${int(q.labeled)} decisiones etiquetadas`)}
      </div>
      <div class="grid cols-2">
        <div class="card">
          <h2>Costo por cada 1.000 decisiones</h2>
          <p class="sub">El mismo trabajo hecho por un LLM como juez en cada acción. Estimado con los tokens reales de cada llamada.</p>
          <div class="compare">
            <div class="side"><div class="v">${usd(jevPer1000)}</div><div class="l">JEV</div></div>
            <div class="x">frente a</div>
            <div class="side"><div class="v">${usd(llmPer1000)}</div><div class="l">LLM como juez</div></div>
            <div class="ratio">${m.savings_factor ? `JEV cuesta <b>${int(m.savings_factor)} veces menos</b>` : ""}${m.llm_escalation_rate ? ` · solo el ${pct(m.llm_escalation_rate, 1)} de las acciones llegó al LLM` : ""}</div>
          </div>
        </div>
        <div class="card">
          <h2>¿Quién decidió?</h2>
          <p class="sub">${pct(m.automation_rate)} se resolvió sin una persona.</p>
          <div data-chart="route"></div>
          ${tableView(["Ruta", "Decisiones", "Porcentaje"], routeRows.map((r) => [r.label, int(r.value), pct(r.value / m.decisions)]))}
        </div>
        <div class="card">
          <h2>Latencia del guardián</h2>
          <p class="sub">Decisiones por rango de milisegundos. p50 ${ms(m.latency_ms?.p50)} · p95 ${ms(m.latency_ms?.p95)} · p99 ${ms(m.latency_ms?.p99)}</p>
          <div data-chart="latency"></div>
          ${tableView(["Rango (ms)", "Decisiones"], bins.map((b) => [b.label, int(b.value)]))}
        </div>
        <div class="card">
          <h2>Veredictos por tipo de acción</h2>
          <p class="sub">${int(m.decisions)} decisiones en total.</p>
          <div data-chart="types"></div>
          ${tableView(["Tipo", ...VERDICT_KEYS.map((k) => k.label)], typeRows.map((r) => [r.label, ...VERDICT_KEYS.map((k) => int(r.values[k.key] || 0))]))}
        </div>
      </div>
      <div class="card" style="margin-top:16px">
        <h2>Operación</h2>
        <div class="facts">
          <span>Decisiones <b>${int(m.decisions)}</b></span>
          <span>Llamadas a JEV <b>${int(m.jev_calls)}</b></span>
          <span>Resueltas por reglas sin llamar a JEV <b>${pct(m.resolved_by_rules_rate)}</b></span>
          <span>Tokens de entrada <b>${int(m.input_tokens)}</b></span>
          <span>Tokens por llamada <b>${int(m.jev_calls ? m.input_tokens / m.jev_calls : 0)}</b></span>
          <span>Costo total <b>${usd(m.cost_usd)}</b></span>
          <span>Pendientes de revisión <b>${int(m.pending_review)}</b></span>
          <span>Latencia de JEV p50 / p95 <b>${ms(m.jev_latency_ms?.p50)} / ${ms(m.jev_latency_ms?.p95)}</b></span>
          <span>Umbral de frenado en impacto crítico <b>${dec(store.policy?.policy?.tiers?.critical?.block)}</b></span>
        </div>
      </div>`;

    const cw = (sel) => Math.max(260, body.querySelector(sel).clientWidth || 320);
    body.querySelector('[data-chart="route"]').innerHTML = hbars(routeRows, cw('[data-chart="route"]'), { labelWidth: 80 });
    body.querySelector('[data-chart="latency"]').innerHTML = columns(bins, cw('[data-chart="latency"]'));
    body.querySelector('[data-chart="types"]').innerHTML = stacked(typeRows, VERDICT_KEYS, cw('[data-chart="types"]'));
  }

  async function load() {
    try { data = await api.metrics(); render(); } catch (e) { body.innerHTML = `<div class="card empty error">${esc(e.message)}</div>`; }
  }

  // Los <details> de tabla abiertos se conservan entre refrescos.
  function refresh() {
    const open = [...body.querySelectorAll("details.table-view")].map((d) => d.open);
    load().then(() => body.querySelectorAll("details.table-view").forEach((d, i) => { d.open = !!open[i]; }));
  }

  let lastWidth = 0;
  const ro = new ResizeObserver(([entry]) => {
    const wNow = Math.round(entry.contentRect.width);
    if (wNow === lastWidth) return; // solo el ancho cambia la geometría de los gráficos
    lastWidth = wNow;
    if (data) render();
  });
  ro.observe(body);
  const timer = setInterval(refresh, 4000);
  const off = on("reset", load);
  load();
  return () => { clearInterval(timer); ro.disconnect(); off(); };
}
