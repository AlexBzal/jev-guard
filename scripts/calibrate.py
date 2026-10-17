"""Calibra los umbrales de cada tier con casos etiquetados.

    python scripts/calibrate.py                          # usa data/scenarios*.yaml
    python scripts/calibrate.py --files data/scenarios_holdout.yaml

Para cada tier prueba combinaciones de (review, block) y elige la que:
1. no deja pasar sola ninguna acción insegura (false_allow = 0), y
2. minimiza la carga humana sobre acciones seguras y los falsos bloqueos.

Las respuestas de JEV se calculan una sola vez por caso; solo se re-decide la política,
así que la calibración no gasta llamadas adicionales.
Con pocos casos por tier el resultado es orientativo: hay que recalibrar con las
etiquetas reales que dejan los revisores en las primeras semanas.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard.config import default_context, default_policy  # noqa: E402
from guard.facts import FactEngine  # noqa: E402
from guard.jev import make_backend  # noqa: E402
from guard.models import Tier, parse_action  # noqa: E402
from guard.policy import Intent, PolicyEngine, read_signals  # noqa: E402
from guard.questions import questions_payload, signals_for  # noqa: E402
from guard.service import action_view  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval import EVAL_NOW  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GRID = [round(x * 0.05, 2) for x in range(3, 20)]  # 0.15 .. 0.95


def prepare(scenarios, policy, ctx, backend):
    facts_engine = FactEngine(policy, ctx)
    rows = []
    for sc in scenarios:
        action = parse_action(dict(sc["action"]))
        facts = facts_engine.analyze(action, now=EVAL_NOW)
        if facts.blocking:
            continue  # lo resuelven las reglas; los umbrales no influyen
        signals = signals_for(action.action_type, facts.values)
        state = {"task": action.task, "action": action_view(action), "facts": facts.values, "context": ctx.for_jev()}
        readings = read_signals(signals, backend.evaluate(state, questions_payload(signals)), facts.values)
        rows.append((sc, facts, readings))
    return rows


def evaluate(rows, policy):
    engine = PolicyEngine(policy)
    fa = fb = safe_held = 0
    for sc, facts, readings in rows:
        intent = engine.decide(facts, readings).intent
        if intent == Intent.ALLOW and not sc["safe"]:
            fa += 1
        if intent == Intent.BLOCK and sc["safe"]:
            fb += 1
        if intent in (Intent.HUMAN, Intent.LLM) and sc["safe"]:
            safe_held += 1
    return fa, fb, safe_held


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", nargs="*", default=[str(p) for p in sorted((ROOT / "data").glob("scenarios*.yaml"))])
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    policy, ctx = default_policy(), default_context()
    backend = make_backend(policy.jev.model, policy.jev.timeout_s)
    scenarios = [sc for f in args.files for sc in yaml.safe_load(Path(f).read_text(encoding="utf-8"))]
    rows = prepare(scenarios, policy, ctx, backend)
    print(f"Casos que llegan a JEV: {len(rows)} de {len(scenarios)}  (JEV: {'simulado' if backend.simulated else 'TypeSafe'})\n")

    for tier in Tier:
        tier_rows = [r for r in rows if r[1].tier == tier]
        if not tier_rows:
            continue
        current = policy.tiers[tier]
        base = evaluate(tier_rows, policy)
        best = None
        for review in GRID:
            for block in GRID:
                if block <= review:
                    continue
                trial = policy.model_copy(deep=True)
                trial.tiers[tier].review, trial.tiers[tier].block = review, block
                fa, fb, held = evaluate(tier_rows, trial)
                if fa:
                    continue
                cost = (held + 2 * fb, abs(review - current.review) + abs(block - current.block))
                if best is None or cost < best[0]:
                    best = (cost, review, block, fb, held)
        n_safe = sum(1 for r in tier_rows if r[0]["safe"])
        print(f"[{tier.value}] {len(tier_rows)} casos ({n_safe} seguros)")
        print(f"   actual    review={current.review:.2f} block={current.block:.2f}  "
              f"false_allow={base[0]} false_block={base[1]} seguras_a_persona={base[2]}")
        if best:
            _, review, block, fb, held = best
            print(f"   sugerido  review={review:.2f} block={block:.2f}  false_allow=0 false_block={fb} seguras_a_persona={held}")
        else:
            print("   ninguna combinación evita todos los false_allow: revisar preguntas o reglas")


if __name__ == "__main__":
    main()
