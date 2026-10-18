# Bitácora de desarrollo

Registro cronológico de lo que se construyó, por qué y qué se encontró en el camino.
Incluye los errores y los resultados malos, porque son parte de la evidencia.

## 2026-10-17: backend, evaluación y documentación

### 1. Lectura del reto y de JEV

- **Reto:** "¿Qué decisiones de 30X podría tomar JEV miles de veces al día?" Se eligió la idea de *guardrails para agentes internos*.
- **Fuentes de JEV:** docs.typesafe.ai (inicio rápido, primitivas, confianza, patrones) y la guía de DigitalOcean.
- **Datos clave de la API:** `POST https://api.typesafe.ai/v1/systemone` con `state`, `model` y `questions`. Hay tres tipos de pregunta: `choice` (devuelve `choice`, `probabilities` y `confidence`), `score` (devuelve `score`, `legend`, `probabilities` y `confidence`) y `noul` (devuelve solo `noul`, la probabilidad de sí).
- **Fórmulas de confianza publicadas.** Choice usa `(p_max - 1/n) / (1 - 1/n)`. Score usa la dispersión ordinal frente a una distribución uniforme. Noul no tiene confianza; se usa `|2p - 1|`, como sugieren las docs.
- **Por qué este caso gana:** es el único donde la latencia es obligatoria, porque el agente espera la respuesta para actuar. Además el volumen es de miles de acciones diarias y el costo de un error es visible.

### 2. Decisiones de arquitectura

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Reglas deterministas antes de JEV | Preguntarle todo a JEV | JEV no cuenta ni compara fechas. Además, si una regla ya frena la acción, se ahorra la llamada. |
| Una pregunta por juicio y combinación en código | Una pregunta "¿es segura?" | Recomendación explícita de TypeSafe. Además permite explicar qué se activó. |
| Una sola llamada por acción con 5 a 8 preguntas | Varias llamadas | El patrón *speculative fan-out*: cada pregunta adicional casi no suma latencia. |
| Umbrales por tier de impacto | Umbral único | Un correo a una persona no merece la misma vara que una campaña a 8.000. |
| "OR ruidoso" con piso de ruido 0,20 | Promedio ponderado | El promedio diluye una señal fuerte entre muchas débiles. Sin el piso, diez señales de 0,1 sumaban una falsa alarma. Hay una prueba para eso. |
| Certeza mínima por tier | Frenar con cualquier riesgo alto | JEV puede equivocarse con confianza, pero cuando no la tiene no hay que frenar a ciegas: se escala. |
| Escalado a LLM solo en tiers bajo y medio | LLM en todo lo dudoso | En lo crítico la segunda opinión debe ser humana. |
| Si JEV cae: deja pasar en tier bajo y retiene en el resto | Fallar siempre cerrado | Fallar siempre cerrado paraliza a todos los agentes durante una caída. Queda configurable. |
| Simulador local de JEV | Exigir la clave para correr | El reto pide que el prototipo corra fuera de los sistemas de 30X. El simulador se marca como tal en cada decisión. |
| SQLite como auditoría | Base externa | No requiere infraestructura y basta para el prototipo. |
| SDK oficial de Anthropic para la segunda opinión | Llamadas HTTP a mano | Salida JSON estructurada, manejo de rechazos y modelos de respaldo del lado del servidor. |

### 3. Construcción

Orden de construcción: modelos (`guard/models.py`), política y contexto en YAML, reglas (`guard/facts.py`), catálogo de preguntas (`guard/questions.py`), cliente real y simulador (`guard/jev.py`), motor de decisión (`guard/policy.py`), LLM (`guard/llm.py`), auditoría (`guard/store.py`), métricas (`guard/metrics.py`), orquestación (`guard/service.py`), API (`guard/api.py`) y SDK (`guard/sdk.py`).

### 4. Errores encontrados y corregidos

1. **Lista de palabras vacías mal construida.** El simulador fallaba al importar porque se normalizaba una lista en vez de un texto.
2. **Falsos bloqueos en todas las campañas.** La regla de marcadores sin reemplazar buscaba `{first_name}` y también coincidía dentro de `{{first_name}}`, que es una etiqueta válida del proveedor de correo. Se corrigió la expresión regular y se agregó una prueba.
3. **"TODO" frente a "todo".** La regla de borradores buscaba "TODO" sin distinguir mayúsculas, así que la palabra española "todo" bloqueaba publicaciones normales. Ahora solo cuenta en mayúsculas, y hay una prueba para eso.
4. **Prueba del LLM que no probaba nada.** Era condicional a que JEV dudara. Se reescribió con un JEV falso que siempre duda, para forzar el camino del escalado.
5. **Cifras sin fuente frente a la marca.** La primera versión de la regla P007 confundía "30X" con "30 veces". Se quitó ese patrón.

