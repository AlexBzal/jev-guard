// Vista "Bandeja": acciones retenidas que esperan a una persona.

import { api } from "../api.js";
import { actionPreview, icon, metaChips, reasonsList, signalRow, verdictBadge } from "../components.js";
import { clock, esc } from "../format.js";
import { emit, on } from "../state.js";

const REVIEWER_KEY = "jevguard-reviewer";

export function mount(el) {
  let reviewer = "";
  try { reviewer = localStorage.getItem(REVIEWER_KEY) || ""; } catch (e) { /* sin almacenamiento */ }

  el.innerHTML = `
    <div class="page-head">
      <div>
        <h1>Bandeja de revisión</h1>
        <p>Aquí llega solo lo que el guardián no debe decidir solo: dudas de JEV en acciones de alto impacto, o reglas que exigen una segunda llave humana. Cada decisión queda como etiqueta y mejora la calibración de los umbrales.</p>
      </div>
      <div class="field" style="margin:0;min-width:220px">
        <label for="reviewer">Revisas como</label>
        <input id="reviewer" type="text" placeholder="Tu nombre o usuario" value="${esc(reviewer)}">
      </div>
    </div>
    <div class="queue" id="queue"><div class="card empty">Cargando…</div></div>`;

  const queue = el.querySelector("#queue");
  let rows = [];

  el.querySelector("#reviewer").addEventListener("input", (e) => {
    reviewer = e.target.value.trim();
    try { localStorage.setItem(REVIEWER_KEY, reviewer); } catch (err) { /* sin almacenamiento */ }
  });

  function cardHtml(row) {
    const d = row.decision;
    const sigs = (d.signals || []).filter((s) => s.risk >= 0.3).map((s) => signalRow(s, d.action_type)).join("");
    return `<article class="card review-card" data-id="${esc(d.decision_id)}">
      <div class="head">${verdictBadge("hold")}<span class="title">${esc(d.summary)}</span><span class="spacer"></span><span class="muted small">${clock(d.created_at)}</span></div>
      <div class="row">${metaChips(d)}</div>
      <div><div class="small muted" style="margin-bottom:4px">Por qué se retuvo</div>${reasonsList(d.reasons)}</div>
      ${sigs ? `<details><summary class="small ink2" style="cursor:pointer">Señales de JEV con riesgo</summary><div class="signals" style="margin-top:8px">${sigs}</div></details>` : ""}
      <div><div class="small muted" style="margin-bottom:4px">Tarea del agente: ${esc(row.action?.task || "")}</div>${actionPreview(row.action)}</div>
      <div class="review-actions">
        <input type="text" placeholder="Nota para el registro (opcional)" aria-label="Nota" data-note>
        <button class="btn approve" type="button" data-approve="1">${icon("check")}Aprobar y ejecutar</button>
        <button class="btn reject" type="button" data-approve="0">${icon("x")}Rechazar</button>
      </div>
    </article>`;
  }

  // Si la persona está escribiendo una nota, no se redibuja hasta que salga del campo.
  let deferred = false;
  function renderUnlessTyping() {
    const active = document.activeElement;
    if (active && queue.contains(active) && active.matches("input")) { deferred = true; return; }
    render();
  }
  queue.addEventListener("focusout", () => { if (deferred) { deferred = false; setTimeout(renderUnlessTyping, 0); } });

  function render() {
    queue.innerHTML = rows.length
      ? rows.map(cardHtml).join("")
      : `<div class="card empty">${icon("check")} No hay acciones pendientes. El guardián está resolviendo todo solo.</div>`;
  }

  async function load() {
    try { rows = await api.pending(); render(); } catch (e) { queue.innerHTML = `<div class="card empty error">${esc(e.message)}</div>`; }
  }

  queue.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-approve]");
    if (!btn) return;
    const card = btn.closest("[data-id]");
    const id = card.dataset.id;
    const approve = btn.dataset.approve === "1";
    const note = card.querySelector("[data-note]").value.trim();
    if (!reviewer) {
      el.querySelector("#reviewer").focus();
      emit("toast", "Escribe tu nombre antes de revisar: queda en el registro de auditoría.");
      return;
    }
    card.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      await api.review(id, approve, reviewer, note);
      rows = rows.filter((r) => r.decision.decision_id !== id);
      render();
      emit("toast", approve ? "Aprobada: el agente puede ejecutar la acción." : "Rechazada: el agente no ejecutará la acción.");
    } catch (err) {
      emit("toast", err.message);
      card.querySelectorAll("button").forEach((b) => { b.disabled = false; });
    }
  });

  const offs = [
    on("decision", (ev) => {
      if (ev.decision.status !== "pending_review") return;
      // La acción completa se pide aparte para mostrar la vista previa.
      api.decision(ev.decision.decision_id).then((row) => {
        if (!rows.some((r) => r.decision.decision_id === row.decision_id)) {
          rows.unshift(row);
          renderUnlessTyping();
        }
      }).catch(() => {});
    }),
    on("review", (ev) => {
      const before = rows.length;
      rows = rows.filter((r) => r.decision.decision_id !== ev.decision_id);
      if (rows.length !== before) render();
    }),
    on("reset", load),
  ];
  load();
  return () => offs.forEach((off) => off());
}
