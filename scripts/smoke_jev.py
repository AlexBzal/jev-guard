"""Prueba de humo contra la API real de TypeSafe.

    set TYPESAFE_API_KEY=...        (PowerShell: $env:TYPESAFE_API_KEY="...")
    python scripts/smoke_jev.py

Envía un correo de ejemplo con las preguntas reales del guardián y muestra las
respuestas crudas de JEV, la latencia y el costo. Úsalo para validar que las
instrucciones en español funcionan como se espera antes de una demo.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard.config import default_context, default_policy  # noqa: E402
from guard.facts import FactEngine  # noqa: E402
from guard.jev import TypeSafeJev  # noqa: E402
from guard.models import parse_action  # noqa: E402
from guard.questions import questions_payload, signals_for  # noqa: E402
from guard.service import action_view  # noqa: E402

SAMPLE = {
    "agent_id": "agente-seguimiento",
    "action_type": "email.send",
    "task": "Haz seguimiento a Valentina, interesada en el programa ejecutivo de IA",
    "to": ["valentina.cruz@banca-demo.example"],
    "subject": "Una propuesta especial para ti",
    "body": "Hola Valentina, para que te animes te damos 40% de descuento y una beca garantizada. Saludos.",
    "purpose": "follow_up",
}


def main() -> int:
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        print("Falta TYPESAFE_API_KEY.")
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    policy, ctx = default_policy(), default_context()
    action = parse_action(SAMPLE)
    facts = FactEngine(policy, ctx).analyze(action)
    signals = signals_for(action.action_type, facts.values)
    state = {"task": action.task, "action": action_view(action), "facts": facts.values, "context": ctx.for_jev()}
    result = TypeSafeJev(api_key=key, model=policy.jev.model, timeout_s=10).evaluate(state, questions_payload(signals))
    print(f"Modelo: {result.model}  latencia: {result.latency_ms:.0f} ms  tokens: {result.input_tokens}  "
          f"costo: {result.input_tokens * policy.jev.price_per_million_input / 1e6:.7f} USD")
    for qid, ans in result.answers.items():
        print(qid, json.dumps(ans.model_dump(exclude_none=True), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