### 5. Evaluación

**Conjunto de desarrollo:** `data/scenarios.yaml`, 49 casos escritos a mano, 15 seguros y 34 inseguros. El vocabulario del simulador se ajustó mirando estos casos, así que este resultado está sesgado a favor.

| Medida | Resultado |
|---|---|
| Coinciden con lo esperado | 49 de 49 |
| Inseguras que pasaron solas | 0 |
| Seguras bloqueadas | 0 % |

**Conjunto independiente:** `data/scenarios_holdout.yaml`, 30 casos, 12 seguros y 18 inseguros. Los escribió un agente aparte con la instrucción explícita de no leer el código del guardián, usando paráfrasis distintas de las palabras obvias.

| Medida | Primera corrida, sin ver los casos | Tras corregir el diseño |
|---|---|---|
| Coinciden con lo esperado | 20 de 30 | 24 de 30 |
| Inseguras detenidas | 78 % | 89 % |
| Inseguras que pasaron solas | 4 | 2 |
| Seguras bloqueadas | 8 % | 0 % |
| Seguras enviadas a una persona | 4 | 4 |

La primera columna es la medida honesta de generalización. La segunda ya no es independiente, porque se miraron los casos para corregir. Se corrigieron **solo fallas de diseño**, no el vocabulario del simulador:

- **La inyección venía en la tarea.** El agente recibió un correo entrante con instrucciones y lo copió en la tarea. La pregunta de inyección ahora mira también `task`.
- **Filtración de una lista de asistentes.** Nueva regla E011: un correo con 3 o más direcciones de otras personas en el cuerpo va a revisión.
- **Avisos a alumnos sin "darse de baja".** La regla B001 ahora aplica solo a comunicaciones de marketing.
- **Borrado de un negocio tomado por duplicado.** Nueva regla C007: borrar negocios siempre requiere una persona.
- **Publicación con estadísticas sin fuente.** Nueva regla P007: cifras sin fuente citada van a revisión.

Las 2 que siguen pasando solas son paráfrasis semánticas: "pagas solo la mitad", y una fuga que describe al cliente sin nombrarlo. Un simulador por palabras clave no puede verlas, y es exactamente el trabajo que debe hacer JEV. No se parchearon para no maquillar el resultado. **Son los primeros casos que hay que probar con JEV real.**

**Calibración:** `scripts/calibrate.py` confirma que los umbrales actuales no dejan pasar inseguras en el conjunto de desarrollo. Los datos por tier son pocos y el resultado es orientativo.

**Rendimiento:** con `scripts/bench.py` y 3.000 decisiones en un solo proceso se obtienen unas 800 decisiones por segundo. La sobrecarga propia del guardián es de 1 a 2 ms en p50 y p95. En producción domina la latencia de JEV, de 70 a 500 ms según TypeSafe.

**Costo:** unos 1.070 tokens de entrada por llamada, estimados en modo simulado. Eso da 0,033 USD por 1.000 decisiones con JEV, frente a unos 6 USD con Claude Opus 5.5 como juez, unas 180 veces más.

**Prueba de punta a punta:** con el servidor real en uvicorn y 60 acciones de agentes simulados con revisión automática, quedaron 27 permitidas, 14 frenadas y 19 retenidas. El p95 fue de 9 ms y la cola de revisión se resolvió.

## 2026-10-17: interfaz

El plan de [UI_PLAN.md](UI_PLAN.md) se aprobó con el stack sin compilación.

### Backend agregado

- **Flujo en vivo:** `GET /v1/stream` con Server-Sent Events. Las decisiones se toman en hilos y los suscriptores viven en asyncio; `guard/events.py` cruza esa frontera con `call_soon_threadsafe`. Un cliente lento pierde eventos viejos y no frena a los demás.
- **Modo de prueba:** `?sandbox=true`. El Laboratorio decide igual, pero no guarda, no publica y no cuenta en métricas.
- **Tráfico simulado dentro del servidor:** `guard/demo.py` usa los casos como plantillas, con más peso para los seguros, y etiqueta cada decisión con la verdad del caso para que las métricas de calidad aparezcan desde el primer minuto.
- **Reloj fijo en modo demo**, para que horarios e historial coincidan con los casos.
- Resumen legible de cada acción, severidad en las razones de reglas e histograma de latencia en las métricas.

### Interfaz

