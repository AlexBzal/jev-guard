"""Segunda opinión con un LLM (Claude) para los casos en que JEV duda.

Es el "System Two" del diseño: lento y caro comparado con JEV, por eso solo se usa
en la fracción de acciones que JEV no puede resolver con confianza y cuyo impacto
es bajo o medio. Si el LLM no está configurado, falla o se niega, el caso pasa a
una persona: nunca se aprueba por omisión.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

from .config import LlmConfig

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres el revisor de seguridad de las acciones que proponen los agentes internos de 30X \
(correos, cambios en el CRM, publicaciones). Un clasificador rápido ya analizó la acción y no tuvo \
certeza suficiente. Decide con criterio:
- "allow" si la acción es segura y cumple la tarea del agente;
- "block" si causaría daño claro (a personas, a la marca, a los datos o por incumplir la política);
- "human" si la decisión depende de información que no tienes o es genuinamente ambigua.
Ante la duda razonable, prefiere "human" a "allow". Responde en español con una razón breve y concreta \
(máximo dos frases) que ayude a quien revise."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["allow", "block", "human"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}


@dataclass
class LlmOpinion:
    verdict: Literal["allow", "block", "human"]
    reason: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str


def llm_available(cfg: LlmConfig) -> bool:
    if not cfg.enabled or os.environ.get("JEV_GUARD_LLM") == "0":
        return False
    has_creds = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return has_creds or os.environ.get("JEV_GUARD_LLM") == "1"


class SecondOpinion:
    def __init__(self, cfg: LlmConfig):
        import anthropic  # importación diferida: el resto del sistema no depende del SDK

        self.cfg = cfg
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(timeout=cfg.timeout_s, max_retries=1)

    def review(self, payload: dict[str, Any]) -> LlmOpinion | None:
        content = "Acción propuesta y análisis previo (JSON):\n" + json.dumps(payload, ensure_ascii=False, default=str)
        try:
            response = self.client.beta.messages.create(
                model=self.cfg.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_config={"effort": self.cfg.effort, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except self._anthropic.APIStatusError as exc:
            log.warning("El LLM respondió %s: %s", exc.status_code, exc.message)
            return None
        except self._anthropic.APIConnectionError as exc:
            log.warning("No se pudo conectar con el LLM: %s", exc)
            return None

        if response.stop_reason == "refusal":
            log.warning("El LLM se negó a evaluar la acción; pasa a una persona")
            return None
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("El LLM devolvió JSON inválido")
            return None
        usage = response.usage
        cost = (usage.input_tokens * self.cfg.price_per_million_input
                + usage.output_tokens * self.cfg.price_per_million_output) / 1_000_000
        return LlmOpinion(verdict=data["verdict"], reason=data["reason"], input_tokens=usage.input_tokens,
                          output_tokens=usage.output_tokens, cost_usd=cost, model=response.model)
