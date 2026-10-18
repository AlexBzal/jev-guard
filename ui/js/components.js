// Componentes reutilizables (devuelven HTML como texto; todo dato pasa por esc()).

import { ROUTE, SEVERITY, SOURCE, TIER, VERDICT, actionTypeLabel, agentName, dec, esc, ms, pct, usd } from "./format.js";
import { questionFor, tierPolicy } from "./state.js";

const ICONS = {
  check: '<path d="m5 12 5 5 9-10" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>',
  x: '<path d="M7 7l10 10M17 7 7 17" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>',
  pause: '<path d="M9 6v12M15 6v12" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round"/>',
  sun: '<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  auto: '<circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor"/>',
  play: '<path d="M8 5v14l11-7Z" fill="currentColor"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  flask: '<path d="M9 3h6M10 3v6L5 19a1.5 1.5 0 0 0 1.3 2h11.4A1.5 1.5 0 0 0 19 19l-5-10V3" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  pulse: '<path d="M3 12h4l2-6 4 12 2-6h6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  inbox: '<path d="M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5M4 13l2.5-7h11L20 13M4 13h4.5l1 2h5l1-2H20" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  chevron: '<path d="m9 6 6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  sparkle: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
};

// Glosario: los términos propios del sistema se explican la primera vez que aparecen.
export const GLOSSARY = {
  jev: "JEV es el modelo de TypeSafe AI que responde preguntas tipadas (sí/no, escala u opciones) en milisegundos, con una probabilidad calibrada.",
  impacto: "Cuántas personas o registros afecta la acción y si se puede deshacer. A mayor impacto, umbrales más estrictos.",
  certeza: "Qué tan seguro está JEV de su respuesta, de 0 a 1. Con poca certeza, el guardián no actúa solo: escala.",
  riesgo: "Combinación de todas las señales de JEV, de 0 a 1. Se compara con los umbrales de retener y frenar del impacto de la acción.",
  retenida: "La acción espera en la Bandeja a que una persona la apruebe o la rechace.",
  reglas: "Comprobaciones exactas en código, antes de JEV: listas de baja, horarios, permisos, secretos y formato.",
};

/** Un término con su definición en tooltip y para lectores de pantalla. */
export function term(text, key) {
  const def = GLOSSARY[key] || "";
  return `<span class="term" tabindex="0" data-tip="${esc(def)}" aria-label="${esc(`${text}: ${def}`)}">${esc(text)}</span>`;
}

/** Esqueletos: reservan el espacio con la forma del contenido que va a llegar. */
export const skeleton = {
  lines: (n = 3) => Array.from({ length: n }, (_, i) => `<div class="sk sk-line" style="width:${92 - i * 14}%"></div>`).join(""),
  tiles: (n = 4) => `<div class="tiles">${'<div class="sk sk-block"></div>'.repeat(n)}</div>`,
  card: (h = 180) => `<div class="card"><div class="sk" style="height:${h}px;border-radius:10px"></div></div>`,
};

/** Anima un número desde su valor actual hasta `to`, respetando el movimiento reducido. */
export function tween(el, to, format, ms = 450) {
  if (!el) return;
  const from = Number(el.dataset.value ?? to);
  el.dataset.value = String(to);
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduced || from === to || !Number.isFinite(from) || !Number.isFinite(to)) { el.textContent = format(to); return; }
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / ms);
    const e = 1 - (1 - k) ** 3;
    el.textContent = format(from + (to - from) * e);
    if (k < 1 && el.dataset.value === String(to)) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Tiempo relativo en español: "hace 5 s", "hace 3 min". */
export function relTime(iso) {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  return `hace ${Math.round(s / 3600)} h`;
}

export const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;

export function verdictBadge(verdict, big = false) {
  const v = VERDICT[verdict] || { label: verdict, icon: "pause" };
  return `<span class="badge ${esc(verdict)}${big ? " big" : ""}">${icon(v.icon)}${esc(v.label)}</span>`;
}