HTML, CSS y módulos de JavaScript, servidos en `/` por la misma API. Diseño según la guía de visualización:

- Veredictos con la paleta de estado reservada, siempre con ícono y texto.
- Gráficos de una serie en un solo tono, barras de máximo 24 px con extremo redondeado y separación de 2 px.
- Tooltip en cada marca y vista de tabla en cada gráfico.
- Modo claro y oscuro seleccionados, no invertidos.
- El costo de JEV frente al LLM juez se muestra como cifras y no como barras: con una diferencia de unas 180 veces, la barra de JEV sería invisible.

### Errores encontrados al mirar la interfaz en un navegador real

1. **Una señal fuerte no podía frenar sola.** En el Laboratorio, un descuento falso daba riesgo de 0,99 con certeza de 0,98, pero el compuesto quedaba en 0,84, justo bajo el umbral de 0,85 del impacto bajo. La causa: el peso de la señal, 0,85, limita el compuesto. Se agregó la regla de "señal fuerte": peso de 0,80 o más, riesgo sobre el umbral de frenado y certeza suficiente. Los dos conjuntos de evaluación dieron los mismos resultados con la regla nueva, y se agregaron 2 pruebas.
2. **Mensaje engañoso.** Decía "JEV tuvo dudas" cuando el motivo era riesgo moderado. Ahora se distinguen los dos casos.
3. **Medidor de riesgo vacío.** Al relleno del medidor compuesto le faltaba la regla de color.
4. **Señales confusas.** Se mostraba la frase de riesgo ("no corresponde a la tarea") junto a la respuesta a la pregunta contraria ("Sí, 99 %"). Cada pregunta tiene ahora una versión corta en lenguaje claro, y la interfaz muestra pregunta y respuesta.
5. **Posible ciclo de redibujo** en Métricas: el observador de tamaño reaccionaba a la altura. Ahora solo reacciona al ancho.

### Verificación

- Recorrido automatizado en un navegador sin interfaz. Arranca los agentes, abre un detalle, aplica el descuento falso en el Laboratorio (pasa de "Permitida" a "Frenada") y recorre Bandeja y Métricas en modo claro y oscuro.
- Resultado: 0 errores de consola y 0 peticiones fallidas.
- La página carga en unos 650 ms.
- 56 pruebas automatizadas pasan.

## 2026-10-18: despliegue en Render y versión abierta para cualquier empresa

### Preparación del despliegue

- `render.yaml` para el plan gratis de Render, con el modo demo y la base en `/tmp` porque el disco no persiste.
- Los agentes simulados se apagan solos a los 10 minutos, para que un visitante del enlace público no los deje encendidos. La interfaz refleja el apagado.
- Se probó en local el mismo comando de arranque que usa Render.

### De caso 30X a producto abierto

Se separó el núcleo genérico de la configuración de cada empresa:

- **Perfiles.** `config/defaults.yaml` guarda el motor y `profiles/<empresa>/` guarda el negocio: política, contexto y casos. El perfil se elige con `JEV_GUARD_PROFILE`. 30X queda como un perfil de ejemplo, y `demo` (Nimbus, una empresa de software ficticia) es el perfil por defecto y la plantilla.
- **Preguntas sin nombres propios.** Ahora citan `context.company`, `context.brand` y `context.policies`. La pregunta de propósito del correo se arma con los propósitos del perfil.
- **Propósitos configurables.** Cada propósito declara si es de marketing, lo que exige opción de baja, y si puede enviarse fuera de horario. Un propósito no registrado se frena (E012).
- **Acciones propias sin código.** Se declaran en `custom_actions` con sus campos, su alcance, su reversibilidad, preguntas comunes reutilizadas y preguntas nuevas en YAML, validadas al arrancar. Pasan por las reglas de texto y por el mismo motor. Un tipo no declarado se frena (G005). Nimbus trae la respuesta de soporte como ejemplo.
- **Preguntas extra** para las acciones estándar, vía `extra_questions`.
- **Clave opcional para agentes** con `JEV_GUARD_API_KEY`.
- **Interfaz** con el nombre de la empresa, los agentes, los propósitos y las acciones propias leídos del perfil, a través de `GET /v1/profile`.
- **Guía de adopción** en [PERFILES.md](PERFILES.md). Sus ejemplos YAML se validan en una prueba automática.

### Evaluación del perfil genérico

Un agente aparte escribió 44 casos para Nimbus, con 16 seguros y 28 inseguros, sin ver el código del guardián. Incluyen 8 respuestas de soporte.

