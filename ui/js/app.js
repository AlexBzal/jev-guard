// Arranque de la interfaz: enrutador con transiciones, atajos, conexión en vivo, tema, tooltip y panel lateral.

import { api } from "./api.js";
import { closeDrawer, icon, toast } from "./components.js";
import { emit, on, store } from "./state.js";
import * as live from "./views/live.js";
import * as lab from "./views/lab.js";
import * as review from "./views/review.js";
import * as metrics from "./views/metrics.js";

const VIEWS = { vivo: live, laboratorio: lab, bandeja: review, metricas: metrics };
const ORDER = ["vivo", "laboratorio", "bandeja", "metricas"];
const view = document.getElementById("view");
let unmount = null;

// -- enrutador ----------------------------------------------------------------------

function currentRoute() {
  const name = (location.hash.replace(/^#\//, "") || "vivo").split("?")[0];
  return VIEWS[name] ? name : "vivo";
}

function render() {
  const name = currentRoute();
  document.querySelectorAll(".nav a").forEach((a) => {
    if (a.dataset.route === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (unmount) unmount();
  view.innerHTML = "";
  unmount = VIEWS[name].mount(view) || null;
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function route() {
  // Transición suave entre vistas donde el navegador la soporta.
  if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    document.startViewTransition(render);
  } else {
    render();
  }
}

// -- tema ------------------------------------------------------------------------------

const THEMES = ["auto", "light", "dark"];
const THEME_LABEL = { auto: "Tema: automático", light: "Tema: claro", dark: "Tema: oscuro" };
const THEME_ICON = { auto: "auto", light: "sun", dark: "moon" };

function applyTheme(t) {
  if (t === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  const btn = document.getElementById("theme-btn");
  btn.innerHTML = icon(THEME_ICON[t]);
  btn.title = THEME_LABEL[t];
  btn.setAttribute("aria-label", THEME_LABEL[t]);
  try { localStorage.setItem("jevguard-theme", t); } catch (e) { /* almacenamiento no disponible */ }
}

function initTheme() {
  let t = "auto";
  try { t = localStorage.getItem("jevguard-theme") || "auto"; } catch (e) { /* sin almacenamiento */ }
  applyTheme(THEMES.includes(t) ? t : "auto");
  document.getElementById("theme-btn").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || "auto";
    applyTheme(THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length]);
  });
}

// -- tooltip global (data-tip), con ratón y con teclado ------------------------------------

function initTooltip() {
  const tip = document.getElementById("tooltip");
  const show = (el, x, y) => {
    tip.textContent = el.getAttribute("data-tip");
    tip.hidden = false;
    const pad = 14;
    const r = tip.getBoundingClientRect();
    let left = x + pad;
    let top = y + pad;
    if (left + r.width > innerWidth - 8) left = x - r.width - pad;
    if (top + r.height > innerHeight - 8) top = y - r.height - pad;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  };
  document.addEventListener("mousemove", (e) => {
    const el = e.target.closest?.("[data-tip]");
    if (!el || !el.getAttribute("data-tip")) { tip.hidden = true; return; }
    show(el, e.clientX, e.clientY);
  });
  document.addEventListener("focusin", (e) => {
    const el = e.target.closest?.("[data-tip]");
    if (!el || !el.getAttribute("data-tip")) return;
    const r = el.getBoundingClientRect();
    show(el, r.left, r.bottom);
  });
  document.addEventListener("focusout", () => { tip.hidden = true; });
  document.addEventListener("scroll", () => { tip.hidden = true; }, true);
}

// -- panel lateral, ayuda y atajos -------------------------------------------------------------

function initOverlays() {
  document.getElementById("drawer").addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) closeDrawer();
  });
  const help = document.getElementById("help-dialog");
  document.getElementById("help-btn").addEventListener("click", () => help.showModal());
  document.addEventListener("keydown", (e) => {
    const typing = e.target.closest?.("input, textarea, select, [contenteditable]");
    if (e.key === "Escape" && document.getElementById("drawer").classList.contains("open")) { closeDrawer(); return; }
    if (typing || e.metaKey || e.ctrlKey || e.altKey || help.open) return;
    if (e.key === "?") { e.preventDefault(); help.showModal(); return; }
    const idx = ["1", "2", "3", "4"].indexOf(e.key);
    if (idx >= 0) { e.preventDefault(); location.hash = `#/${ORDER[idx]}`; return; }
    emit("key", e); // atajos propios de cada vista
  });
}