export const chip = (text, cls = "", title = "") =>
  `<span class="chip ${cls}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;

export function metaChips(d) {
  return [
    chip(agentName(d.agent_id)),
    chip(actionTypeLabel(d.action_type)),
    chip(TIER[d.tier] || d.tier),
    chip(`Ruta: ${ROUTE[d.route]?.label || d.route}`),
  ].join("");
}

export function topReason(d) {
  const r = (d.reasons || []).find((x) => x.source !== "system") || (d.reasons || [])[0];
  if (r) return r.message;
  return d.verdict === "allow" ? "Sin observaciones: ninguna señal superó el umbral" : "";
}

export function reasonsList(reasons, { only, skip } = {}) {
  const list = (reasons || []).filter((r) => (!only || only.includes(r.source)) && (!skip || !skip.includes(r.source)));
  if (!list.length) return "";
  return `<ul class="reason-list">${list
    .map((r) => {
      const sev = r.severity ? chip(SEVERITY[r.severity] || r.severity, `sev-${r.severity}`) : "";
      return `<li><span class="src">${esc(SOURCE[r.source] || r.source)}</span>${sev}<span>${esc(r.message)}</span></li>`;
    })
    .join("")}</ul>`;
}

/** Texto legible de la respuesta cruda de JEV. */
export function answerText(signal, question) {
  const a = signal.raw || {};
  if (a.type === "noul") return a.noul >= 0.5 ? `Sí (${pct(a.noul)})` : `No (${pct(1 - a.noul)})`;
  if (a.type === "choice") {
    const p = a.probabilities?.[a.choice];
    const label = question?.question?.criteria?.[a.choice] || a.choice;
    return `${label} (${pct(p)})`;
  }
  if (a.type === "score") {
    const levels = question?.question?.criteria || [];
    const lvl = Math.max(0, Math.min(levels.length - 1, Math.round(a.score ?? 0)));
    return `${levels[lvl] || `nivel ${dec(a.score, 1)}`}`;
  }
  return "";
}

const level = (risk) => (risk >= 0.7 ? "lvl-high" : risk >= 0.35 ? "lvl-mid" : "lvl-low");

export function signalRow(signal, actionType) {
  const q = questionFor(actionType, signal.qid);
  const typeName = { noul: "sí/no", choice: "opciones", score: "escala" }[signal.raw?.type] || "";
  const title = q?.question?.instructions || signal.label;
  const risk = Math.max(0, Math.min(1, signal.risk));
  return `<div class="signal">
    <div class="q" title="${esc(title)}">${esc(q?.short || signal.label)}${signal.critical ? " " + chip("crítica", "crit") : ""}
      <small>JEV: <b class="ink2">${esc(answerText(signal, q))}</b> · ${esc(typeName)}</small></div>
    <div class="meter-col" data-tip="${esc(`Riesgo ${dec(risk)} · certeza ${dec(signal.certainty)} · peso ${dec(signal.weight)}`)}">
      <div class="meter"><div class="fill ${level(risk)}" style="width:${(risk * 100).toFixed(1)}%"></div></div>
      <div class="nums"><span>riesgo ${dec(risk)}</span><span>certeza ${dec(signal.certainty)}</span></div>
    </div>
  </div>`;
}

export function riskMeter(risk, tier) {
  const tp = tierPolicy(tier) || { review: 0.5, block: 0.8 };
  const r = Math.max(0, Math.min(1, risk || 0));
  return `<div class="risk">
    <div class="row"><span class="risk-value">${dec(r)}</span><span class="muted small">riesgo compuesto · ${esc(TIER[tier] || tier)}</span></div>
    <div style="height:26px"></div>
    <div class="risk-track" role="img" aria-label="${esc(`Riesgo ${dec(r)}; retener desde ${dec(tp.review)}, frenar desde ${dec(tp.block)}`)}">
      <div class="fill ${level(r >= tp.block ? 1 : r >= tp.review ? 0.5 : 0)}" style="width:${(r * 100).toFixed(1)}%"></div>
      <div class="mark" style="left:${tp.review * 100}%"><span>retener ${dec(tp.review)}</span></div>
      <div class="mark" style="left:${tp.block * 100}%"><span>frenar ${dec(tp.block)}</span></div>
    </div>
    <div class="risk-legend"><span>0</span><span>certeza mínima ${dec(tp.min_certainty)}</span><span>1</span></div>
  </div>`;
}

export function actionPreview(action) {
  if (!action) return "";
  const t = action.action_type;
  let text = "";
  if (t === "email.send" || t === "email.bulk") {
    const to = t === "email.send" ? (action.to || []).join(", ") : `${action.audience?.description || ""} (${action.recipient_count ?? (action.recipients || []).length} personas)`;
    text = `Para: ${to}\nAsunto: ${action.subject}\n\n${action.body}`;
  } else if (action.content) {
    text = Object.entries(action.content).map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join("\n\n");
  } else if (t === "content.publish") {
    text = `${action.platform}${action.title ? ` · ${action.title}` : ""}\n\n${action.text}`;
  } else {
    const scope = action.record_ids?.length ? action.record_ids.join(", ") : action.filter || "";
    const changes = t === "crm.update" ? `Cambios: ${JSON.stringify(action.changes)}\n` : `Motivo: ${action.reason || "—"}\n`;
    text = `${action.object} · ${scope}\n${changes}Evidencia: ${action.evidence || "—"}`;
  }
  return `<div class="preview">${esc(text)}</div>`;
}

export function decisionDetail(row) {
  const d = row.decision || row;
  const action = row.action;
  const final = row.final_verdict && row.status === "final" && d.verdict === "hold"
    ? `<p class="small ink2">Resuelta por ${esc(row.reviewer || "una persona")}: ${verdictBadge(row.final_verdict)}${row.review_note ? ` · «${esc(row.review_note)}»` : ""}</p>` : "";
  const sigs = (d.signals || []).map((s) => signalRow(s, d.action_type)).join("");
  return `
    <h2 id="drawer-title">${esc(d.summary || actionTypeLabel(d.action_type))}</h2>
    <div class="row">${verdictBadge(d.verdict)}${metaChips(d)}</div>
    ${final}
    <section><h3>Por qué</h3>${reasonsList(d.reasons) || '<p class="ink2 small">Ninguna señal superó los umbrales.</p>'}</section>
    ${sigs ? `<section><h3>Respuestas de JEV</h3><div class="signals">${sigs}</div></section>` : `<section><h3>JEV</h3><p class="ink2 small">No se llamó a JEV: una regla ya resolvió la acción.</p></section>`}
    <section><h3>Riesgo</h3>${riskMeter(d.risk, d.tier)}</section>
    <section><h3>Costo y tiempo</h3><div class="facts">
      <span>Guardián <b>${ms(d.latency_ms)}</b></span>
      <span>JEV <b>${ms(d.jev_latency_ms)}</b></span>
      <span>Tokens <b>${esc(d.input_tokens)}</b></span>
      <span>Costo <b>${usd(d.cost_usd)}</b></span>
      <span>Modelo <b>${esc(d.jev_model || "—")}</b></span>
    </div></section>
    ${action ? `<section><h3>Acción propuesta</h3>${actionPreview(action)}
      <div class="row" style="margin-top:10px"><button class="btn" type="button" data-open-lab>${icon("flask")}Abrir en el laboratorio</button></div></section>` : ""}
    <section><h3>Datos</h3><pre>${esc(JSON.stringify({ facts: d.facts, decision_id: d.decision_id, created_at: d.created_at }, null, 2))}</pre></section>`;
}

// -- panel lateral y avisos ---------------------------------------------------

let lastFocus = null;

export function openDrawer(html, onReady) {
  const drawer = document.getElementById("drawer");
  document.getElementById("drawer-body").innerHTML = html;
  lastFocus = document.activeElement;
  drawer.classList.add("open");
  drawer.setAttribute("aria-hidden", "false");
  drawer.querySelector(".drawer-close").focus();
  if (onReady) onReady(document.getElementById("drawer-body"));
}

export function closeDrawer() {
  const drawer = document.getElementById("drawer");
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  if (lastFocus) lastFocus.focus();
}

/** Aviso breve. Con `action`, muestra un botón (por ejemplo "Deshacer"). */
export function toast(message, { action, onAction, duration = 3200 } = {}) {
  const el = document.createElement("div");
  el.className = "toast";
  const text = document.createElement("span");
  text.textContent = message;
  el.appendChild(text);
  let timer = setTimeout(() => el.remove(), duration);
  if (action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = action;
    btn.addEventListener("click", () => { clearTimeout(timer); el.remove(); onAction?.(); });
    el.appendChild(btn);
  }
  document.getElementById("toasts").appendChild(el);
  return { close: () => { clearTimeout(timer); el.remove(); } };
}
