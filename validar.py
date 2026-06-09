"""validar.py — Testes de validação do banco vs Excel original."""
import sqlite3

conn = sqlite3.connect("mkb_dre.db")

print("=== TOTAL POR EMPRESA E COMPETENCIA ===")
rows = conn.execute("""
    SELECT e.sigla, l.competencia, COUNT(*) as contas
    FROM lancamentos l JOIN empresas e ON l.empresa_id = e.id
    GROUP BY e.sigla, l.competencia ORDER BY l.competencia, e.sigla
""").fetchall()
for r in rows:
    print(f"  {r[0]:8s} {r[1]}  {r[2]} contas")

print()
print("=== VALIDACAO: RECEITA BRUTA MKB JAN 2026 ===")
rob = conn.execute("""
    SELECT ROUND(SUM(valor), 2)
    FROM lancamentos
    WHERE empresa_id=1 AND competencia='2026-01' AND conta_cod LIKE '3.1.1.%'
""").fetchone()[0]
print(f"  ROB (3.1.1.*) Jan/2026: R$ {rob:>15,.2f}")

# Soma esperada: 149.180,73 + 3.824.517,63 + 941.611,03 + 10.690,25 + 1.505.591,53
esperado = 149180.73 + 3824517.63 + 941611.03 + 10690.25 + 1505591.53
print(f"  Esperado (soma manual):  R$ {esperado:>15,.2f}")
print(f"  Diferença:               R$ {abs(rob - esperado):>15,.2f}")

print()
print("=== VALIDACAO: DEDUCOES MKB JAN 2026 ===")
ded = conn.execute("""
    SELECT ROUND(SUM(valor), 2)
    FROM lancamentos
    WHERE empresa_id=1 AND competencia='2026-01' AND conta_cod LIKE '3.1.3.%'
""").fetchone()[0]
print(f"  Deducoes (3.1.3.*) Jan/2026: R$ {ded:>15,.2f}")
ded_esp = -(314187.55 + 106121.31 + 488800.94)
print(f"  Esperado (soma manual):      R$ {ded_esp:>15,.2f}")

print()
print("=== RESULTADO LIQUIDO MKB JAN 2026 ===")
rl = conn.execute("""
    SELECT ROUND(SUM(valor), 2)
    FROM lancamentos
    WHERE empresa_id=1 AND competencia='2026-01'
""").fetchone()[0]
print(f"  Soma total (lucro liquido): R$ {rl:>15,.2f}")
print(f"  Esperado (TOTAL do Excel):  R$       -344,02  (linha TOTAL)")

print()
print("=== TOP 10 CONTAS MKB JAN 2026 (por valor absoluto) ===")
rows2 = conn.execute("""
    SELECT l.conta_cod, c.descricao, ROUND(l.valor,2)
    FROM lancamentos l LEFT JOIN contas c ON l.conta_cod=c.cod AND l.empresa_id=c.empresa_id
    WHERE l.empresa_id=1 AND l.competencia='2026-01'
    ORDER BY ABS(l.valor) DESC LIMIT 10
""").fetchall()
for r in rows2:
    print(f"  {r[0]}  {r[2]:>15,.2f}  {r[1]}")

print()
print("=== GNILEB JAN 2026 — RECEITA BRUTA ===")
rob_g = conn.execute("""
    SELECT ROUND(SUM(valor), 2)
    FROM lancamentos
    WHERE empresa_id=2 AND competencia='2026-01' AND conta_cod LIKE '3.1.1.%'
""").fetchone()[0]
print(f"  ROB Gnileb Jan/2026: R$ {rob_g:>15,.2f}")
# Esperado: 189.394,68 + 14.703,18 = 204.097,86
esp_g = 189394.68 + 14703.18
print(f"  Esperado:            R$ {esp_g:>15,.2f}")

conn.close()
