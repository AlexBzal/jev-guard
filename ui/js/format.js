// Formatos y etiquetas en español. Los nombres propios de cada empresa salen del perfil activo.

import { store } from "./state.js";

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

const LOCALE = "es-CO";
export const int = (n) => (n == null ? "—" : new Intl.NumberFormat(LOCALE).format(Math.round(n)));
export const dec = (n, d = 2) =>
  n == null ? "—" : new Intl.NumberFormat(LOCALE, { minimumFractionDigits: d, maximumFractionDigits: d }).format(n);
export const pct = (x, d = 0) =>
  x == null ? "—" : new Intl.NumberFormat(LOCALE, { style: "percent", maximumFractionDigits: d }).format(x);
export const compact = (n) =>
  n == null ? "—" : new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 }).format(n);

export function ms(x) {
  if (x == null) return "—";
  return `${x < 10 ? dec(x, 1) : int(x)} ms`;
}

export function usd(x) {
  if (x == null) return "—";
  if (x === 0) return "0 USD";
  if (x < 0.01) {
    return `${new Intl.NumberFormat(LOCALE, { maximumSignificantDigits: 2 }).format(x)} USD`;
  }
  return `${dec(x, 2)} USD`;
}

export function clock(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const VERDICT = {
  allow: { label: "Permitida", icon: "check" },
  block: { label: "Frenada", icon: "x" },
  hold: { label: "Retenida", icon: "pause" },
};

export const ROUTE = {
  rules: { label: "Reglas", long: "La resolvieron las reglas, sin llamar a JEV" },
  jev: { label: "JEV", long: "JEV decidió solo, con certeza suficiente" },
  llm: { label: "LLM", long: "JEV dudó y un LLM dio la segunda opinión" },
  human: { label: "Persona", long: "Pasa a una persona en la bandeja de revisión" },
};

export const TIER = {
  low: "Impacto bajo",
  medium: "Impacto medio",
  high: "Impacto alto",
  critical: "Impacto crítico",
};

const BUILTIN_TYPES = {
  "email.send": "Correo",
  "email.bulk": "Campaña",
  "crm.update": "Cambio en CRM",
  "crm.delete": "Borrado en CRM",
  "content.publish": "Publicación",
};

/** Tipos de acción del perfil activo: los estándar más los propios de la empresa. */
export function actionTypes() {
  const types = store.profile?.action_types || Object.keys(BUILTIN_TYPES);
  return Object.fromEntries(types.map((t) => [t, actionTypeLabel(t)]));
}

export function actionTypeLabel(t) {
  return BUILTIN_TYPES[t] || store.profile?.custom_actions?.[t]?.label || t;
}

export const agentName = (id) => store.profile?.agents?.[id]?.name || id;
export const companyName = () => store.profile?.company?.name || "tu empresa";

export const SEVERITY = { block: "Frena", review: "Revisión", info: "Aviso" };

export const SOURCE = { rule: "Regla", jev: "JEV", llm: "LLM", system: "Sistema", human: "Persona" };
