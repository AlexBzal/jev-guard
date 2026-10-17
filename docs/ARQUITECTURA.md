# Arquitectura

```
 Agente de 30X (Python, n8n, Make, LangChain…)
        │  POST /v1/guard/check  {agent_id, action_type, task, …}
        ▼
 ┌──────────────────────────── JEV Guard ─────────────────────────────┐
 │ 1. Validación de esquema (pydantic)               guard/models.py │
 │ 2. Reglas deterministas + tier de impacto         guard/facts.py  │
 │      └─ si una regla frena ─────────────────────► BLOCK (sin JEV) │
 │ 3. Preguntas tipadas, en una sola llamada         guard/questions │
 │ 4. JEV (TypeSafe) o simulador local               guard/jev.py    │
 │ 5. Riesgo y certeza por señal + umbral por tier   guard/policy.py │
 │      ├─ seguro ──────────────────────────────────► ALLOW          │
 │      ├─ riesgo alto y JEV seguro ────────────────► BLOCK          │
 │      ├─ duda en tier bajo o medio ──► LLM (Claude) ► ALLOW/BLOCK  │
 │      └─ duda en tier alto, o regla de revisión ──► HOLD (persona) │
 │ 6. Auditoría en SQLite                            guard/store.py  │
 └────────────────────────────────────────────────────────────────────┘
        │                                   ▲
        ▼                                   │ POST /v1/reviews/{id}
   veredicto + razones                Bandeja de revisión humana
                                            │
                                  etiquetas ► /v1/metrics ► calibrate.py
```

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `guard/models.py` | Esquemas de acciones (unión discriminada por `action_type`), hechos, respuestas de JEV y decisiones |
| `guard/config.py` | Carga `config/policy.yaml` (umbrales, límites, permisos) y `data/context.yaml` (marca, catálogo, listas) |
| `guard/facts.py` | Reglas deterministas con código (E001…P007), conteos y cálculo del tier |
| `guard/questions.py` | Catálogo de preguntas a JEV y la función que traduce cada respuesta a riesgo y certeza |
| `guard/jev.py` | Cliente de la API de TypeSafe, simulador heurístico y fórmulas de confianza |
| `guard/policy.py` | Motor de decisión: riesgo compuesto, señales críticas, dudas y umbrales |
| `guard/llm.py` | Segunda opinión con Claude, con salida JSON estructurada. Si falla, el caso pasa a una persona. |
| `guard/service.py` | Orquesta el flujo y aplica la política de caída de JEV |
| `guard/store.py` | Registro de decisiones, revisiones y etiquetas |
| `guard/metrics.py` | Automatización, latencia, costo y calidad frente a etiquetas |
| `guard/api.py` | API HTTP con FastAPI |
| `guard/sdk.py` | Cliente y decorador `@guarded` para agentes |
| `guard/events.py` | Bus de eventos para el flujo en vivo (SSE) |
| `guard/demo.py` | Generador de tráfico de agentes simulados para la demo |
| `ui/` | Interfaz: `index.html`, `css/app.css`, `js/app.js` (enrutador y conexión en vivo), `js/views/*` (cuatro pantallas), `js/charts.js` (gráficos SVG) |

## Estado que ve JEV

```json
{
  "task":    "instrucción que recibió el agente",
  "action":  { "...contenido de la acción, sin identificadores..." },
  "facts":   { "recipient_count": 1, "external_domains": [], "record_count": 0 },
  "context": { "brand": {}, "offer_catalog": [], "confidential_entities": [] }
}
```

Las preguntas referencian campos del estado con comillas invertidas, por ejemplo `` `context.offer_catalog` ``. Así JEV juzga contra el catálogo real y no contra lo que imagina.

## Endpoints

