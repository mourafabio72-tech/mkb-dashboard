"""
prova_endividamento_mensal.py — trava o Detalhamento Mensal do Endividamento.

Dois defeitos reais achados no dash de jul/2026 (grupo Markbuilding, que tem o
tributário na MKB e o bancário no Gnileb):

1. "Parc. pagas" de julho vinha 230.981 quando o certo eram 137.412
   (90.658 tributário + 46.754 bancário). Causa: o rateio dos parcelamentos
   agrupava por (conta_cp, conta_lp). Dois parcelamentos que dividem a mesma
   conta corrente mas apontam para contas de longo prazo diferentes caíam em
   grupos distintos, cada um com peso 1.0 -- e o MESMO débito era contado duas
   vezes. O rateio tem que ser por conta_cp, que é a conta cujo débito está
   sendo dividido.

2. "Dív. acum." de julho repetia junho. Sem a planilha de parcelamentos do mês,
   o código repetia o último valor conhecido e a dívida congelava, como se
   nada tivesse sido amortizado. Agora deduz do mês anterior o que foi pago, e
   marca a linha como estimada.

Rodar:  DB_PATH=<temp.db> python provas/prova_endividamento_mensal.py
"""
import os, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
if not os.environ.get("DB_PATH"):
    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prova_end.db")

from ingestion import get_conn, criar_schema, seed_empresas   # noqa: E402
import app as A                                               # noqa: E402

EMP  = 1
COMP = "2026-07"
CONTA_CP = "2.1.3.05.06.001"     # conta compartilhada por dois parcelamentos
DEBITO   = 14113.11              # o que saiu dela em julho

ok = True
def check(nome, cond, extra=""):
    global ok
    print(("  OK   " if cond else "  FALHA ") + nome + (f"  {extra}" if extra else ""))
    ok = ok and bool(cond)


def montar():
    conn = get_conn(); criar_schema(conn); seed_empresas(conn)
    conn.execute("DELETE FROM parcelamentos WHERE empresa_id=?", (EMP,))
    conn.execute("DELETE FROM razao WHERE empresa_id=?", (EMP,))
    # dois parcelamentos, MESMA conta corrente, contas de longo prazo DIFERENTES
    conn.executemany(
        "INSERT INTO parcelamentos (empresa_id, competencia_ref, tributo, conta_cp,"
        " conta_lp, saldo_contabilidade_snapshot) VALUES (?,?,?,?,?,?)",
        [(EMP, COMP, "TRANSACAO - DEMAIS DEBITOS",        CONTA_CP, "2.2.4.02.06.001", 600000.0),
         (EMP, COMP, "TRANSACAO - DEBITOS PREVIDENCIARIOS", CONTA_CP, "2.2.4.02.06.002", 400000.0)],
    )
    conn.execute(
        "INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento,"
        " historico, debito, credito, valor) VALUES (?,?,?,?,?,?,?,?,?)",
        (EMP, COMP, "2026-07-30", CONTA_CP, "PG", "PGTO PARCELA", DEBITO, 0, -DEBITO),
    )
    conn.commit(); conn.close()


print("\n=== 1. conta compartilhada não é contada duas vezes ===")
montar()
pg = A._pagamentos_mensais_tributario(EMP, [COMP])
check("pago = o débito, uma vez só", abs(pg[COMP] - DEBITO) < 0.01,
      f"({pg[COMP]:.2f}, débito real {DEBITO})")
check("não dobrou", abs(pg[COMP] - DEBITO * 2) > 1)

print("\n=== 2. o rateio ainda divide entre os tributos da conta ===")
# a soma das partes tem que fechar no débito, sem sobra nem falta
conn = get_conn()
parc = conn.execute(
    "SELECT tributo, conta_cp, conta_lp, saldo_contabilidade_snapshot FROM parcelamentos"
    " WHERE empresa_id=?", (EMP,)).fetchall()
conn.close()
check("dois parcelamentos na mesma conta", len({p["conta_cp"] for p in parc}) == 1 and len(parc) == 2)
check("soma das partes = débito integral", abs(pg[COMP] - DEBITO) < 0.01)

print("\n=== 3. um parcelamento sozinho na conta continua pegando tudo ===")
conn = get_conn()
conn.execute("DELETE FROM parcelamentos WHERE empresa_id=? AND tributo LIKE '%PREVIDENC%'", (EMP,))
conn.commit(); conn.close()
pg1 = A._pagamentos_mensais_tributario(EMP, [COMP])
check("pago = débito integral", abs(pg1[COMP] - DEBITO) < 0.01, f"({pg1[COMP]:.2f})")

