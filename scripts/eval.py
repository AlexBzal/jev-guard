"""Evalúa el guardián contra los casos etiquetados de un perfil.

    python scripts/eval.py                          # perfil activo (JEV_GUARD_PROFILE, por defecto demo)
    python scripts/eval.py --profile 30x            # otro perfil
    python scripts/eval.py --profile 30x --scenarios profiles/30x/scenarios_holdout.yaml
    python scripts/eval.py --simulate               # fuerza el simulador aunque haya TYPESAFE_API_KEY
    python scripts/eval.py --json out.json

Sale con código 1 si alguna acción insegura se dejó pasar sola (false_allow > 0).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard.config import profile_dir  # noqa: E402
from guard.jev import SimulatedJev  # noqa: E402
from guard.service import GuardService  # noqa: E402
from guard.store import DecisionStore  # noqa: E402

EVAL_NOW = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)  # 10:00 en Bogotá


def load_scenarios(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run(scenarios: list[dict], service: GuardService) -> list[dict]:
    results = []
    for sc in scenarios:
        d = service.check(dict(sc["action"]), now=EVAL_NOW)
        service.store.label(d.decision_id, sc["safe"], reviewer="dataset", note=sc["id"], source="dataset")
        ok = d.verdict.value in sc["expected"]
        results.append({
            "id": sc["id"], "title": sc["title"], "safe": sc["safe"], "expected": sc["expected"],
            "verdict": d.verdict.value, "route": d.route.value, "tier": d.tier.value, "risk": d.risk,
            "ok": ok, "false_allow": (not sc["safe"]) and d.verdict.value == "allow",
            "false_block": sc["safe"] and d.verdict.value == "block",
            "latency_ms": d.latency_ms, "reasons": [r.message for r in d.reasons[:3]],
        })
    return results


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", help="Perfil de empresa (carpeta en profiles/)")
    ap.add_argument("--scenarios", help="Archivo de casos; por defecto profiles/<perfil>/scenarios.yaml")
    ap.add_argument("--simulate", action="store_true")
    ap.add_argument("--json", help="Guarda resultados y métricas en este archivo")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if args.profile:
        os.environ["JEV_GUARD_PROFILE"] = args.profile
    scenarios_path = Path(args.scenarios) if args.scenarios else profile_dir() / "scenarios.yaml"
    backend = SimulatedJev() if args.simulate else None
    service = GuardService(backend=backend, store=DecisionStore(), second_opinion=None)
    results = run(load_scenarios(scenarios_path), service)
    metrics = service.metrics()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    mode = service.mode
    print(f"Perfil: {mode['profile']} ({mode['company']})   casos: {scenarios_path.name}")
    print(f"JEV: {mode['jev']}   LLM: {mode['llm'] or 'no configurado (las dudas van a personas)'}")
    print(f"{'caso':28} {'seguro':6} {'esperado':12} {'veredicto':9} {'ruta':6} {'tier':8} {'riesgo':>6}")
    for r in results:
        mark = "OK " if r["ok"] else ("!! " if r["false_allow"] else "x  ")
        print(f"{mark}{r['id']:25} {str(r['safe']):6} {'/'.join(r['expected']):12} {r['verdict']:9} "
              f"{r['route']:6} {r['tier']:8} {r['risk']:6.2f}")
        if not args.quiet and not r["ok"]:
            for msg in r["reasons"]:
                print(f"      - {msg}")

    q = metrics["quality"]
    hits = sum(r["ok"] for r in results)
    print()
    print(f"Coincidencia con lo esperado: {hits}/{len(results)}")
    print(f"Inseguras detenidas (block u hold): {q['unsafe_caught']:.0%} de {q['unsafe']}")
    print(f"Inseguras que pasaron solas: {q['false_allow']}")
    print(f"Seguras bloqueadas por error: {q['false_block_rate']:.0%}")
    print(f"Resueltas sin persona: {metrics['automation_rate']:.0%}   (por reglas: {metrics['resolved_by_rules_rate']:.0%})")
    print(f"Latencia del guardián p50/p95: {metrics['latency_ms']['p50']} / {metrics['latency_ms']['p95']} ms")
    print(f"Costo por 1.000 decisiones: JEV {metrics['cost_per_1000_usd']} USD vs. LLM juez {metrics['llm_judge_cost_per_1000_usd']} USD")
    if mode["jev"] == "simulated":
        print("Nota: JEV simulado. La latencia no incluye red y la calidad mide las heurísticas, no a JEV.")

    if args.json:
        Path(args.json).write_text(json.dumps({"mode": mode, "results": results, "metrics": metrics},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if q["false_allow"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
