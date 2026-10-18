# JEV Guard

Guardián en tiempo real para los agentes internos de 30X. Antes de que un agente envíe un correo, lance una campaña, modifique el CRM o publique contenido, **JEV** (TypeSafe AI) decide en milisegundos y por fracciones de centavo si la acción es segura. Lo dudoso pasa a un LLM; lo crítico, a una persona.

> Reto 30X: "¿Qué decisiones de 30X podría tomar JEV miles de veces al día, en milisegundos y por fracciones de centavo?"

- **Playbook (entregable):** [docs/PLAYBOOK.md](docs/PLAYBOOK.md)
- **Catálogo de preguntas a JEV:** [docs/PREGUNTAS.md](docs/PREGUNTAS.md)
- **Arquitectura y reglas:** [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md)
- **Bitácora de desarrollo y resultados:** [docs/BITACORA.md](docs/BITACORA.md)

## Ver la demo

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows. En macOS o Linux: source .venv/bin/activate
pip install -r requirements.txt
python scripts/demo.py            # abre http://127.0.0.1:8000
```

La interfaz tiene cuatro pantallas:

- **En vivo:** los agentes simulados trabajando, con decisiones en tiempo real, latencia y costo frente a un LLM juez.
- **Laboratorio:** se edita una acción y se ve cómo decide el guardián: reglas, preguntas a JEV, umbrales y veredicto. Los botones de "¿Qué pasa si…?" muestran cómo cambia la decisión.
- **Bandeja:** las acciones retenidas, para aprobarlas o rechazarlas.
- **Métricas:** calidad frente a etiquetas, rutas de decisión, latencia y costo.

Es HTML y JavaScript sin compilación, servido por la misma API. No necesita Node.

## Desplegar en Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/AlexBzal/jev-guard)

El archivo `render.yaml` crea un servicio web en el plan gratis, con el modo demo activado. Cosas a tener en cuenta:

- **El servicio se duerme** tras 15 minutos sin visitas y tarda cerca de un minuto en despertar. Abre el enlace un par de minutos antes de presentar.
- **El disco no persiste:** el registro de decisiones se reinicia cada vez que el servicio se reinicia o despierta.
- **Los controles de la demo son públicos:** cualquiera con el enlace puede arrancar los agentes simulados o reiniciar el registro. Los agentes se apagan solos a los 10 minutos.
- **JEV real es opcional:** si completas `TYPESAFE_API_KEY` en Render, se usa JEV real en vez del simulador.

## Arranque rápido

Requiere Python 3.10 o superior. Funciona sin claves: sin `TYPESAFE_API_KEY` usa un simulador local de JEV, y cada decisión lo indica.

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows. En macOS o Linux: source .venv/bin/activate
pip install -r requirements.txt

pytest                            # 56 pruebas
python scripts/eval.py            # evalúa los 49 casos etiquetados
python scripts/eval.py --scenarios data/scenarios_holdout.yaml   # 30 casos independientes
python scripts/bench.py           # rendimiento y costo
```

Levantar la API y simular a los agentes trabajando:

```bash
uvicorn guard.api:app --port 8000                     # docs interactivas en http://127.0.0.1:8000/docs
python scripts/simulate_agents.py --rate 5 --count 200 --auto-review
```

Con JEV real y segunda opinión de Claude:

```bash
export TYPESAFE_API_KEY=...       # PowerShell: $env:TYPESAFE_API_KEY="..."
export ANTHROPIC_API_KEY=...      # opcional
python scripts/smoke_jev.py       # una llamada real con las preguntas del guardián
python scripts/eval.py
```

## Integrar un agente

```python
from guard.sdk import GuardClient, guarded, ActionBlocked, ActionHeld

guard = GuardClient("http://127.0.0.1:8000")

@guarded(guard, "email.send", agent_id="agente-seguimiento")
def send_email(*, task, to, subject, body, purpose):
    ...  # el envío real; solo se ejecuta si JEV Guard lo permite

try:
    send_email(task="Haz seguimiento a Andrea…", to=["andrea@fintech-demo.example"],
               subject="Gracias por venir", body="Hola Andrea…", purpose="follow_up")
except ActionBlocked as e:
    print("Frenado:", e)                 # las razones vienen en e.decision.reasons
except ActionHeld as e:
    print("Esperando revisión:", e.decision.decision_id)
```

Desde cualquier otra herramienta basta un `POST /v1/guard/check` con la acción en JSON.

## Estructura

```
config/policy.yaml        umbrales por tier, límites, permisos por agente
data/context.yaml         marca, catálogo, listas de baja (todo simulado)
data/scenarios*.yaml      casos etiquetados para evaluación
guard/                    el sistema (ver docs/ARQUITECTURA.md)
scripts/                  evaluación, calibración, benchmark, simulación de agentes
tests/                    pruebas automatizadas
ui/                       interfaz web (HTML, CSS y JS sin compilación)
```

## Datos

Todos los datos son ficticios: personas inventadas y dominios `.example`. No hay datos personales reales. El catálogo de oferta y la línea editorial de `data/context.yaml` son ejemplos y deben reemplazarse por los reales de 30X.