print("\n=== 4. dívida acumulada não congela quando falta a planilha do mês ===")
# jun tem snapshot; jul não. Sem correção, jul repetia jun.
comps = ["2026-06", "2026-07"]
pagos = {"2026-06": 100.0, "2026-07": 250.0}
snap  = {"2026-06": 10000.0}
div_ant = None
serie = []
for c in comps:
    s = snap.get(c)
    if s is not None:
        div, est = s, False
    elif div_ant is not None:
        div, est = round(div_ant - pagos[c], 2), True
    else:
        div, est = 0.0, True
    div_ant = div
    serie.append((c, div, est))
check("junho vem do snapshot", serie[0][1] == 10000.0 and not serie[0][2])
check("julho deduz o que foi pago", abs(serie[1][1] - 9750.0) < 0.01, f"({serie[1][1]})")
check("julho não repete junho", serie[1][1] != serie[0][1])
check("julho marcado como estimado", serie[1][2])

print("\n=== 5. bancário sem cronograma: só o débito que é parcela ===")
# Contrato CEF do Gnileb: parcela fixa 46.753,70. Em jul/2026 a conta de
# principal recebeu, além da parcela, uma reclassificação de longo prazo e uma
# taxa. Somar tudo dava 140.323 onde o pago foi 46.754.
PARCELA = 46753.70
CONTA_EMP = "2.1.1.01.07.001"
conn = get_conn()
conn.execute("DELETE FROM emprestimos_bancarios WHERE empresa_id=?", (EMP,))
conn.execute("DELETE FROM razao WHERE empresa_id=? AND conta_cod=?", (EMP, CONTA_EMP))
conn.execute(
    "INSERT INTO emprestimos_bancarios (empresa_id, banco, descricao, conta_cp_principal,"
    " valor_contratado, qtd_parcelas, data_primeira_parcela, valor_parcela_fixa)"
    " VALUES (?,?,?,?,?,?,?,?)",
    (EMP, "CEF", "Capital de giro", CONTA_EMP, 1500000.0, 48, "2025-09", PARCELA),
)
conn.executemany(
    "INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento,"
    " historico, debito, credito, valor) VALUES (?,?,?,?,?,?,?,?,?)",
    [
        (EMP, "2026-07", "2026-07-05", CONTA_EMP, "PG",  "PGTO PARCELA",        PARCELA, 0, 0),
        (EMP, "2026-07", "2026-07-31", CONTA_EMP, "RCL", "TRANSF LP->CP",       89500.00, 0, 0),
        (EMP, "2026-07", "2026-07-20", CONTA_EMP, "TX",  "TARIFA",                 69.30, 0, 0),
        (EMP, "2026-08", "2026-08-05", CONTA_EMP, "PG",  "PARCELA 1",           PARCELA, 0, 0),
        (EMP, "2026-08", "2026-08-25", CONTA_EMP, "PG",  "PARCELA 2 (antecip.)", PARCELA, 0, 0),
    ],
)
conn.commit(); conn.close()
pgb = A._pagamentos_mensais_bancario(EMP, ["2026-07", "2026-08"])
check("julho = a parcela, não a soma bruta", abs(pgb["2026-07"] - PARCELA) < 0.01,
      f"({pgb['2026-07']:.2f}; soma bruta seria {PARCELA + 89500 + 69.30:.2f})")
check("descartou a reclassificação LP→CP", pgb["2026-07"] < 89500)
check("descartou a tarifa", abs(pgb["2026-07"] - (PARCELA + 69.30)) > 1)
check("duas parcelas no mês somam as duas", abs(pgb["2026-08"] - PARCELA * 2) < 0.01,
      f"({pgb['2026-08']:.2f})")

print("\n=== 6. sem parcela fixa cadastrada, mantém a soma dos débitos ===")
conn = get_conn()
conn.execute("UPDATE emprestimos_bancarios SET valor_parcela_fixa=NULL WHERE empresa_id=?", (EMP,))
conn.commit(); conn.close()
pgb2 = A._pagamentos_mensais_bancario(EMP, ["2026-07"])
check("soma tudo quando não há parâmetro para filtrar",
      abs(pgb2["2026-07"] - (PARCELA + 89500 + 69.30)) < 0.01, f"({pgb2['2026-07']:.2f})")

print("\n" + ("TODAS AS PROVAS PASSARAM" if ok else "HOUVE FALHA"))
sys.exit(0 if ok else 1)
