# Plan de la interfaz (aprobado y construido el 2026-10-17)

## Objetivo

Una demo de 3 minutos donde el jurado **vea** a JEV decidir, dudar y escalar, en tiempo real y con el costo a la vista. La interfaz no es un panel administrativo genérico: cada pantalla responde una pregunta del jurado.

| Pantalla | Pregunta del jurado que responde |
|---|---|
| 1. En vivo | ¿De verdad decide miles de veces, rápido y barato? |
| 2. Laboratorio | ¿Cómo decide? ¿Qué le pregunta a JEV? |
| 3. Bandeja | ¿Qué pasa cuando no está seguro? ¿Quién lo opera? |
| 4. Métricas | ¿Cómo saben que funciona? |

## 1. En vivo

- Flujo de tarjetas que entran en tiempo real: agente, tipo de acción, veredicto con color, latencia y una línea con la razón principal.
- Cuatro indicadores arriba: decisiones, porcentaje resuelto sin persona, latencia p95 y costo acumulado de JEV junto al costo que habría tenido un LLM juez.
- Botón "Simular un día de agentes" que arranca y detiene el tráfico desde la propia interfaz.
- Clic en una tarjeta abre el detalle, igual que en el Laboratorio.

## 2. Laboratorio (el momento "wow")

- A la izquierda, un editor de la acción: se elige un agente y un caso preparado, o se edita el texto libremente.
- A la derecha, el recorrido de la decisión en cuatro pasos que se iluminan en orden:
  1. **Reglas:** qué se verificó en código, con sus códigos.
  2. **JEV:** cada pregunta tipada con su respuesta, una barra de probabilidad y la certeza.
  3. **Política:** un medidor de riesgo con los umbrales del tier marcados.
  4. **Veredicto:** con las razones en lenguaje claro.
- Guion de la demo: un correo correcto pasa. Se agregan las palabras "50 % de descuento" y en menos de un segundo pasa a bloqueado, mostrando qué pregunta lo detectó.

## 3. Bandeja de revisión

- Lista de acciones retenidas, con la razón por la que JEV dudó y las señales.
- Botones "Aprobar" y "Rechazar" con una nota opcional.
- Mensaje visible de que cada revisión se vuelve una etiqueta que alimenta las métricas y la calibración.

## 4. Métricas

- Calidad: inseguras detenidas, falsos permisos, falsos bloqueos y precisión de la bandeja.
- Distribución por ruta: reglas, JEV, LLM y persona.
- Costo por 1.000 decisiones frente al LLM juez.
- Histograma de latencia.
- Un aviso permanente cuando JEV está simulado, para no confundir al jurado.

## Cambios necesarios en el backend

- `GET /v1/stream`: eventos del servidor (SSE) con cada decisión nueva, para el flujo en vivo.
- `GET /v1/scenarios`: casos preparados para el Laboratorio.
- `POST /v1/demo/traffic` para arrancar y detener el tráfico simulado, solo en modo demo.
- La evaluación en el Laboratorio no debe ensuciar las métricas de producción: se marca como prueba.

## Opciones de stack

**Recomendado: HTML, CSS y JavaScript sin paso de compilación**, servidos por la misma API en `/`.
- Arranca con un solo comando, sin Node, que es lo más robusto para correr fuera de los sistemas de 30X y en el computador del jurado.
- Los gráficos se hacen en SVG propio siguiendo la guía de visualización de datos, con modo claro y oscuro.

**Alternativa: React con Vite y TypeScript.**
- Más cómodo para crecer después de la hackathon.
- Exige Node y un paso de compilación para la demo.

## Identidad visual

Sobria, con mucho espacio. Tres colores de estado bien diferenciados para permitido, frenado y retenido, legibles también para personas con daltonismo. Interfaz en español, sin jerga técnica en las pantallas que ve el jurado.