function initNavIcons() {
  document.querySelectorAll(".nav [data-icon]").forEach((el) => { el.innerHTML = icon(el.dataset.icon); });
}

// -- conexión en vivo ---------------------------------------------------------------------------

function setConn(state) {
  const pill = document.getElementById("conn-pill");
  pill.classList.toggle("live", state === "live");
  pill.classList.toggle("down", state === "down");
  pill.lastElementChild.textContent = { live: "En vivo", down: "Sin conexión", connecting: "Conectando" }[state];
}

function initStream() {
  const es = new EventSource("/v1/stream");
  setConn("connecting");
  es.onopen = () => setConn("live");
  es.onerror = () => setConn("down"); // EventSource reintenta solo
  es.addEventListener("decision", (e) => {
    const ev = JSON.parse(e.data);
    if (ev.decision?.status === "pending_review") setPending(store.pendingCount + 1);
    emit("decision", ev);
  });
  es.addEventListener("review", (e) => {
    setPending(Math.max(0, store.pendingCount - 1));
    emit("review", JSON.parse(e.data));
  });
  es.addEventListener("reset", () => { setPending(0); emit("reset"); });
}

function setPending(n) {
  store.pendingCount = n;
  const el = document.getElementById("pending-count");
  el.textContent = n > 99 ? "99+" : String(n);
  el.hidden = n === 0;
}

async function refreshPending() {
  try { setPending((await api.pending()).length); } catch (e) { /* se reintenta en el próximo ciclo */ }
}

// -- arranque ------------------------------------------------------------------------------------

async function boot() {
  initTheme();
  initNavIcons();
  initTooltip();
  initOverlays();
  try {
    const [health, policy, scenarios, profile] = await Promise.all([api.health(), api.policy(), api.scenarios(), api.profile()]);
    Object.assign(store, { health, policy, scenarios, profile });
    const company = profile.company.name;
    document.getElementById("company-name").textContent = company;
    document.getElementById("company-profile").textContent = `Perfil «${profile.profile}» · ${Object.keys(profile.agents).length} agentes`;
    document.getElementById("company-card").hidden = false;
    document.title = `JEV Guard · ${company}`;
    const simulated = health.jev === "simulated";
    const mode = document.getElementById("mode-pill");
    mode.textContent = simulated ? "JEV simulado" : "JEV · TypeSafe";
    mode.title = health.llm ? `Segunda opinión: ${health.llm}` : "Sin LLM: las dudas van a personas";
    document.getElementById("sim-banner").hidden = !simulated;
    if (health.clock) {
      const when = new Date(health.clock).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
      document.getElementById("clock-note").textContent = ` Reloj de la demo fijado en ${when.replace(/\.$/, "")}.`;
    }
  } catch (e) {
    view.innerHTML = `<div class="card empty"><strong>No se pudo conectar con la API de JEV Guard</strong>¿Está corriendo el servidor?<br><span class="error">${e.message}</span></div>`;
    return;
  }
  initStream();
  refreshPending();
  setInterval(refreshPending, 15000);
  on("open-lab", (action) => {
    const already = location.hash === "#/laboratorio";
    store.labAction = action;
    closeDrawer();
    if (already) route();
    else location.hash = "#/laboratorio";
  });
  on("pending-changed", refreshPending);
  on("toast", (t) => (typeof t === "string" ? toast(t) : toast(t.message, t)));
  window.addEventListener("hashchange", route);
  render();
}

boot();