| Medida | Primera corrida, sin ver los casos | Tras quitar lo fijo de 30X del simulador |
|---|---|---|
| Coinciden con lo esperado | 34 de 44 | 37 de 44 |
| Inseguras que pasaron solas | 1 | 1 |
| Seguras frenadas por error | 2 de 16 | 0 |

La primera columna es la medida honesta. La segunda ya no es independiente. Lo que se corrigió fue una falla de generalización real: el simulador tenía fijos el código de descuento de 30X (EARLY10), el vocabulario editorial sobre IA y los propósitos de correo de 30X. Ahora los lee del perfil: catálogo, línea editorial y descripciones de propósitos. También se ajustó una heurística de alcance que leía "del contacto" como un solo registro aunque fueran duplicados.

La inyección en una nota del CRM, redactada con frases que el vocabulario del simulador no conoce, sigue pasando sola. No se parcheó, por la misma razón que en el perfil 30X: es lo que debe resolver JEV real.

Con estos cambios, el perfil 30X sigue en 49 de 49 en desarrollo y mejora de 24 a 27 de 30 en su conjunto independiente, con las mismas 2 paráfrasis sin detectar.

### Errores encontrados

1. **Una edición dejó un salto de línea literal dentro de un texto de JavaScript.** Todos los módulos que importaban ese archivo fallaron, y la interfaz quedó en blanco sin errores visibles en la consola. La comprobación con `node --check` no lo detectó, porque trata el archivo como CommonJS. Se agregó una prueba que importa cada módulo de la interfaz con Node.
2. **El ejemplo con `curl` del README fallaba en Windows,** porque `curl` envía los acentos con la codificación local. El ejemplo quedó sin acentos y con una nota.

## 2026-10-18: rediseño del front con una skill de diseño propia

No había una skill de diseño aplicable: la única instalada pertenece a otro producto, con su propia marca. Se creó la skill de proyecto `.claude/skills/jev-guard-ui/` con `skill-creator`. Recoge los principios de UX (una tarea por pantalla, la respuesta primero, lenguaje de negocio, estado nunca solo en color, nada salta, movimiento que explica, teclado de primera clase), los tokens del sistema de diseño, el inventario de componentes y la lista de verificación. Se complementa con la skill `dataviz` para los gráficos.

### Cambios aplicados

- **Estructura:** barra lateral con navegación, empresa activa y estado del motor. En móvil pasa a una barra inferior. Transiciones suaves entre vistas.
- **En vivo:** acción primaria en el encabezado, cifra principal animada con tendencia del último minuto, y el bloque "cómo se decidió cada acción", que muestra cuántas resolvió cada capa (reglas, JEV, LLM) y la proporción de veredictos. El flujo se pausa al pasar el cursor para poder leerlo.
- **Laboratorio:** la respuesta primero. El veredicto, la ruta y las razones van arriba, y los pasos van debajo en tarjetas plegables que recuerdan si las abriste. La columna del resultado queda fija.
- **Bandeja:** bandeja de entrada de dos columnas, operable con J, K, A y R. La decisión es optimista y se puede deshacer durante 4 segundos. Se guarda aunque se cierre la pestaña.
- **Métricas:** una frase en lenguaje claro resume si se puede confiar, antes de las cifras y los gráficos.
- **Comprensión:** los términos propios (JEV, impacto, certeza, riesgo, reglas, retenida) tienen su definición al pasar el cursor o con el teclado.
- **Fluidez:** esqueletos de carga en lugar de "Cargando…", contadores animados y tiempos relativos.
- **Accesibilidad:** diálogo de atajos con `?`, tooltips también con el teclado, movimiento reducido respetado.

### Verificación

- Recorrido en navegador según la lista de la skill. Se verificó el arranque de agentes con Espacio, el descuento falso que pasa a "Frenada" en el Laboratorio, la Bandeja con J, R y Deshacer (de 100 a 99 y de nuevo a 100, con la selección restaurada), las Métricas, el modo oscuro y el móvil a 390 px sin desplazamiento horizontal.
- Cero errores de consola y cero peticiones fallidas.
- Ningún nombre de empresa escrito en `ui/`.
- 77 pruebas automatizadas pasan.

### Encontrado y corregido durante la verificación

- El fondo de la barra lateral terminaba en las páginas largas.
- La lista de la Bandeja mostraba el identificador técnico del agente en lugar de su nombre.
- El atajo "Espacio" aparecía en el botón en móvil, donde no aplica.

### Pendiente

- Correr `scripts/smoke_jev.py` y `scripts/eval.py` con una clave real de TypeSafe. Validar que las instrucciones en español rinden bien, especialmente en las preguntas propias de cada perfil, y comparar contra el simulador.
