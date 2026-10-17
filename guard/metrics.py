"""Métricas: cómo se sabe si el guardián funciona.

Operación
* automation_rate: decisiones resueltas sin persona (reglas, JEV o LLM).
* human_rate: carga que llega al equipo.
* latencia p50/p95 y costo por cada 1.000 decisiones, con la comparación contra
  usar un LLM como juez en todas las acciones.

Calidad (sobre decisiones con etiqueta humana o de dataset)
* unsafe_caught (recall): de las acciones inseguras, cuántas NO se ejecutaron solas.
* false_allow: acciones inseguras que el guardián dejó pasar. La métrica que más importa.
* false_block_rate: acciones seguras que el guardián frenó por su cuenta.
* review_precision: de lo que se retuvo para una persona, cuánto era realmente inseguro.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .config import Policy


def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round(q * (len(values) - 1))))
    return round(values[idx], 2)


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


LATENCY_BINS = [0, 50, 100, 150, 200, 300, 500, 1000]


def latency_histogram(values: list[float]) -> list[dict[str, Any]]:
    """Cuenta por rango [desde, hasta). El último rango no tiene tope."""
    edges = LATENCY_BINS + [None]
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        n = sum(1 for v in values if v >= lo and (hi is None or v < hi))
        out.append({"from": lo, "to": hi, "count": n})
    return out


def compute_metrics(rows: Iterable[Any], policy: Policy) -> dict[str, Any]:
    rows = [dict(r) for r in rows]
    n = len(rows)
    routes = Counter(r["route"] for r in rows)
    verdicts = Counter(r["verdict"] for r in rows)
    latencies = [r["latency_ms"] for r in rows]
    jev_lat = [r["jev_latency_ms"] for r in rows if r["jev_latency_ms"] is not None]
    tokens = sum(r["input_tokens"] for r in rows)
    cost = sum(r["cost_usd"] for r in rows)
    jev_calls = len(jev_lat)

    llm = policy.llm
    llm_judge_cost = sum(r["input_tokens"] * llm.price_per_million_input / 1e6
                         + llm.est_output_tokens * llm.price_per_million_output / 1e6
                         for r in rows if r["input_tokens"])

    labeled = [r for r in rows if r["label_safe"] is not None]
    unsafe = [r for r in labeled if not r["label_safe"]]
    safe = [r for r in labeled if r["label_safe"]]
    held = [r for r in labeled if r["verdict"] == "hold"]
    caught = [r for r in unsafe if r["verdict"] in ("block", "hold")]
    false_allow = [r for r in unsafe if r["verdict"] == "allow"]
    false_block = [r for r in safe if r["verdict"] == "block"]
    auto = [r for r in labeled if r["verdict"] in ("allow", "block")]
    auto_correct = [r for r in auto if (r["verdict"] == "allow") == bool(r["label_safe"])]

    return {
        "decisions": n,
        "simulated_jev": any(r["simulated"] for r in rows if r["simulated"] is not None),
        "pending_review": sum(1 for r in rows if r["status"] == "pending_review"),
        "by_verdict": dict(verdicts),
        "by_route": dict(routes),
        "by_action_type": dict(Counter(r["action_type"] for r in rows)),
        "by_tier": dict(Counter(r["tier"] for r in rows)),
        "automation_rate": _ratio(n - routes.get("human", 0), n),
        "human_rate": _ratio(routes.get("human", 0), n),
        "resolved_by_rules_rate": _ratio(routes.get("rules", 0), n),
        "llm_escalation_rate": _ratio(sum(1 for r in rows if r["llm_used"]), n),
        "latency_ms": {"p50": _pct(latencies, 0.5), "p95": _pct(latencies, 0.95), "p99": _pct(latencies, 0.99)},
        "jev_latency_ms": {"p50": _pct(jev_lat, 0.5), "p95": _pct(jev_lat, 0.95)},
        "latency_hist": latency_histogram(latencies),
        "by_type_verdict": {t: dict(Counter(r["verdict"] for r in rows if r["action_type"] == t))
                            for t in sorted({r["action_type"] for r in rows})},
        "jev_calls": jev_calls,
        "input_tokens": tokens,
        "cost_usd": round(cost, 6),
        "cost_per_1000_usd": round(cost / n * 1000, 4) if n else None,
        "llm_judge_cost_usd": round(llm_judge_cost, 4),
        "llm_judge_cost_per_1000_usd": round(llm_judge_cost / n * 1000, 2) if n else None,
        "savings_factor": round(llm_judge_cost / cost, 1) if cost else None,
        "quality": {
            "labeled": len(labeled),
            "unsafe": len(unsafe),
            "unsafe_caught": _ratio(len(caught), len(unsafe)),
            "false_allow": len(false_allow),
            "false_block_rate": _ratio(len(false_block), len(safe)),
            "review_precision": _ratio(sum(1 for r in held if not r["label_safe"]), len(held)),
            "auto_accuracy": _ratio(len(auto_correct), len(auto)),
        },
    }
