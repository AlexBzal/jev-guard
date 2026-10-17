"""Mide el costo propio del guardián (reglas + política + auditoría), sin red.

    python scripts/bench.py --n 5000

Con el simulador, la latencia medida es la sobrecarga del guardián. En producción
se suma la latencia de JEV (70-500 ms según TypeSafe), que domina el total.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard.jev import SimulatedJev  # noqa: E402
from guard.service import GuardService  # noqa: E402
from guard.store import DecisionStore  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000)
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    scenarios = yaml.safe_load((ROOT / "data" / "scenarios.yaml").read_text(encoding="utf-8"))
    svc = GuardService(backend=SimulatedJev(sleep=False), store=DecisionStore(), second_opinion=False)
    lat = []
    t0 = time.perf_counter()
    for i in range(args.n):
        d = svc.check(dict(scenarios[i % len(scenarios)]["action"]))
        lat.append(d.latency_ms)
    total = time.perf_counter() - t0
    lat.sort()
    m = svc.metrics()
    print(f"{args.n} decisiones en {total:.2f} s  ->  {args.n / total:,.0f} decisiones/s en un solo proceso")
    print(f"Sobrecarga del guardián: p50 {statistics.median(lat):.2f} ms, p95 {lat[int(0.95 * len(lat))]:.2f} ms")
    print(f"Llamadas a JEV evitadas por reglas: {m['resolved_by_rules_rate']:.0%}")
    print(f"Tokens de entrada promedio por llamada a JEV: {m['input_tokens'] / max(m['jev_calls'], 1):,.0f}")
    print(f"Costo JEV por 1.000 decisiones: {m['cost_per_1000_usd']} USD "
          f"(LLM como juez: {m['llm_judge_cost_per_1000_usd']} USD, {m['savings_factor']}x más)")
    per_day = 10_000
    print(f"A {per_day:,} acciones al día: JEV ~{m['cost_per_1000_usd'] * per_day / 1000:.2f} USD/día, "
          f"LLM juez ~{m['llm_judge_cost_per_1000_usd'] * per_day / 1000:.0f} USD/día")


if __name__ == "__main__":
    main()