| Método y ruta | Uso |
|---|---|
| `POST /v1/guard/check` | Evalúa una acción y devuelve el veredicto, las razones, las señales, la latencia y el costo. Con `?sandbox=true` no se guarda ni cuenta en métricas. |
| `GET /v1/stream` | Flujo en vivo de decisiones y revisiones (Server-Sent Events) |
| `GET /v1/scenarios` | Casos preparados para el Laboratorio |
| `GET` y `POST /v1/demo/traffic` | Estado, arranque y parada de los agentes simulados, solo con `JEV_GUARD_DEMO=1` |
| `GET /v1/decisions` | Registro de auditoría, con filtros |
| `GET /v1/decisions/{id}` | Detalle de una decisión, con la acción completa |
| `GET /v1/reviews/pending` | Bandeja de retenidas |
| `POST /v1/reviews/{id}` | Una persona aprueba o rechaza: `{approve, reviewer, note}` |
| `POST /v1/decisions/{id}/label` | Etiqueta de auditoría sobre cualquier decisión |
| `GET /v1/metrics` | Métricas de operación y calidad |
| `GET /v1/policy` | Política activa y catálogo de preguntas |
| `DELETE /v1/decisions` | Limpia el registro, solo con `JEV_GUARD_DEMO=1` |

## Variables de entorno

| Variable | Efecto |
|---|---|
| `TYPESAFE_API_KEY` | Activa JEV real. Sin ella se usa el simulador. |
| `JEV_GUARD_SIMULATE=1` | Fuerza el simulador aunque haya clave |
| `JEV_SIM_LATENCY=1` | El simulador espera una latencia realista de 70 a 300 ms |
| `ANTHROPIC_API_KEY` | Activa la segunda opinión con Claude |
| `JEV_GUARD_LLM=0` | Desactiva el LLM aunque haya credenciales |
| `JEV_GUARD_DB` | Ruta de la base SQLite, por defecto `data/runtime/guard.db` |
| `JEV_GUARD_NOW` | Fija el reloj en ISO 8601, para demos reproducibles |
| `JEV_GUARD_DEMO=1` | Habilita el borrado del registro |
| `JEV_GUARD_POLICY`, `JEV_GUARD_CONTEXT` | Rutas alternativas de configuración |

## Reglas deterministas

| Código | Severidad | Regla |
|---|---|---|
| G001, G002 | frena | Agente no registrado, o sin permiso para ese tipo de acción |
| G003 | revisión | El impacto supera el tier máximo del agente |
| G004 | revisión | La acción excede el contexto de JEV |
| T001 | frena | Secretos: claves de API, tokens, contraseñas, tarjetas válidas por Luhn |
| T002 | frena | Marcadores sin reemplazar, etiquetas desconocidas, borradores |
| T003, T004 | revisión | Acortadores de enlaces y dominios fuera de la lista permitida |
| E001 | frena | Destinatarios dados de baja |
| E003, E008 | frena | Correo inválido, asunto o cuerpo vacíos |
| E006 | revisión | Tope de frecuencia semanal |
| E007 | revisión o frena | Fuera de horario: revisión en individuales, frena en masivos |
| E009 | frena | Mismo correo a la misma persona en 24 h |
| E010 | revisión | Más de 50 destinatarios en un envío individual |
| E011 | revisión | Direcciones de terceros en el cuerpo, posible filtración |
| B001 | frena | Campaña de marketing sin opción de baja |
| B002 | revisión o frena | Más destinatarios que el segmento esperado: revisión desde 1,5 veces, frena desde 3 |
| B003 | revisión | Segunda llave humana desde 5.000 destinatarios |
| C001 | revisión | Campos protegidos del CRM |
| C002 | revisión | Cambio de monto de 50 % o más |
| C003 | frena o revisión | Sin filtro ni IDs frena; más de 2.000 registros va a revisión |
| C004 | frena o revisión | Borrado sin motivo frena; más de 100 registros va a revisión |
| C005 | revisión | Cambio sobre un negocio ya ganado |
| C007 | revisión | Borrar negocios |
| P001, P002 | frena | Límite de caracteres de la plataforma, publicación vacía |
| P006 | revisión | Datos de contacto personales en una publicación |
| P007 | revisión | Cifras sin fuente citada |
