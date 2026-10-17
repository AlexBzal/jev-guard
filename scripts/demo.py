"""Levanta la demo completa con un solo comando.

    python scripts/demo.py               # http://127.0.0.1:8000
    python scripts/demo.py --port 8080 --no-browser

Activa el modo demo: reloj fijo en la hora de los casos, latencia realista del
simulador (70-300 ms, como JEV), control de tráfico desde la interfaz y una base
de datos aparte (data/runtime/demo.db). Si hay TYPESAFE_API_KEY, usa JEV real.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="Empieza con el registro vacío")
    args = ap.parse_args()

    os.environ.setdefault("JEV_GUARD_DEMO", "1")
    os.environ.setdefault("JEV_SIM_LATENCY", "1")
    db = ROOT / "data" / "runtime" / "demo.db"
    os.environ.setdefault("JEV_GUARD_DB", str(db))
    if args.fresh:
        for suffix in ("", "-wal", "-shm"):
            Path(str(db) + suffix).unlink(missing_ok=True)

    import uvicorn

    url = f"http://{args.host}:{args.port}/"
    print(f"JEV Guard en {url}  (Ctrl+C para detener)")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("guard.api:app", host=args.host, port=args.port, log_level="warning", app_dir=str(ROOT))


if __name__ == "__main__":
    main()
