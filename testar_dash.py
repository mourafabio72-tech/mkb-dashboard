import sys
sys.path.insert(0, ".")
from app import app
from dre_engine import calcular_rob_por_segmento, calcular_top_contas_custo, calcular_serie_mensal

erros = []
with app.test_client() as c:
    testes = [
        ("GET /",                       c.get("/")),
        ("GET /dre/2026-04",            c.get("/dre/2026-04")),
        ("GET /dre/2026-04?modo=meses", c.get("/dre/2026-04?modo=meses")),
    ]
    for nome, r in testes:
        ok = "OK" if r.status_code == 200 else "FALHOU"
        if r.status_code != 200: erros.append(f"{nome} -> {r.status_code}")
        print(f"  {ok}  {r.status_code}  {nome}")

    html = c.get("/").data.decode("utf-8", errors="replace")
    checks = [
        "chartPizza", "chartRob", "chartLB", "chartEbitda", "chartTop5",
        "const serie", "const segmentos", "const top5",
        "EBITDA", "chart.umd.min.js",
    ]
    print()
    for ch in checks:
        found = ch in html
        mark = "OK" if found else "FALHOU"
        if not found: erros.append(f"[{ch}] nao encontrado")
        print(f"  {mark}  [{ch}]")

# Engine tests
print()
comps = ["2026-01","2026-02","2026-03","2026-04"]
seg = calcular_rob_por_segmento(comps)
assert len(seg) >= 2, "Segmentos de receita insuficientes"
print(f"  OK  Segmentos ROB: {[s['label'] for s in seg]}")

top5 = calcular_top_contas_custo(comps)
assert len(top5) >= 3, "Top5 insuficiente"
print(f"  OK  Top 5 custos: {[t['label'][:20] for t in top5]}")

serie = calcular_serie_mensal(comps)
assert serie["rob"][0] > 0, "ROB Jan deve ser positivo"
print(f"  OK  Série mensal ROB: {serie['rob']}")
print(f"  OK  Margens LB: {serie['margem_lb']}")

print()
if erros:
    print(f"FALHA: {len(erros)} erro(s):")
    for e in erros: print(f"  - {e}")
    sys.exit(1)
else:
    print("Todos os testes passaram!")
