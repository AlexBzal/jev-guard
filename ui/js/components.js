// Componentes reutilizables (devuelven HTML como texto; todo dato pasa por esc()).

import { ACTION_TYPE, ROUTE, SEVERITY, SOURCE, TIER, VERDICT, agentName, dec, esc, ms, pct, usd } from "./format.js";
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
};

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
    chip(ACTION_TYPE[d.action_type] || d.action_type),
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
    <h2 id="drawer-title">${esc(d.summary || ACTION_TYPE[d.action_type])}</h2>
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

export function toast(message) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  document.getElementById("toasts").appendChild(el);
  setTimeout(() => el.remove(), 3200);
}
