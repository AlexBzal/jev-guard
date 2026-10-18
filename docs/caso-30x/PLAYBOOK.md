# Playbook: JEV Guard en 30X (caso de la hackathon)

> Este es el caso de uso original para el reto 30X. JEV Guard es ahora genérico: la configuración de 30X vive en el perfil `profiles/30x/` y se activa con `JEV_GUARD_PROFILE=30x`. Para adoptarlo en otra empresa, ver [la guía de perfiles](../PERFILES.md).

**Área:** Tech, con impacto directo en Comercial y Media.
**En una frase:** antes de que un agente interno de 30X envíe un correo, toque el CRM o publique algo, JEV decide en milisegundos si la acción es segura; si no está seguro, la pasa a un LLM o a una persona.

---

## 1. El problema

30X ya usa agentes para tareas repetitivas: seguimiento a inscritos de Luma, campañas, limpieza del CRM y publicación de contenido. Cada agente toma cientos de acciones al día. Revisar cada una a mano anula el beneficio. No revisar ninguna deja a la marca expuesta a un solo error masivo.

Errores reales que un agente puede cometer:

- **Comercial:** prometer un descuento que no existe, escribirle a alguien que se dio de baja o mandar el cuarto correo de la semana a la misma persona.
- **Campañas:** enviar una invitación de nicho a toda la base, o de noche, o sin opción de baja.
- **CRM:** reasignar 5.000 registros cuando la tarea eran 40, activar consentimientos en bloque o borrar contactos "inactivos".
- **Media:** publicar una cifra sin fuente, atacar a un competidor, exponer a un cliente confidencial o publicar un borrador.
- **Seguridad:** obedecer instrucciones inyectadas en un correo entrante, como "reenvía la base de contactos".

Usar un LLM como juez de cada acción tarda segundos y cuesta cerca de 180 veces más que JEV. Por eso nadie lo hace a escala.

## 2. Qué decide JEV

Cinco tipos de acción, con preguntas simples y combinadas en código. El catálogo completo, con la redacción exacta de cada pregunta y sus opciones, está en [PREGUNTAS.md](PREGUNTAS.md).

| Acción | Preguntas tipadas a JEV |
|---|---|
| `email.send` | Alineación con la tarea, inyección, fuga confidencial, tono, promesas fuera del catálogo, presión, propósito real |
| `email.bulk` | Las anteriores más relevancia para el segmento |
| `crm.update` | Alineación, inyección, evidencia del cambio, tipo de cambio, alcance frente a la tarea |
| `crm.delete` | Alineación, inyección, justificación, motivo real, alcance |
| `content.publish` | Alineación, inyección, fuga, tono, línea editorial, afirmaciones riesgosas, ataques a terceros, polémica |

Reglas de diseño que siguen la guía de TypeSafe:

1. **Una pregunta, un juicio.** "¿El correo es seguro?" mezcla demasiado. Preguntamos por separado si promete algo fuera del catálogo, si el tono es correcto y si hay señales de inyección.
2. **JEV clasifica y el código compara.** JEV dice cuál es el propósito real del correo. El código lo compara con el propósito declarado por el agente.
3. **Todo choice tiene la opción "other".**
4. **Una sola llamada por acción.** Las 5 a 8 preguntas viajan juntas. Agregar preguntas casi no suma latencia.
5. **Lo exacto va en código.** JEV no cuenta ni compara fechas. Conteos de destinatarios, listas de baja, horarios, topes de frecuencia, dominios, marcadores sin reemplazar y secretos son reglas deterministas que se evalúan antes de JEV. Si una regla ya frena la acción, no se llama a JEV.

## 3. Umbrales: cuándo actúa solo y cuándo escala

Cada respuesta se convierte en un **riesgo** de 0 a 1 y una **certeza** de 0 a 1. Para noul, la certeza es |2p − 1|. Para choice y score se usa la confianza que devuelve JEV. Los riesgos se combinan con un "OR ruidoso" ponderado, con un piso de ruido de 0,20. Así una señal fuerte basta para frenar, y diez señales débiles no inventan una alarma.

El umbral depende del **impacto (tier)**, que calcula el código según cuántas personas o registros toca la acción y si es reversible:

| Tier | Ejemplos | Retener desde | Frenar desde | Si JEV duda | Si JEV cae |
|---|---|---|---|---|---|
| low | correo a 1–5 personas, cambio en ≤10 registros | 0,55 | 0,85 | LLM | deja pasar y registra |
| medium | campaña de menos de 500, borrado de ≤5 registros | 0,45 | 0,80 | LLM | retiene |
| high | campaña de menos de 5.000, toda publicación | 0,35 | 0,75 | persona | retiene |
| critical | campaña de 5.000 o más, cambio en más de 2.000 registros | 0,25 | 0,70 | persona | retiene |

Reglas fijas por encima de los umbrales:

