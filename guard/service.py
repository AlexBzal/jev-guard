"""Orquestación de una verificación completa.

    acción del agente
        -> reglas deterministas (facts)         ~0,1 ms, gratis
        -> JEV: todas las preguntas en 1 llamada  70-500 ms, fracciones de centavo
        -> motor de política (umbrales por tier)
        -> [solo si hay duda] LLM segunda opinión
        -> [solo si hace falta] persona
        -> registro de auditoría
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

from .config import BusinessContext, Policy, default_context, default_policy
from .facts import FactEngine
from .jev import JevBackend, JevError, estimate_tokens, make_backend
from .llm import SecondOpinion, llm_available
from .metrics import compute_metrics
from .models import (
    Decision,
    Facts,
    Reason,
    Route,
    RuleHit,
    Severity,
    SignalReading,
    Verdict,
    parse_action,
)
from .events import EventBus
from .policy import Intent, PolicyEngine, PolicyOutcome, read_signals, rule_reasons
from .questions import questions_payload, signals_for
from .store import DecisionStore

log = logging.getLogger(__name__)


def _fixed_now() -> datetime | None:
    """JEV_GUARD_NOW fija el reloj (ISO 8601) para demos reproducibles."""
    value = os.environ.get("JEV_GUARD_NOW")
    return datetime.fromisoformat(value) if value else None


def action_view(action) -> dict[str, Any]:
    """Lo que JEV ve de la acción: el contenido, sin identificadores internos."""
    return action.model_dump(mode="json", exclude={"action_id", "agent_id", "task", "requested_at"})


def _short(text: str, n: int = 90) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def describe(action) -> str:
    """Una línea que una persona entiende sin abrir el JSON."""
    t = action.action_type
    if t == "email.send":
        who = "1 persona" if len(action.to) == 1 else f"{_int(len(action.to))} personas"
        return f"Correo a {who}: «{_short(action.subject, 70)}»"
    if t == "email.bulk":
        n = action.recipient_count if action.recipient_count is not None else len(action.recipients)
        return f"Campaña a {_int(n)} personas: «{_short(action.subject, 60)}»"
    if t in ("crm.update", "crm.delete"):
        n = action.record_count if action.record_count is not None else len(action.record_ids)
        singular, plural = {"contact": ("contacto", "contactos"), "deal": ("negocio", "negocios"),
                            "company": ("empresa", "empresas")}[action.object.value]
        what = f"{_int(n)} {singular if n == 1 else plural}"
        if t == "crm.update":
            return f"Cambia {', '.join(action.changes)} en {what}"
        return f"Borra {what}"
    names = {"linkedin": "LinkedIn", "x": "X", "instagram": "Instagram", "youtube": "YouTube", "blog": "el blog"}
    return f"Publicación en {names[action.platform.value]}: «{_short(action.title or action.text, 70)}»"


class GuardService:
    def __init__(self, policy: Policy | None = None, context: BusinessContext | None = None,
                 backend: JevBackend | None = None, store: DecisionStore | None = None,
                 second_opinion: SecondOpinion | None | bool = None):
        self.policy = policy or default_policy()
        self.context = context or default_context()
        self.facts = FactEngine(self.policy, self.context)
        self.engine = PolicyEngine(self.policy)
        self.backend = backend or make_backend(self.policy.jev.model, self.policy.jev.timeout_s)
        self.store = store or DecisionStore()
        if second_opinion is None:
            second_opinion = SecondOpinion(self.policy.llm) if llm_available(self.policy.llm) else False
        self.llm: SecondOpinion | None = second_opinion or None
        self.events = EventBus()

    # -- API pública ---------------------------------------------------------

    def check(self, raw_action: dict[str, Any] | Any, now: datetime | None = None, *, persist: bool = True,
              source: str | None = None) -> Decision:
        """Evalúa una acción.

        persist=False es el modo de prueba del Laboratorio: decide igual, pero no se guarda,
        no se publica en el flujo en vivo y no cuenta en las métricas.
        """
        t0 = time.perf_counter()
        now = now or _fixed_now()
        action = parse_action(raw_action) if isinstance(raw_action, dict) else raw_action
        facts = self.facts.analyze(action, now=now)

        jev_result = None
        readings: list[SignalReading] = []
        outcome = self.engine.rules_only(facts)

        if outcome is None:
            signals = signals_for(action.action_type, facts.values)
            state = {"task": action.task, "action": action_view(action), "facts": facts.values,
                     "context": self.context.for_jev()}
            questions = questions_payload(signals)
            if estimate_tokens(state, questions) > self.policy.jev.max_context_tokens:
                facts.hits.append(RuleHit(code="G004", severity=Severity.REVIEW,
                                          message="La acción es demasiado grande para evaluarla automáticamente."))
                outcome = PolicyOutcome(Intent.HUMAN, 0.5, rule_reasons(facts), decided_by="rules")
            else:
                try:
                    jev_result = self.backend.evaluate(state, questions)
                    readings = read_signals(signals, jev_result, facts.values)
                    outcome = self.engine.decide(facts, readings)
                except JevError as exc:
                    log.warning("JEV falló: %s", exc)
                    outcome = self._on_jev_error(facts, str(exc))

        decision = self._finalize(action, facts, outcome, readings, jev_result)
        decision.latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        decision.summary = describe(action)
        decision.sandbox = not persist
        if persist:
            self.store.save(decision, action.model_dump(mode="json"))
            self.events.publish({"type": "decision", "source": source,
                                 "decision": decision.model_dump(mode="json")})
        return decision

    def metrics(self) -> dict[str, Any]:
        return compute_metrics(self.store.all_rows(), self.policy)

    @property
    def mode(self) -> dict[str, Any]:
        return {"jev": "simulated" if self.backend.simulated else "typesafe",
                "llm": self.policy.llm.model if self.llm else None}

    # -- internos ------------------------------------------------------------

    def _on_jev_error(self, facts: Facts, error: str) -> PolicyOutcome:
        mode = self.policy.tiers[facts.tier].on_jev_error
        reasons = rule_reasons(facts)
        reasons.append(Reason(source="system", code="jev_error",
                              message=f"JEV no estuvo disponible ({error}). Política del tier: {mode}."))
        if mode == "allow" and not facts.needs_review:
            return PolicyOutcome(Intent.ALLOW, 0.0, reasons, decided_by="rules")
        return PolicyOutcome(Intent.HUMAN, 0.5, reasons, decided_by="rules")

    def _finalize(self, action, facts: Facts, outcome: PolicyOutcome, readings: list[SignalReading],
                  jev_result) -> Decision:
        jev_cost = (jev_result.input_tokens * self.policy.jev.price_per_million_input / 1e6) if jev_result else 0.0
        base = dict(
            action_id=action.action_id, agent_id=action.agent_id, action_type=action.action_type, tier=facts.tier,
            risk=round(outcome.risk, 4), reasons=outcome.reasons, signals=readings,
            facts={**facts.values, "blast_radius": facts.blast_radius, "reversible": facts.reversible},
            jev_latency_ms=round(jev_result.latency_ms, 2) if jev_result else None,
            jev_model=jev_result.model if jev_result else None,
            jev_simulated=jev_result.simulated if jev_result else None,
            input_tokens=jev_result.input_tokens if jev_result else 0,
            cost_usd=jev_cost,
        )
        route_for = Route.RULES if outcome.decided_by == "rules" else Route.JEV

        if outcome.intent == Intent.ALLOW:
            return Decision(verdict=Verdict.ALLOW, route=route_for, **base)
        if outcome.intent == Intent.BLOCK:
            return Decision(verdict=Verdict.BLOCK, route=route_for, **base)
        if outcome.intent == Intent.LLM:
            return self._second_opinion(action, facts, readings, base)
        return Decision(verdict=Verdict.HOLD, route=Route.HUMAN, status="pending_review", **base)

    def _second_opinion(self, action, facts: Facts, readings: list[SignalReading], base: dict) -> Decision:
        if self.llm is None:
            base["reasons"] = base["reasons"] + [Reason(
                source="system", code="llm_unavailable",
                message="Hace falta una segunda opinión y no hay LLM configurado: pasa a una persona.")]
            return Decision(verdict=Verdict.HOLD, route=Route.HUMAN, status="pending_review", **base)
        payload = {
            "task": action.task, "action_type": action.action_type, "action": action_view(action),
            "facts": base["facts"], "rules": [h.model_dump(mode="json") for h in facts.hits],
            "classifier_signals": [{"signal": r.label, "risk": r.risk, "certainty": r.certainty} for r in readings],
            "context": self.context.for_jev(),
        }
        opinion = self.llm.review(payload)
        if opinion is None:
            base["reasons"] = base["reasons"] + [Reason(source="system", code="llm_failed",
                                                        message="La segunda opinión no estuvo disponible: pasa a una persona.")]
            return Decision(verdict=Verdict.HOLD, route=Route.HUMAN, status="pending_review", llm_used=True, **base)
        base["cost_usd"] = base["cost_usd"] + opinion.cost_usd
        base["reasons"] = base["reasons"] + [Reason(source="llm", code=f"llm:{opinion.verdict}", message=opinion.reason)]
        if opinion.verdict == "allow":
            return Decision(verdict=Verdict.ALLOW, route=Route.LLM, llm_used=True, **base)
        if opinion.verdict == "block":
            return Decision(verdict=Verdict.BLOCK, route=Route.LLM, llm_used=True, **base)
        return Decision(verdict=Verdict.HOLD, route=Route.HUMAN, status="pending_review", llm_used=True, **base)
