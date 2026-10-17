// Gráficos en SVG propio, según la guía de visualización:
// barras de máximo 24 px con extremo redondeado de 4 px y base recta, separación de 2 px
// entre segmentos, guías de 1 px discretas, etiquetas directas selectivas, tooltip en cada
// marca (atributo data-tip, manejado globalmente) y vista de tabla.

import { esc, int } from "./format.js";
import { icon } from "./components.js";

const BAR = 16;
const R = 4;

/** Barra horizontal con el extremo derecho redondeado y la base (izquierda) recta. */
function hbarPath(x, y, w, h, r = R) {
  if (w <= 0) return "";
  const rr = Math.min(r, w, h / 2);
  return `M${x},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h - rr}Q${x + w},${y + h} ${x + w - rr},${y + h}H${x}Z`;
}

/** Columna con el extremo superior redondeado y la base recta. */
function colPath(x, y, w, h, r = R) {
  if (h <= 0) return "";
  const rr = Math.min(r, h, w / 2);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

export function tableView(head, rows) {
  return `<details class="table-view"><summary>Ver tabla</summary><table><thead><tr>${head
    .map((h, i) => `<th${i ? ' class="num"' : ""}>${esc(h)}</th>`)
    .join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${r.map((c, i) => `<td${i ? ' class="num"' : ""}>${esc(c)}</td>`).join("")}</tr>`)
    .join("")}</tbody></table></details>`;
}

/** Barras horizontales de una sola serie. rows: [{label, value, display, tip}] */
export function hbars(rows, width, { labelWidth = 120 } = {}) {
  const rowH = 34;
  const valueW = 64;
  const plotW = Math.max(60, width - labelWidth - valueW);
  const max = Math.max(1, ...rows.map((r) => r.value));
  const h = rows.length * rowH;
  const body = rows
    .map((r, i) => {
      const y = i * rowH + (rowH - BAR) / 2;
      const w = (r.value / max) * plotW;
      return `<g>
        <text class="ink" x="${labelWidth - 10}" y="${y + BAR / 2 + 4}" text-anchor="end">${esc(r.label)}</text>
        <path class="bar" d="${hbarPath(labelWidth, y, w, BAR)}"/>
        <text class="val" x="${labelWidth + w + 8}" y="${y + BAR / 2 + 4}">${esc(r.display ?? int(r.value))}</text>
        <rect class="hit" x="0" y="${i * rowH}" width="${width}" height="${rowH}" data-tip="${esc(r.tip || `${r.label}: ${r.display ?? int(r.value)}`)}"/>
      </g>`;
    })
    .join("");
  return `<div class="chart"><svg width="${width}" height="${h}" role="img">
    <line class="base-line" x1="${labelWidth}" x2="${labelWidth}" y1="0" y2="${h}"/>${body}</svg></div>`;
}

/** Histograma en columnas. bins: [{label, value, tip}] */
export function columns(bins, width, { height = 180 } = {}) {
  const left = 36;
  const bottom = 26;
  const top = 18;
  const plotW = Math.max(100, width - left - 8);
  const plotH = height - bottom - top;
  const max = niceMax(Math.max(1, ...bins.map((b) => b.value)));
  const band = plotW / bins.length;
  const barW = Math.min(24, band - 2);
  const ticks = [0, max / 2, max];
  const grid = ticks
    .map((t) => {
      const y = top + plotH - (t / max) * plotH;
      return `<line class="${t === 0 ? "base-line" : "grid-line"}" x1="${left}" x2="${left + plotW}" y1="${y}" y2="${y}"/>
        <text x="${left - 6}" y="${y + 4}" text-anchor="end">${esc(int(t))}</text>`;
    })
    .join("");
  const peak = bins.reduce((best, b, i) => (b.value > bins[best].value ? i : best), 0);
  const body = bins
    .map((b, i) => {
      const x = left + i * band + (band - barW) / 2;
      const bh = (b.value / max) * plotH;
      const y = top + plotH - bh;
      const label = i === peak && b.value > 0 ? `<text class="val" x="${x + barW / 2}" y="${y - 6}" text-anchor="middle">${esc(int(b.value))}</text>` : "";
      return `<g>
        <path class="bar" d="${colPath(x, y, barW, bh)}"/>${label}
        <text x="${left + i * band + band / 2}" y="${height - 8}" text-anchor="middle">${esc(b.label)}</text>
        <rect class="hit" x="${left + i * band}" y="${top}" width="${band}" height="${plotH}" data-tip="${esc(b.tip || `${b.label}: ${int(b.value)}`)}"/>
      </g>`;
    })
    .join("");
  return `<div class="chart"><svg width="${width}" height="${height}" role="img">${grid}${body}</svg></div>`;
}

/** Barras horizontales apiladas. keys: [{key, label, cls, icon}] rows: [{label, values:{key:n}}] */
export function stacked(rows, keys, width, { labelWidth = 120 } = {}) {
  const rowH = 34;
  const valueW = 48;
  const plotW = Math.max(60, width - labelWidth - valueW);
  const max = Math.max(1, ...rows.map((r) => keys.reduce((s, k) => s + (r.values[k.key] || 0), 0)));
  const h = rows.length * rowH;
  const legend = `<div class="legend">${keys.map((k) => `<span><svg viewBox="0 0 14 14" aria-hidden="true"><rect width="14" height="14" rx="3" class="${k.cls}" style="fill:var(--${k.color})"/></svg>${icon(k.icon)}${esc(k.label)}</span>`).join("")}</div>`;
  const body = rows
    .map((r, i) => {
      const y = i * rowH + (rowH - BAR) / 2;
      const total = keys.reduce((s, k) => s + (r.values[k.key] || 0), 0);
      const present = keys.filter((k) => (r.values[k.key] || 0) > 0);
      let x = labelWidth;
      const segs = present
        .map((k, j) => {
          const v = r.values[k.key];
          const w = Math.max(1, (v / max) * plotW - (j < present.length - 1 ? 2 : 0));
          const isLast = j === present.length - 1;
          const d = isLast ? hbarPath(x, y, w, BAR) : `M${x},${y}h${w}v${BAR}h${-w}Z`;
          const out = `<path class="${k.cls}" d="${d}"/><rect class="hit" x="${x}" y="${i * rowH}" width="${Math.max(w, 4)}" height="${rowH}" data-tip="${esc(`${r.label} · ${k.label}: ${int(v)} de ${int(total)}`)}"/>`;
          x += w + 2;
          return out;
        })
        .join("");
      return `<g><text class="ink" x="${labelWidth - 10}" y="${y + BAR / 2 + 4}" text-anchor="end">${esc(r.label)}</text>${segs}
        <text class="val" x="${x + 6}" y="${y + BAR / 2 + 4}">${esc(int(total))}</text></g>`;
    })
    .join("");
  return `${legend}<div class="chart"><svg width="${width}" height="${h}" role="img">
    <line class="base-line" x1="${labelWidth}" x2="${labelWidth}" y1="0" y2="${h}"/>${body}</svg></div>`;
}
