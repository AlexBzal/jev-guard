---
name: jev-guard-ui
description: Sistema de diseño y criterios de UX del front de JEV Guard (HTML, CSS y JS sin compilación en ui/). Hace la interfaz fluida, comprensible al primer vistazo y moderna. Use when editing anything under ui/, adding a screen, component, chart or interaction to JEV Guard, or when the user mentions el front, la interfaz, diseño, UX, pantallas, En vivo, Laboratorio, Bandeja o Métricas.
---

# JEV Guard UI

El front de JEV Guard tiene que responder en cinco segundos tres preguntas de quien lo mira por primera vez: **qué está pasando, si es seguro y qué debo hacer**. Todo lo demás se subordina a eso.

Sistema de tokens: [references/tokens.md](references/tokens.md). Componentes: [references/components.md](references/components.md). Verificación: [references/checklist.md](references/checklist.md). Para cualquier gráfico, aplica además la skill `dataviz`.

## Principios

1. **Una tarea por pantalla.** Cada vista tiene un trabajo y una acción primaria:
   - **En vivo:** ver que el sistema funciona ahora. Acción: simular o pausar.
   - **Laboratorio:** entender cómo decide. Acción: cambiar la acción y ver el veredicto.
   - **Bandeja:** decidir lo pendiente. Acción: aprobar o rechazar.
   - **Métricas:** decidir si se puede confiar. Sin acción primaria: es lectura.
2. **La respuesta primero.** El veredicto, la cifra o el estado van arriba. El porqué va debajo, y el detalle técnico se despliega a pedido.
3. **Lenguaje de negocio en la primera capa.** "Impacto alto", no "tier high". "Certeza", no "confidence". Los términos propios (JEV, certeza, impacto, riesgo compuesto) llevan una definición en `term()` la primera vez que aparecen en una vista.
4. **El estado nunca va solo en color.** Permitida, frenada y retenida llevan ícono y texto, siempre.
5. **Nada salta.** Se reserva el espacio de lo que va a cargar con esqueletos. Ningún contenido empuja a otro al llegar.
6. **El movimiento explica.** Se anima solo lo que cambia de estado: una decisión que entra, un número que sube, un paso que se ilumina. Todo respeta `prefers-reduced-motion`.
7. **Teclado de primera clase.** Navegación con 1 a 4, `?` muestra los atajos, la Bandeja se opera con J, K, A y R. Todo elemento interactivo tiene foco visible.
8. **El perfil manda.** Nombres de empresa, agentes, propósitos y acciones propias se leen de `store.profile`. Nunca se escribe el nombre de una empresa en el front.
9. **Honestidad.** Si JEV está simulado, se dice de forma visible en todas las pantallas.

## Cómo trabajar

1. **Antes de tocar:** nombra la tarea de la pantalla y separa lo que debe verse al primer vistazo de lo que espera un clic.
2. **Usa los tokens.** No inventes colores, tamaños ni duraciones. Si falta un token, agrégalo a `tokens.md` y a `:root`.
3. **Escribe contra roles:** `var(--ink-2)` y no un hex; `.badge.allow` y no un verde suelto.
4. **Todo texto que venga de datos pasa por `esc()`.**
5. **Verifica en el navegador** con la lista de [checklist.md](references/checklist.md). Una captura no basta: recorre el flujo.

## Lo que no se hace

- Gráficos de dos ejes, colores de estado usados como series, texto con el color de la serie.
- Pantallas que solo dicen "Cargando…". Se usa un esqueleto con la forma del contenido.
- Modales para lo que cabe en el panel lateral.
- Marcas o nombres de una empresa escritos en el front.
- Dependencias de compilación. El front corre tal cual lo sirve FastAPI.
