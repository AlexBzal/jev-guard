// Arranque de la interfaz: enrutador, conexión en vivo, tema, tooltip y panel lateral.

import { api } from "./api.js";
import { closeDrawer, icon, toast } from "./components.js";
import { emit, on, store } from "./state.js";
import * as live from "./views/live.js";
import * as lab from "./views/lab.js";
import * as review from "./views/review.js";
import * as metrics from "./views/metrics.js";

const VIEWS = { vivo: live, laboratorio: lab, bandeja: review, metricas: metrics };
const view = document.getElementById("view");
let unmount = null;

// -- enrutador ------------------------------------------------------------------

function route() {
  const name = (location.hash.replace(/^#\//, "") || "vivo").split("?")[0];
  const mod = VIEWS[name] || live;
  document.querySelectorAll(".tabs a").forEach((a) => {
    if (a.dataset.route === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (unmount) unmount();
  view.innerHTML = "";
  unmount = mod.mount(view) || null;
  view.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

// -- tema -------------------------------------------------------------------------

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

// -- tooltip global (cualquier elemento con data-tip) ------------------------------

function initTooltip() {
  const tip = document.getElementById("tooltip");
  document.addEventListener("mousemove", (e) => {
    const el = e.target.closest?.("[data-tip]");
    if (!el) { tip.hidden = true; return; }
    tip.textContent = el.getAttribute("data-tip");
    tip.hidden = false;
    const pad = 14;
    const { innerWidth: W, innerHeight: H } = window;
    const r = tip.getBoundingClientRect();
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    if (x + r.width > W - 8) x = e.clientX - r.width - pad;
    if (y + r.height > H - 8) y = e.clientY - r.height - pad;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
  });
  document.addEventListener("scroll", () => { tip.hidden = true; }, true);
}

// -- panel lateral -------------------------------------------------------------------

function initDrawer() {
  document.getElementById("drawer").addEventListener("click", (e) => {
    if (e.target.closest("[data-close]")) closeDrawer();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.getElementById("drawer").classList.contains("open")) closeDrawer();
  });
}

// -- conexión en vivo ------------------------------------------------------------------

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
  es.addEventListener("reset", () => {
    setPending(0);
    emit("reset");
  });
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

// -- arranque --------------------------------------------------------------------------

async function boot() {
  initTheme();
  initTooltip();
  initDrawer();
  try {
    const [health, policy, scenarios] = await Promise.all([api.health(), api.policy(), api.scenarios()]);
    store.health = health;
    store.policy = policy;
    store.scenarios = scenarios;
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
    view.innerHTML = `<div class="card empty">No se pudo conectar con la API de JEV Guard. ¿Está corriendo el servidor?<br><span class="error">${e.message}</span></div>`;
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
  on("toast", toast);
  window.addEventListener("hashchange", route);
  route();
}

boot();
