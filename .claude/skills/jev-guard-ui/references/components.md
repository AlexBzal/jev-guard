# Componentes

Viven en `ui/js/components.js` (HTML como texto, datos siempre por `esc()`) y `ui/js/charts.js` (SVG propio).

| Componente | Función | Reglas |
|---|---|---|
| Barra lateral | Navegación, empresa activa, estado del motor y conexión | Ítem activo con fondo `--accent-wash`. Contador de la Bandeja en ámbar. |
| Encabezado de vista | Título, una frase de "qué estás viendo" y la acción primaria | La frase es obligatoria: es lo que lee alguien nuevo. |
| `verdictBadge()` | Estado de una decisión | Ícono más texto. `big` solo en el veredicto del Laboratorio. |
| `term()` | Término con definición | Subrayado punteado; definición en tooltip y en `aria-label`. |
| `statTile()` | Una cifra con su contexto | Etiqueta, valor y detalle. El valor anima su cambio con `tween()`. |
| `skeleton()` | Reserva el espacio de lo que carga | Misma forma y altura que el contenido real. |
| Fila de decisión | Una decisión en el flujo | Veredicto, resumen, razón principal y metadatos en una línea secundaria. |
| Tarjeta de paso | Un paso del recorrido de la decisión | Número, título, una frase y contenido. Se puede contraer. |
| `signalRow()` | Una pregunta a JEV | Pregunta en lenguaje claro, respuesta de JEV y medidor de riesgo con certeza. |
| `riskMeter()` | Riesgo compuesto con umbrales | Marcas de "retener" y "frenar" del impacto de la acción. |
| Panel lateral | Detalle de una decisión | Se cierra con Esc y con clic fuera. Devuelve el foco. |
| Aviso | Confirmación breve | Puede llevar la acción "Deshacer". |
| Diálogo de atajos | Lista de atajos de teclado | Se abre con `?`. |

## Gráficos (`charts.js`)

| Función | Para qué |
|---|---|
| `hbars()` | Magnitud por categoría, una serie |
| `columns()` | Distribución, como el histograma de latencia |
| `stacked()` | Composición por veredicto |
| `sparkline()` | Tendencia reciente sin ejes, junto a una cifra |
| `splitBar()` | Proporción de veredictos en una barra |

Todos cumplen la skill `dataviz`: barras de máximo 24 px, extremo redondeado de 4 px, separación de 2 px, tooltip en cada marca y vista de tabla en los gráficos con ejes.
