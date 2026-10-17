"""Genera docs/PREGUNTAS.md a partir del código (guard/questions.py y config/policy.yaml).

    python scripts/export_questions.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from guard.config import default_policy  # noqa: E402
from guard.models import ACTION_TYPES  # noqa: E402
from guard.questions import QUESTION_SETS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TYPE_NAMES = {"noul": "Noul (sí/no)", "score": "Score (escala)", "choice": "Choice (opciones)"}


def main() -> None:
    policy = default_policy()
    lines = [
        "# Catálogo de preguntas a JEV",
        "",
        "Generado automáticamente con `python scripts/export_questions.py`. No editar a mano.",
        "",
        "Todas las preguntas de una acción viajan en una sola llamada a JEV. Cada respuesta se convierte en un",
        "riesgo de 0 a 1 y una certeza de 0 a 1. El peso indica cuánto aporta al riesgo compuesto.",
        "Las señales críticas frenan la acción por sí solas cuando su riesgo supera "
        f"{policy.critical_block:.2f}.",
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
    for action_type in ACTION_TYPES:
        lines += ["", f"## `{action_type}`", "", "| ID | Tipo | Pregunta | Peso | Crítica |", "|---|---|---|---|---|"]
        details = []
        for s in QUESTION_SETS[action_type]:
            q = s.question
            lines.append(f"| `{s.qid}` | {TYPE_NAMES[q['type']]} | {q['instructions']} | {s.weight:.2f} | "
                         f"{'sí' if s.critical else ''} |")
            if q["type"] == "choice":
                opts = "; ".join(f"`{k}`: {v}" for k, v in q["criteria"].items())
                details.append(f"- `{s.qid}`: {opts}")
            elif q["type"] == "score":
                lvls = "; ".join(f"{i}. {v}" for i, v in enumerate(q["criteria"]))
                details.append(f"- `{s.qid}`: {lvls}")
        if details:
            lines += ["", "Opciones y niveles:", "", *details]
    out = ROOT / "docs" / "PREGUNTAS.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Escrito {out}")


if __name__ == "__main__":
    main()
