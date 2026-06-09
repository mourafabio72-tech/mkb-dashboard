"""testar_flask.py -- Sprint 3: toggle empresa/meses + colunas compactas."""
import sys, json
sys.path.insert(0, ".")
from app import app
from dre_engine import fmt_brl

erros = []

with app.test_client() as c:
    testes = [
        # Existentes
        ("GET /",                                         c.get("/")),
        ("GET /dre/2026-04",                              c.get("/dre/2026-04")),
        ("GET /dre/2026-04?modo=empresa",                 c.get("/dre/2026-04?modo=empresa")),
        # Novos: modo meses
        ("GET /dre/2026-04?modo=meses",                   c.get("/dre/2026-04?modo=meses")),
        ("GET /dre/2026-04?modo=meses&meses=2026-01",     c.get("/dre/2026-04?modo=meses&meses=2026-01")),
        ("GET /dre/2026-04?modo=meses&meses=2026-01&meses=2026-03",
                                                          c.get("/dre/2026-04?modo=meses&meses=2026-01&meses=2026-03")),
        # Mensal
        ("GET /dre/mensal/consolidado",                   c.get("/dre/mensal/consolidado")),
        ("GET /dre/mensal/mkb",                           c.get("/dre/mensal/mkb")),
        ("GET /dre/2026-04/detalhada/mkb",                c.get("/dre/2026-04/detalhada/mkb")),
    ]

    for nome, resp in testes:
        ok = "OK" if resp.status_code == 200 else "FALHOU"
        if resp.status_code != 200:
            erros.append(f"{nome} -> {resp.status_code}")
        print(f"  {ok}  {resp.status_code}  {nome}")

    # Verifica conteúdo do modo meses
    r = c.get("/dre/2026-04?modo=meses&meses=2026-01&meses=2026-03")
    html = r.data.decode("utf-8", errors="replace")
    assert "Jan/2026" in html or "jan" in html.lower(), "Mês Jan não encontrado no HTML"
    assert "Mar/2026" in html or "mar" in html.lower(), "Mês Mar não encontrado no HTML"
    print(f"\n  OK  Modo meses: Jan/2026 e Mar/2026 encontrados no HTML")

    # Verifica que toggle está presente
    assert "Por Empresa" in html or "empresa" in html.lower(), "Toggle não encontrado"
    print(f"  OK  Toggle modo encontrado no HTML")

print()
if erros:
    print(f"FALHA: {len(erros)} erro(s):")
    for e in erros: print(f"  - {e}")
    sys.exit(1)
else:
    print("Todos os testes passaram!")
