# Adoptar JEV Guard en tu empresa

JEV Guard no está atado a ninguna empresa. Todo lo propio de tu negocio vive en un **perfil**: una carpeta con tres archivos YAML. El motor, las reglas y la interfaz se adaptan solos.

```
profiles/<tu-empresa>/
  policy.yaml      agentes, permisos, acciones propias y ajustes del motor
  context.yaml     marca, oferta, políticas, propósitos de correo y listas
  scenarios.yaml   casos etiquetados para medir y calibrar (recomendado)
```

El perfil activo se elige con `JEV_GUARD_PROFILE`. El repositorio trae dos perfiles:

- `demo`: Nimbus, una empresa de software ficticia. Es la plantilla recomendada.
- `30x`: el caso original de la hackathon.

## 1. Crear tu perfil

```bash
cp -r profiles/demo profiles/mi-empresa
JEV_GUARD_PROFILE=mi-empresa python scripts/demo.py
```

En PowerShell, la variable se define con `$env:JEV_GUARD_PROFILE="mi-empresa"`.

## 2. `context.yaml`: tu negocio

JEV juzga contra estos datos. Las preguntas los citan, por ejemplo `context.offer_catalog`, así que JEV no inventa qué ofreces.

| Clave | Para qué sirve |
|---|---|
| `company` | Nombre y descripción. La interfaz y las preguntas la usan. |
| `email_purposes` | Los propósitos de correo que pueden declarar tus agentes. `marketing: true` exige opción de baja en los envíos masivos. `quiet_hours_exempt: true` permite enviar fuera de horario. |
| `brand` | `voice`, `editorial_line` y `forbidden_topics`. Se usan para juzgar el tono y la línea editorial. |
| `offer_catalog` | Lo único que ofreces. Cualquier promesa fuera de aquí es un riesgo. Los códigos de descuento vigentes van en `notes`. |
| `policies` | Reglas que los agentes no pueden contradecir, como plazos de reembolso o tiempos de respuesta. |
| `allowed_link_domains`, `link_shorteners` | Dominios permitidos y acortadores que se envían a revisión. |
| `suppression_list` | Personas dadas de baja. En producción conviene cargarla desde tu proveedor de correo. |
| `confidential_entities` | Clientes o aliados cuyos datos no deben circular. |
| `send_history` | Historial reciente para los topes de frecuencia y los duplicados. En producción se reemplaza por tu fuente real. |

## 3. `policy.yaml`: tus agentes y tus acciones

### Agentes y mínimo privilegio

```yaml
agents:
  agente-ventas:
    name: Agente de ventas
    description: Hace seguimiento a oportunidades
    allowed: [email.send, crm.update]
    max_tier: medium      # por encima de este impacto, la acción va a una persona
```

Un agente no registrado, o que intenta una acción que no tiene permitida, se frena siempre.

### Acciones estándar

Estas acciones ya traen reglas y preguntas: `email.send`, `email.bulk`, `crm.update`, `crm.delete` y `content.publish`. El esquema de cada una está en [ARQUITECTURA.md](ARQUITECTURA.md) y en `/docs` de la API.

### Acciones propias, sin escribir código

Declara cualquier acción de tu negocio: respuestas de soporte, reembolsos, mensajes en Slack, cambios de precio. Cada una define sus campos, cómo se mide su alcance y qué le pregunta el guardián a JEV.

```yaml
custom_actions:
  billing.refund:
    label: Reembolso
    summary_field: customer
    fields:
      - {name: customer, label: Cliente}
      - {name: amount, label: Monto, kind: number}
      - {name: reason, label: Motivo, kind: textarea}
      - {name: message, label: Mensaje al cliente, kind: textarea}
    reversible: false
    scope: {fixed: 1}                    # o {field: recipients} para leer el alcance del contenido
    tier_by_scope: {low: 5, medium: 200, high: 2000}
    common_questions: [goal_alignment, injection_signs, confidential_leak, tone]
    questions:
      - qid: refund_justified
        type: noul
        short: ¿El motivo justifica el reembolso según la política?
        label: El reembolso no está justificado por la política
        instructions: ¿`action.content.reason` justifica un reembolso según `context.policies`?
        risk: yes_is_good                # la respuesta "sí" es la segura
        weight: 0.8
      - qid: refund_size
        type: score
        short: ¿Qué tan inusual es el monto?
        label: Monto de reembolso inusual
        instructions: ¿Qué tan inusual es `action.content.amount` para un reembolso de este cliente?
        criteria: [Habitual, Algo alto, Muy alto, Desproporcionado]   # de menos a más riesgo
        weight: 0.7
```

