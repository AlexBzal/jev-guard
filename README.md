# JEV Guard

Un guardián abierto y configurable para los agentes de IA de cualquier empresa. Antes de que un agente envíe un correo, lance una campaña, modifique el CRM, publique contenido o ejecute cualquier acción propia de tu negocio, **JEV** (TypeSafe AI) decide en milisegundos y por fracciones de centavo si es seguro. Lo dudoso pasa a un LLM; lo crítico, a una persona.

- **Sin código para adoptarlo:** tu empresa se describe en un perfil YAML con marca, oferta, políticas, agentes y permisos.
- **Acciones propias declarativas:** soporte, reembolsos, Slack o lo que uses, con sus propias preguntas tipadas a JEV.
- **Tres capas de decisión:** reglas en código para lo exacto, JEV para el juicio rápido y un LLM o una persona para la duda.
- **Medible:** auditoría de cada decisión, bandeja de revisión humana, métricas de calidad frente a etiquetas y calibración de umbrales.

Nació como prototipo para el reto 30X de la hackathon. Ese caso se conserva como perfil de ejemplo en `profiles/30x/` y en [docs/caso-30x/](docs/caso-30x/PLAYBOOK.md).

## Documentación

- [Adoptar JEV Guard en tu empresa](docs/PERFILES.md): perfiles, acciones propias e integración.
- [Arquitectura, reglas y API](docs/ARQUITECTURA.md)
- [Catálogo de preguntas del perfil demo](docs/PREGUNTAS.md)
- [Bitácora de desarrollo y resultados](docs/BITACORA.md)
- [Caso 30X: playbook de la hackathon](docs/caso-30x/PLAYBOOK.md)

## Ver la demo

Requiere Python 3.10 o superior. Funciona sin claves: sin `TYPESAFE_API_KEY` usa un simulador local de JEV, y la interfaz lo indica.

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows. En macOS o Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/demo.py            # abre http://127.0.0.1:8000 con el perfil demo (Nimbus)
```

Para ver otro perfil, define `JEV_GUARD_PROFILE=30x` antes de arrancar. En PowerShell: `$env:JEV_GUARD_PROFILE="30x"`.

La interfaz tiene cuatro pantallas:

- **En vivo:** los agentes simulados trabajando, con decisiones en tiempo real, latencia y costo frente a un LLM juez.
- **Laboratorio:** se edita una acción, incluidas las acciones propias del perfil, y se ve cómo decide el guardián.
- **Bandeja:** las acciones retenidas, para aprobarlas o rechazarlas.
- **Métricas:** calidad frente a etiquetas, rutas de decisión, latencia y costo.

Es HTML y JavaScript sin compilación, servido por la misma API. No necesita Node.

## Integrar a tus agentes

Cada agente llama al guardián antes de actuar y obedece el veredicto: `allow`, `block` o `hold`.

```bash
curl -X POST http://127.0.0.1:8000/v1/guard/check -H "Content-Type: application/json" -d '{
  "agent_id": "agente-seguimiento", "action_type": "email.send",
  "task": "Haz seguimiento a Andrea, que pidio una demo",
  "to": ["andrea@cliente-demo.example"], "subject": "Tu demo de Nimbus",
  "body": "Hola Andrea, agendamos la demo esta semana?", "purpose": "follow_up"}'
```

El cuerpo debe ir en UTF-8. En Windows, `curl` puede enviar los acentos con otra codificación; desde código, cualquier cliente HTTP lo hace bien.

O con el decorador de Python:

```python
from guard.sdk import GuardClient, guarded, ActionBlocked, ActionHeld

guard = GuardClient("http://127.0.0.1:8000")

@guarded(guard, "email.send", agent_id="agente-seguimiento")
def send_email(*, task, to, subject, body, purpose):
    ...  # solo se ejecuta si JEV Guard lo permite
```

Más ejemplos, incluidos n8n, Make y las acciones propias, en [docs/PERFILES.md](docs/PERFILES.md).

## Desplegar en Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/AlexBzal/jev-guard)

El archivo `render.yaml` crea un servicio web en el plan gratis, con el perfil `demo` y el modo demo activados. Cosas a tener en cuenta:

- **El servicio se duerme** tras 15 minutos sin visitas y tarda cerca de un minuto en despertar.
- **El disco no persiste:** el registro de decisiones se reinicia cada vez que el servicio se reinicia o despierta.
- **Los controles de la demo son públicos:** cualquiera con el enlace puede arrancar los agentes simulados o reiniciar el registro. Los agentes se apagan solos a los 10 minutos.
- **Variables opcionales:** con `TYPESAFE_API_KEY` se usa JEV real. Con `JEV_GUARD_API_KEY`, los agentes deben autenticarse. Con `JEV_GUARD_PROFILE` eliges el perfil.

## Desarrollo

```bash
pytest                                          # pruebas
python scripts/eval.py --profile demo           # evalúa los casos etiquetados de un perfil
python scripts/eval.py --profile 30x --scenarios profiles/30x/scenarios_holdout.yaml
python scripts/calibrate.py --profile demo      # sugiere umbrales a partir de las etiquetas
python scripts/bench.py                         # rendimiento y costo
python scripts/export_questions.py --profile demo
```

```
config/defaults.yaml      valores del motor, comunes a todas las empresas
profiles/<empresa>/       perfil: policy.yaml, context.yaml, scenarios*.yaml
guard/                    el motor (ver docs/ARQUITECTURA.md)
ui/                       interfaz web (HTML, CSS y JS sin compilación)
scripts/                  demo, evaluación, calibración, benchmark, simulación de agentes
tests/                    pruebas automatizadas
```

## Datos

Todos los datos de los perfiles incluidos son ficticios: personas inventadas y dominios `.example`. No hay datos personales reales.