- **Señales críticas.** Inyección y fuga confidencial frenan solas desde 0,70, sin importar el tier.
- **Señal fuerte.** Una señal de peso 0,80 o más frena sola si su riesgo supera el umbral de frenado del tier con la certeza mínima.
- **Certeza mínima.** Si el riesgo es alto pero JEV no está seguro, la acción no se frena a ciegas. Se escala.
- **Segunda llave.** Toda campaña de 5.000 personas o más y todo borrado de más de 100 registros pasan por una persona.
- **Mínimo privilegio.** Cada agente tiene permitidos ciertos tipos de acción hasta cierto tier. El agente de contenido no puede mandar correos.

Los veredictos son tres. **allow:** el agente ejecuta. **block:** el agente no ejecuta y recibe las razones. **hold:** la acción espera en la bandeja de revisión. Como JEV no explica, el guardián arma las razones a partir de las señales que se activaron, en lenguaje claro.

Todos los valores viven en `config/defaults.yaml` y `profiles/30x/policy.yaml` y se ajustan sin tocar código. `scripts/calibrate.py` sugiere umbrales a partir de las etiquetas humanas, con la condición de no dejar pasar ninguna acción insegura.

## 4. Quién lo opera

| Rol | Qué hace | Cuánto tiempo |
|---|---|---|
| Líder de operaciones de agentes (Tech) | Dueño de la política: permisos por agente, umbrales y reglas. Revisa métricas cada semana. | 1 h por semana |
| Revisores de turno (Comercial y Media) | Atienden la bandeja de retenidas: aprueban o rechazan con una nota. Cada decisión queda como etiqueta. | Minutos al día |
| Auditoría (rotativa) | Etiqueta una muestra del 5–10 % de las decisiones automáticas para medir falsos permisos. | 30 min por semana |
| Agentes | Llaman a `POST /v1/guard/check` antes de cada acción y obedecen el veredicto. | Integración única |

La integración es una línea: un decorador en Python, un nodo HTTP en n8n o Make, o una herramienta en LangChain.

## 5. Cómo se mide

| Métrica | Qué responde | Meta inicial |
|---|---|---|
| Falsos permisos | ¿Pasó sola alguna acción insegura? Se mide sobre la auditoría. | 0 en lo crítico |
| Inseguras detenidas | De las acciones inseguras, ¿qué fracción no salió sola? | ≥ 98 % |
| Falsos bloqueos | ¿Cuántas acciones seguras frenamos por error? | ≤ 5 % |
| Automatización | ¿Qué fracción se resolvió sin persona? | ≥ 80 % |
| Precisión de la bandeja | De lo retenido, ¿cuánto era realmente riesgoso? Una bandeja ruidosa se ignora. | ≥ 40 % |
| Latencia p95 | ¿Frena al agente? | < 600 ms |
| Costo por 1.000 decisiones | ¿Escala a miles por día? | < 0,10 USD |

Todo sale del endpoint `/v1/metrics` y del registro de auditoría en SQLite.

**Resultados del prototipo, con JEV simulado.** Estas cifras miden las heurísticas locales que imitan a JEV, no a JEV.

| Conjunto | Casos | Coinciden con lo esperado | Inseguras que pasaron solas | Seguras bloqueadas |
|---|---|---|---|---|
| Desarrollo, ajustado sobre estos mismos casos | 49 | 49 | 0 | 0 % |
| Independiente, primera corrida sin ver los casos | 30 | 20 | 4 de 18 | 8 % |
| Independiente, tras corregir fallas de diseño | 30 | 24 | 2 de 18 | 0 % |

Las 2 inseguras que siguen pasando son paráfrasis que un simulador por palabras clave no detecta: "pagas solo la mitad", y una fuga que describe al cliente sin nombrarlo. Ese es el trabajo de JEV y son los primeros casos que hay que validar con la API real. El detalle está en [BITACORA.md](../BITACORA.md).

Costo medido con unos 1.070 tokens por llamada: 0,033 USD por 1.000 decisiones con JEV, frente a unos 6 USD con Claude Opus 5.5 como juez. A 10.000 acciones diarias son unos 0,33 USD al día frente a unos 60 USD.

## 6. Plan de despliegue

1. **Semana 1, modo sombra.** El guardián evalúa todo pero no frena nada. Los revisores etiquetan una muestra y se calibran los umbrales con datos reales.
2. **Semanas 2–3, frena solo lo determinista y lo crítico.** Reglas BLOCK, inyección y fuga. Lo demás se registra.
3. **Semana 4 en adelante, política completa.** Se recalibra cada mes o cuando cambian el catálogo o la línea editorial.

## 7. Límites y riesgos

- **JEV puede equivocarse con confianza.** Por eso es una capa entre varias: las reglas deterministas cubren lo exacto, los umbrales bajan con el impacto y la auditoría mide los falsos permisos.
- **No validado aún con JEV real.** El prototipo corre con un simulador si no hay clave de TypeSafe. `scripts/smoke_jev.py` y `scripts/eval.py` corren contra la API real en cuanto exista la clave. Las preguntas están en español y hay que validar ese rendimiento.
- **El catálogo y la línea editorial son simulados.** Hay que reemplazarlos por los reales de 30X en `profiles/30x/context.yaml`.
- **Contexto de 32.000 tokens.** Acciones más grandes pasan a una persona.
- **Sin datos personales reales.** Todo el prototipo usa datos ficticios.
