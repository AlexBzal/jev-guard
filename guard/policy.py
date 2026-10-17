"""Motor de decisión: reglas + señales de JEV + umbrales por tier = veredicto.

Orden de evaluación:
1. Regla determinista BLOCK                     -> BLOCK (no se llama a JEV).
2. Señal crítica (inyección, fuga) muy probable -> BLOCK.
2b. Señal de peso alto con riesgo >= umbral de bloqueo y certeza suficiente -> BLOCK.
3. Riesgo compuesto >= umbral de bloqueo:
     con certeza suficiente                     -> BLOCK
     sin certeza                                -> escalar (LLM o persona, según el tier)
4. Regla determinista REVIEW                    -> persona.
5. Riesgo compuesto >= umbral de revisión       -> escalar (LLM o persona, según el tier).
6. Alguna señal importante dudosa               -> escalar (LLM o persona, según el tier).
7. En otro caso                                 -> ALLOW.

Riesgo compuesto: "OR ruidoso" sobre las señales, descontando un piso de ruido:
    r_i' = max(0, (r_i - piso) / (1 - piso))
    riesgo = 1 - prod(1 - peso_i * r_i')
Así, una señal fuerte basta para frenar, y muchas señales débiles no se suman en
una falsa alarma.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .config import Policy
from .models import Facts, JevResult, Reason, SignalReading, Tier
from .questions import Signal


class Intent(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    HUMAN = "human"
    LLM = "llm"


@dataclass
class PolicyOutcome:
    intent: Intent
    risk: float
    reasons: list[Reason] = field(default_factory=list)
    decided_by: str = "jev"  # rules | jev


def rule_reasons(facts: Facts) -> list[Reason]:
    return [Reason(source="rule", code=h.code, message=h.message, severity=h.severity) for h in facts.hits]


def read_signals(signals: list[Signal], result: JevResult, facts_values: dict) -> list[SignalReading]:
    readings = []
    for s in signals:
        ans = result.answers[s.qid]
        risk, certainty = s.risk_fn(ans, facts_values)
        readings.append(SignalReading(qid=s.qid, label=s.label, risk=round(risk, 4), certainty=round(certainty, 4),
                                      weight=s.weight, critical=s.critical, raw=ans))
    return readings


class PolicyEngine:
    def __init__(self, policy: Policy):
        self.p = policy

    def adjusted(self, risk: float) -> float:
        floor = self.p.risk_floor
        return max(0.0, (risk - floor) / (1 - floor))

    def composite(self, readings: list[SignalReading]) -> float:
        keep = 1.0
        for r in readings:
            keep *= 1 - r.weight * self.adjusted(r.risk)
        return round(1 - keep, 4)

    def _escalation(self, tier: Tier) -> Intent:
        return Intent.LLM if self.p.tiers[tier].on_uncertain == "llm" else Intent.HUMAN

    @staticmethod
    def _rule_reasons(facts: Facts) -> list[Reason]:
        return rule_reasons(facts)

    def rules_only(self, facts: Facts) -> PolicyOutcome | None:
        """Decisión sin JEV cuando una regla ya frena la acción."""
        if facts.blocking:
            return PolicyOutcome(Intent.BLOCK, 1.0, self._rule_reasons(facts), decided_by="rules")
        return None

    def decide(self, facts: Facts, readings: list[SignalReading]) -> PolicyOutcome:
        tp = self.p.tiers[facts.tier]
        reasons = self._rule_reasons(facts)
        risk = self.composite(readings)

        flagged = sorted((r for r in readings if self.adjusted(r.risk) * r.weight >= 0.25),
                         key=lambda r: r.weight * r.risk, reverse=True)
        for r in flagged:
            reasons.append(Reason(source="jev", code=r.qid, message=r.label, risk=r.risk, certainty=r.certainty))

        lo, hi = self.p.uncertain_band
        uncertain = [r for r in readings
                     if r.weight >= self.p.uncertain_min_weight and lo <= r.risk <= hi and r.certainty < tp.min_certainty]

        # 2. Señales críticas
        critical = [r for r in readings if r.critical and r.risk >= self.p.critical_block]
        if critical:
            return PolicyOutcome(Intent.BLOCK, max(risk, max(r.risk for r in critical)), reasons)

        # 3a. Una señal fuerte, segura y de peso alto basta para frenar. Sin esto, una señal con
        #     peso menor que el umbral nunca podría frenar sola, por clara que fuera.
        strong = [r for r in readings if r.weight >= self.p.strong_signal_weight
                  and r.risk >= tp.block and r.certainty >= tp.min_certainty]
        if strong:
            return PolicyOutcome(Intent.BLOCK, max(risk, max(r.risk for r in strong)), reasons)

        # 3b. Riesgo compuesto alto
        if risk >= tp.block:
            top = max(readings, key=lambda r: r.weight * self.adjusted(r.risk))
            if top.certainty >= tp.min_certainty:
                return PolicyOutcome(Intent.BLOCK, risk, reasons)
            reasons.append(Reason(source="system", code="uncertain_block",
                                  message=f"Riesgo alto, pero JEV no está seguro de: {top.label.lower()}."))
            return PolicyOutcome(self._escalation(facts.tier), risk, reasons)

        # 4. Reglas que exigen una persona
        if facts.needs_review:
            return PolicyOutcome(Intent.HUMAN, risk, reasons)

        # 5. Riesgo moderado
        if risk >= tp.review:
            reasons.append(Reason(source="system", code="moderate_risk",
                                  message=f"Riesgo moderado ({risk:.2f}): entre retener ({tp.review:.2f}) y frenar ({tp.block:.2f})."))
            return PolicyOutcome(self._escalation(facts.tier), risk, reasons)

        # 6. Dudas
        if uncertain:
            for r in uncertain:
                reasons.append(Reason(source="system", code=f"uncertain:{r.qid}",
                                      message=f"JEV no está seguro: {r.label.lower()}.", risk=r.risk, certainty=r.certainty))
            return PolicyOutcome(self._escalation(facts.tier), risk, reasons)

        return PolicyOutcome(Intent.ALLOW, risk, reasons)
