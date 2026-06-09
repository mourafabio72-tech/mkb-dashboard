from ingestion import get_conn
from dre_engine import classificar_conta

conn = get_conn()
rows = conn.execute(
    "SELECT l.conta_cod, c.descricao, l.valor FROM lancamentos l "
    "LEFT JOIN contas c ON l.conta_cod=c.cod AND l.empresa_id=c.empresa_id "
    "WHERE l.empresa_id=2 AND l.competencia='2026-04' ORDER BY l.conta_cod"
).fetchall()

print("=== GNILEB ABR/2026 - TODAS AS CONTAS ===")
total = 0
for cod, desc, val in rows:
    grupo = classificar_conta(cod)
    print(f"  {cod}  [{grupo:15s}]  {val:>15,.2f}  {desc or cod}")
    total += val
print(f"  TOTAL: {total:,.2f}")
conn.close()
