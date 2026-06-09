"""testar_ct1.py -- valida o pipeline CT1 completo."""
import sys
sys.path.insert(0, ".")
from ingestion import get_conn
from dre_engine import calcular_dre, fmt_brl, EMPRESAS

erros = []
conn = get_conn()

# 1. View v_lancamentos existe?
view = conn.execute(
    "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_lancamentos'"
).fetchone()
print(f"  {'OK' if view else 'FALHOU'}  view v_lancamentos existe")
if not view: erros.append("view ausente")

# 2. Dados CT2 ainda acessíveis pela view
rob_ct2 = conn.execute("""
    SELECT SUM(valor) FROM v_lancamentos
    WHERE empresa_id=1 AND competencia='2026-01' AND conta_cod LIKE '3.1.1.%'
""").fetchone()[0]
esperado = 6431591.17
dif = abs((rob_ct2 or 0) - esperado)
print(f"  {'OK' if dif < 1 else 'FALHOU'}  ROB Jan/2026 via view: {fmt_brl(rob_ct2 or 0)} (esperado {fmt_brl(esperado)}, dif={dif:.2f})")
if dif >= 1: erros.append(f"ROB divergente: {dif}")

# 3. Dados CT1 (Razão 2023-02) importados
n_razao = conn.execute(
    "SELECT COUNT(*) FROM razao WHERE competencia='2023-02'"
).fetchone()[0]
print(f"  {'OK' if n_razao > 1000 else 'FALHOU'}  Razão 2023-02: {n_razao} lançamentos")
if n_razao <= 1000: erros.append(f"Razão insuficiente: {n_razao}")

# 4. DRE de 2026-04 ainda calcula corretamente (usa lancamentos CT2 via view)
dre = calcular_dre(EMPRESAS["mkb"]["id"], "2026-04")
rob_2604 = dre.get("ROB", 0)
print(f"  {'OK' if abs(rob_2604 - 6717455) < 100 else 'FALHOU'}  DRE MKB Abr/2026 ROB: {fmt_brl(rob_2604)}")
if abs(rob_2604 - 6717455) >= 100: erros.append(f"DRE incorreta: {rob_2604}")

# 5. Flask routes ok
from app import app
with app.test_client() as c:
    for url in ["/", "/dre/2026-04", "/ingest", "/dre/mensal/consolidado"]:
        r = c.get(url)
        ok = r.status_code == 200
        print(f"  {'OK' if ok else 'FALHOU'}  {r.status_code}  {url}")
        if not ok: erros.append(f"{url} -> {r.status_code}")

conn.close()
print()
if erros:
    print(f"FALHA: {len(erros)} erro(s):")
    for e in erros: print(f"  - {e}")
    sys.exit(1)
else:
    print("Todos os testes passaram!")
