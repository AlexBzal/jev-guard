"""La interfaz no tiene compilación: esta prueba carga cada módulo con Node para detectar
errores de sintaxis o importaciones rotas, que en el navegador dejan la página en blanco
sin ningún mensaje visible."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent.parent / "ui" / "js"
MODULES = sorted(p for p in UI.rglob("*.js") if p.name != "app.js")  # app.js arranca con el DOM


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_ui_modules_load():
    script = (
        "const files = JSON.parse(process.argv[1]);"
        "Promise.all(files.map(f => import(f).then(() => null, e => f + ': ' + e.message)))"
        ".then(r => { const bad = r.filter(Boolean); console.log(JSON.stringify(bad)); process.exit(bad.length ? 1 : 0); });"
    )
    urls = [p.as_uri() for p in MODULES]
    result = subprocess.run(["node", "--input-type=module", "-e", script, json.dumps(urls)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_app_entry_has_valid_syntax():
    # app.js toca el DOM al cargarse, así que solo se valida su sintaxis.
    code = (UI / "app.js").read_text(encoding="utf-8")
    result = subprocess.run(["node", "--input-type=module", "--check"], input=code, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 0, result.stderr
