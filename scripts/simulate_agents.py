"""Simula a los agentes de 30X trabajando: un flujo continuo de acciones contra la API.

    uvicorn guard.api:app                       # en otra terminal
    python scripts/simulate_agents.py --rate 5 --count 300 --auto-review

Toma los casos del perfil (profiles/<perfil>/scenarios*.yaml) como plantillas (los seguros pesan más, como
en la operación real) y los envía a POST /v1/guard/check.

--auto-review imita al equipo humano: resuelve las retenidas con la etiqueta de la
plantilla después de unos segundos, y audita una muestra de decisiones automáticas.
Así se llenan las métricas de calidad del tablero.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
REVIEWERS = ["ops-ana", "ops-luis", "ops-marta"]


def load_templates() -> list[dict]:
    out = []
    for path in sorted((ROOT / "profiles" / os.environ.get("JEV_GUARD_PROFILE", "demo")).glob("scenarios*.yaml")):
        out += yaml.safe_load(path.read_text(encoding="utf-8"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--rate", type=float, default=3.0, help="acciones por segundo")
    ap.add_argument("--count", type=int, default=200, help="0 = sin fin")
    ap.add_argument("--safe-weight", type=float, default=4.0, help="peso relativo de las plantillas seguras")
    ap.add_argument("--auto-review", action="store_true")
    ap.add_argument("--review-delay", type=float, default=4.0)
    ap.add_argument("--audit-share", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(args.seed)
    templates = load_templates()
    weights = [args.safe_weight if t["safe"] else 1.0 for t in templates]
    http = httpx.Client(base_url=args.url, timeout=30)
    try:
        print("Guardián:", http.get("/health").json())
    except httpx.HTTPError as exc:
        print(f"No se pudo conectar con {args.url}: {exc}")
        return 1

    pending: list[tuple[float, str, bool]] = []
    lock = threading.Lock()
    stop = threading.Event()

    def reviewer():
        while not stop.is_set() or pending:
            now = time.monotonic()
            with lock:
                due = [p for p in pending if p[0] <= now]
                for p in due:
                    pending.remove(p)
            for _, decision_id, safe in due:
                http.post(f"/v1/reviews/{decision_id}", json={
                    "approve": safe, "reviewer": rng.choice(REVIEWERS),
                    "note": "Aprobado" if safe else "Rechazado en revisión"})
            time.sleep(0.5)

    worker = threading.Thread(target=reviewer, daemon=True)
    if args.auto_review:
        worker.start()

    counts: dict[str, int] = {}
    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            tpl = rng.choices(templates, weights=weights)[0]
            action = dict(tpl["action"], action_id=f"act_{uuid.uuid4().hex[:12]}")
            resp = http.post("/v1/guard/check", json=action)
            if resp.status_code != 200:
                print(f"[{tpl['id']}] error {resp.status_code}: {resp.text[:200]}")
            else:
                d = resp.json()
                counts[d["verdict"]] = counts.get(d["verdict"], 0) + 1
                print(f"{d['verdict']:5} {d['route']:5} {d['tier']:8} {d['latency_ms']:7.1f} ms  {tpl['id']}")
                if args.auto_review:
                    if d["verdict"] == "hold":
                        with lock:
                            pending.append((time.monotonic() + args.review_delay, d["decision_id"], tpl["safe"]))
                    elif rng.random() < args.audit_share:
                        http.post(f"/v1/decisions/{d['decision_id']}/label",
                                  json={"safe": tpl["safe"], "reviewer": rng.choice(REVIEWERS), "note": "auditoría"})
            sent += 1
            time.sleep(1 / args.rate if args.rate > 0 else 0)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if args.auto_review:
            worker.join(timeout=args.review_delay + 5)

    print("\nResumen:", counts)
    m = http.get("/v1/metrics").json()
    print(f"Automatización {m['automation_rate']}, p95 {m['latency_ms']['p95']} ms, "
          f"costo por 1.000 {m['cost_per_1000_usd']} USD, calidad {m['quality']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
