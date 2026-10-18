// Vista "Bandeja": decidir lo pendiente. Acción primaria: aprobar o rechazar.
// Lista a la izquierda, detalle a la derecha. Atajos: J/K para moverse, A/R para decidir.
// La decisión es optimista: se aplica al instante y se envía a los 4 s, salvo que se deshaga.

import { api } from "../api.js";
import { actionPreview, icon, metaChips, reasonsList, relTime, signalRow, skeleton, term, verdictBadge } from "../components.js";
import { agentName, esc } from "../format.js";
import { emit, on } from "../state.js";

const REVIEWER_KEY = "jevguard-reviewer";
const UNDO_MS = 4000;

export function mount(el) {
  let reviewer = "";
  try { reviewer = localStorage.getItem(REVIEWER_KEY) || ""; } catch (e) { /* sin almacenamiento */ }

  el.innerHTML = `
    <div class="page-head">
      <div>
        <div class="eyebrow">Bandeja</div>
        <h1>Lo que el guardián no debe decidir solo</h1>
        <p class="lead">Acciones ${term("retenidas", "retenida")} por duda de JEV, por alto impacto o por una regla que exige una segunda llave humana. Cada decisión queda como etiqueta y mejora la calibración.</p>
      </div>
      <div class="field" style="margin:0;min-width:230px">
        <label for="reviewer">Revisas como</label>
        <input id="reviewer" type="text" placeholder="Tu nombre o usuario" value="${esc(reviewer)}" autocomplete="name">
      </div>
    </div>
    <div class="inbox" id="inbox">
      <div class="card inbox-list" id="list" role="listbox" aria-label="Acciones pendientes">${'<div style="padding:16px">' + skeleton.lines(6) + "</div>"}</div>
      <div class="card review-detail" id="detail">${skeleton.lines(8)}</div>
    </div>`;

  const $ = (s) => el.querySelector(s);
  let rows = [];
  let selected = null;
  const pendingCommits = new Map(); // decision_id -> {timer, commit}

  $("#reviewer").addEventListener("input", (e) => {
    reviewer = e.target.value.trim();
    try { localStorage.setItem(REVIEWER_KEY, reviewer); } catch (err) { /* sin almacenamiento */ }
  });

  // -- render -----------------------------------------------------------------------------
  function itemHtml(row) {
    const d = row.decision;
    const why = (d.reasons || []).find((r) => r.source !== "system") || (d.reasons || [])[0];
    const sel = d.decision_id === selected;
    return `<button class="inbox-item" type="button" role="option" aria-selected="${sel}" data-id="${esc(d.decision_id)}">
      <span class="t">${esc(d.summary)}</span>
      <span class="w">${esc(why?.message || "")}</span>
      <span class="m">${esc(agentName(d.agent_id))} · <span data-rel="${esc(d.created_at)}">${relTime(d.created_at)}</span></span>
    </button>`;
  }

  function renderList() {
    $("#list").innerHTML = rows.length
      ? rows.map(itemHtml).join("")
      : `<div class="empty"><strong>Bandeja vacía</strong>El guardián está resolviendo todo solo.</div>`;
  }

  function renderDetail() {
    const row = rows.find((r) => r.decision.decision_id === selected);
    const detail = $("#detail");
    if (!row) {
      detail.innerHTML = rows.length
        ? `<div class="empty">Elige una acción de la lista.</div>`
        : `<div class="empty"><strong>${icon("check")} Nada pendiente</strong>Cuando una acción necesite a una persona, aparecerá aquí al instante.</div>`;
      return;
    }
    const d = row.decision;
    const sigs = (d.signals || []).filter((s) => s.risk >= 0.3).map((s) => signalRow(s, d.action_type)).join("");
    detail.innerHTML = `
      <div class="row">${verdictBadge("hold")}<span class="spacer"></span><span class="micro muted">${esc(new Date(d.created_at).toLocaleString("es-CO"))}</span></div>
      <h2 class="title">${esc(d.summary)}</h2>
      <div class="row">${metaChips(d)}</div>
      <div><div class="micro muted" style="margin-bottom:6px">Por qué se retuvo</div>${reasonsList(d.reasons)}</div>
      ${sigs ? `<details><summary class="small ink2" style="cursor:pointer">Señales de JEV con riesgo</summary><div class="signals" style="margin-top:10px">${sigs}</div></details>` : ""}
      <div><div class="micro muted" style="margin-bottom:6px">Tarea del agente: ${esc(row.action?.task || "")}</div>${actionPreview(row.action)}</div>
      <div class="review-actions">
        <input type="text" placeholder="Nota para el registro (opcional)" aria-label="Nota" id="note">
        <button class="btn approve" type="button" data-approve="1">${icon("check")}Aprobar <kbd>A</kbd></button>
        <button class="btn reject" type="button" data-approve="0">${icon("x")}Rechazar <kbd>R</kbd></button>
      </div>`;
  }

  function render() {
    if (selected && !rows.some((r) => r.decision.decision_id === selected)) selected = null;
    if (!selected && rows.length) selected = rows[0].decision.decision_id;
    renderList();
    renderDetail();
  }

  function select(id) {
    selected = id;
    el.querySelectorAll(".inbox-item").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.id === id)));
    renderDetail();
    el.querySelector(`.inbox-item[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest" });
  }

  function move(delta) {
    if (!rows.length) return;
    const i = Math.max(0, rows.findIndex((r) => r.decision.decision_id === selected));
    const next = rows[Math.min(rows.length - 1, Math.max(0, i + delta))];
    select(next.decision.decision_id);
  }

  // -- decidir, con deshacer ----------------------------------------------------------------
  function decide(approve) {
    const idx = rows.findIndex((r) => r.decision.decision_id === selected);
    if (idx < 0) return;
    if (!reviewer) {
      $("#reviewer").focus();
      emit("toast", "Escribe tu nombre antes de revisar: queda en el registro de auditoría.");
      return;
    }
    const row = rows[idx];
    const id = row.decision.decision_id;
    const note = $("#note")?.value.trim() || "";
    rows.splice(idx, 1);
    selected = rows[Math.min(idx, rows.length - 1)]?.decision.decision_id || null;
    render();

    const commit = async () => {
      pendingCommits.delete(id);
      try {
        await api.review(id, approve, reviewer, note);
      } catch (err) {
        emit("toast", `No se pudo guardar la revisión: ${err.message}`);
        rows.splice(Math.min(idx, rows.length), 0, row);
        render();
      }
    };
    const timer = setTimeout(commit, UNDO_MS);
    pendingCommits.set(id, { timer, commit });
    emit("toast", {
      message: approve ? "Aprobada: el agente podrá ejecutarla." : "Rechazada: el agente no la ejecutará.",
      action: "Deshacer",
      duration: UNDO_MS,
      onAction: () => {
        clearTimeout(timer);
        pendingCommits.delete(id);
        rows.splice(Math.min(idx, rows.length), 0, row);
        selected = id;
        render();
      },
    });
  }

  // -- eventos ----------------------------------------------------------------------------------
  $("#list").addEventListener("click", (e) => {
    const b = e.target.closest(".inbox-item");
    if (b) select(b.dataset.id);
  });
  $("#detail").addEventListener("click", (e) => {
    const b = e.target.closest("[data-approve]");
    if (b) decide(b.dataset.approve === "1");
  });

  async function load() {
    try { rows = await api.pending(); render(); } catch (e) { $("#detail").innerHTML = `<div class="empty error">${esc(e.message)}</div>`; }
  }

  const offs = [
    on("decision", (ev) => {
      if (ev.decision.status !== "pending_review") return;
      api.decision(ev.decision.decision_id).then((row) => {
        if (rows.some((r) => r.decision.decision_id === row.decision_id)) return;
        rows.unshift(row);
        if (!selected) selected = row.decision_id;
        renderList(); // el detalle no se toca: la persona puede estar escribiendo una nota
        if (!$("#detail .review-actions")) renderDetail();
      }).catch(() => {});
    }),
    on("review", (ev) => {
      if (pendingCommits.has(ev.decision_id)) return;
      const before = rows.length;
      rows = rows.filter((r) => r.decision.decision_id !== ev.decision_id);
      if (rows.length !== before) render();
    }),
    on("reset", load),
    on("key", (e) => {
      const k = e.key.toLowerCase();
      if (k === "j") { e.preventDefault(); move(1); }
      else if (k === "k") { e.preventDefault(); move(-1); }
      else if (k === "a") { e.preventDefault(); decide(true); }
      else if (k === "r") { e.preventDefault(); decide(false); }
    }),
  ];
  const flushAll = () => {
    for (const { timer, commit } of pendingCommits.values()) { clearTimeout(timer); commit(); }
  };
  window.addEventListener("pagehide", flushAll);
  const tick = setInterval(() => {
    el.querySelectorAll("[data-rel]").forEach((s) => { s.textContent = relTime(s.dataset.rel); });
  }, 5000);
  load();

  return () => {
    // Al salir de la vista, las decisiones pendientes de deshacer se guardan ya.
    flushAll();
    window.removeEventListener("pagehide", flushAll);
    offs.forEach((off) => off());
    clearInterval(tick);
  };
}