**Reglas para escribir buenas preguntas.** Son las mismas de la guía de TypeSafe:

- **Un juicio por pregunta.** Combina varias preguntas en lugar de una que mezcle juicios.
- **`noul`:** di si el "sí" es riesgoso (`yes_is_bad`) o seguro (`yes_is_good`).
- **`score`:** ordena los niveles de menos a más riesgo.
- **`choice`:** incluye siempre la opción `other` y asigna el riesgo de cada opción en `risk_by_option`.
- **Peso:** de 0 a 1. Con 0,80 o más, una señal clara frena sola. `critical: true` frena sin importar el impacto.
- **Preguntas comunes reutilizables:** `goal_alignment`, `injection_signs`, `confidential_leak`, `tone`, `unoffered_promise`, `pressure_tactics`, `editorial_fit`, `claims_risk`, `third_party_negative` y `controversy`.

Las acciones propias también pasan por las reglas de texto: secretos, marcadores sin reemplazar, enlaces y datos de contacto.

### Preguntas extra para acciones estándar

```yaml
extra_questions:
  content.publish:
    - qid: mentions_unreleased
      type: noul
      label: Anuncia funciones que todavía no existen
      instructions: ¿La pieza anuncia funciones que no aparecen en `context.offer_catalog`?
      risk: yes_is_bad
      weight: 0.8
```

### Ajustar el motor

Cualquier clave de `config/defaults.yaml` se puede sobrescribir en tu `policy.yaml`. Por ejemplo, umbrales más estrictos para el impacto alto:

```yaml
tiers:
  high: {block: 0.70, review: 0.30}
limits:
  frequency_cap_7d: 2
```

## 4. Integrarlo en tus flujos

Tus agentes llaman al guardián **antes** de ejecutar cada acción y obedecen el veredicto:

- `allow`: ejecutar.
- `block`: no ejecutar y registrar las razones.
- `hold`: esperar a que una persona la resuelva en la bandeja.

**HTTP**, desde n8n, Make, Zapier o cualquier lenguaje:

```bash
curl -X POST https://tu-guardian/v1/guard/check \
  -H "Authorization: Bearer $JEV_GUARD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"agente-soporte","action_type":"support.reply","task":"Responder el ticket 123",
       "content":{"customer":"Ana","subject":"Factura","ticket":"No veo mi factura","reply":"Hola Ana, ..."}}'
```

En n8n o Make, agrega un nodo HTTP antes del paso que ejecuta la acción, y una rama según el campo `verdict`.

**Python**, con el decorador incluido:

```python
from guard.sdk import GuardClient, guarded

guard = GuardClient("https://tu-guardian")

@guarded(guard, "email.send", agent_id="agente-ventas")
def enviar_correo(*, task, to, subject, body, purpose):
    ...  # solo se ejecuta si el guardián lo permite
```

**LangChain u otro framework de agentes:** envuelve cada herramienta que actúa hacia afuera con el decorador, o llama a la API dentro de la herramienta antes de actuar.

**Autenticación:** define `JEV_GUARD_API_KEY` en el servidor y los agentes deberán enviar `Authorization: Bearer <clave>`. La interfaz y la bandeja no tienen autenticación propia; en producción, publícalas detrás de tu proxy o de tu inicio de sesión corporativo.

## 5. Medir y calibrar

1. **Escribe casos etiquetados** en `scenarios.yaml`, con acciones seguras e inseguras de tu negocio. Usa el mismo formato que los perfiles incluidos.
2. **Evalúa:** `python scripts/eval.py --profile mi-empresa`.
3. **Calibra los umbrales:** `python scripts/calibrate.py --profile mi-empresa`.
4. **Exporta el catálogo** para revisarlo con tu equipo: `python scripts/export_questions.py --profile mi-empresa --out docs/mi-empresa.md`.
5. **Arranca en modo sombra** la primera semana: registra todo sin frenar nada, y usa las revisiones humanas como etiquetas para recalibrar.

Con el simulador de JEV, una pregunta propia que el simulador no conoce recibe una respuesta neutra y la acción pasa a una persona. Es el comportamiento seguro. Para medir de verdad tus preguntas propias, usa JEV real con `TYPESAFE_API_KEY`.
