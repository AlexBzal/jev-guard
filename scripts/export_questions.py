"""Genera el catálogo de preguntas a JEV de un perfil, a partir del código y la configuración.

    python scripts/export_questions.py                       # perfil demo -> docs/PREGUNTAS.md
    python scripts/export_questions.py --profile 30x --out docs/caso-30x/PREGUNTAS.md
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
TYPE_NAMES = {"noul": "Noul (sí/no)", "score": "Score (escala)", "choice": "Choice (opciones)"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="demo")
    ap.add_argument("--out", default=str(ROOT / "docs" / "PREGUNTAS.md"))
    args = ap.parse_args()
    os.environ["JEV_GUARD_PROFILE"] = args.profile

    from guard.config import load_context, load_policy
    from guard.questions import QuestionCatalog

    policy, context = load_policy(), load_context()
    catalog = QuestionCatalog(policy, context)
    lines = [
        f"# Catálogo de preguntas a JEV · perfil `{policy.profile}` ({context.company.name})",
        "",
        f"Generado con `python scripts/export_questions.py --profile {policy.profile}`. No editar a mano.",
        "",
        "Todas las preguntas de una acción viajan en una sola llamada a JEV. Cada respuesta se convierte en un",
        "riesgo de 0 a 1 y una certeza de 0 a 1. El peso indica cuánto aporta al riesgo compuesto.",
        f"Las señales críticas frenan la acción por sí solas cuando su riesgo supera {policy.critical_block:.2f}.",
        "Las preguntas citan campos del estado entre comillas invertidas, por ejemplo `context.company`.",
        "",
        "## Umbrales por tier",
        "",
        "| Tier | Retener desde | Frenar desde | Certeza mínima | Si JEV duda | Si JEV no responde |",
        "|---|---|---|---|---|---|",
    ]
    for tier, tp in policy.tiers.items():
        lines.append(f"| {tier.value} | {tp.review:.2f} | {tp.block:.2f} | {tp.min_certainty:.2f} | "
                     f"{'LLM' if tp.on_uncertain == 'llm' else 'persona'} | "
                     f"{'deja pasar' if tp.on_jev_error == 'allow' else 'retiene'} |")
    for action_type in policy.action_types:
        custom = policy.custom_actions.get(action_type)
        title = f"`{action_type}`" + (f" · acción personalizada: {custom.label}" if custom else "")
        lines += ["", f"## {title}", "", "| ID | Tipo | Pregunta | Peso | Crítica |", "|---|---|---|---|---|"]
        details = []
        for s in catalog.sets[action_type]:
            q = s.question
            lines.append(f"| `{s.qid}` | {TYPE_NAMES[q['type']]} | {q['instructions']} | {s.weight:.2f} | "
                         f"{'sí' if s.critical else ''} |")
            if q["type"] == "choice":
                details.append(f"- `{s.qid}`: " + "; ".join(f"`{k}`: {v}" for k, v in q["criteria"].items()))
            elif q["type"] == "score":
                details.append(f"- `{s.qid}`: " + "; ".join(f"{i}. {v}" for i, v in enumerate(q["criteria"])))
        if details:
            lines += ["", "Opciones y niveles:", "", *details]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Escrito {out}")


if __name__ == "__main__":
    main()
