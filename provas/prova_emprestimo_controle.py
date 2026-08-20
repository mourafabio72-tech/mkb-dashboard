"""
prova_emprestimo_controle.py — trava o controle do empréstimo bancário pela
planilha de controle do escritório (contrato CEF do Gnileb, jul/2026).

O quadro por contrato mostrava três números errados e incoerentes entre si,
cada um de uma fonte diferente:

              app          planilha
  Total pago  237.904      332.812,04   (débito na conta de principal é só
                                         amortização, sem os juros da parcela)
  Saldo       1.862.950    1.776.640,54 (saldo contábil carrega reclassificação
                                         de LP para CP -- e ficava MAIOR que o
                                         valor contratado de 1.500.000)
  Parcelas    11/48        10/48        (contava calendário, não pagamento)

Agora o cronograma importado manda, e a coluna "Parcela paga" da planilha é a
fonte do que foi pago -- ela registra inclusive as duas parcelas quitadas em
jun/2026. O razão entra como conferência, não como fonte.

Rodar:  DB_PATH=<temp.db> python provas/prova_emprestimo_controle.py
"""
import os, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
if not os.environ.get("DB_PATH"):
    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prova_emp.db")

from ingestion import get_conn, criar_schema, seed_empresas          # noqa: E402
from emprestimo_bancario_parser import importar_cronograma           # noqa: E402
import app as A                                                      # noqa: E402

GNI = 2
CP  = "2.1.1.01.07.001"
PMT = 46753.698324228164
CAR = 19808.71          # parcelas 1-5, período de carência (só juros)

ok = True
def check(nome, cond, extra=""):
    global ok
    print(("  OK   " if cond else "  FALHA ") + nome + (f"  {extra}" if extra else ""))
    ok = ok and bool(cond)


def montar(cronograma_csv):
    """Monta o contrato e um cronograma equivalente ao da planilha real."""
    conn = get_conn(); criar_schema(conn); seed_empresas(conn)
    conn.execute("DELETE FROM emprestimos_parcelas")
    conn.execute("DELETE FROM emprestimos_bancarios WHERE empresa_id=?", (GNI,))
    conn.execute("DELETE FROM razao WHERE empresa_id=?", (GNI,))
    cur = conn.execute(
        "INSERT INTO emprestimos_bancarios (empresa_id, banco, descricao,"
        " conta_cp_principal, valor_contratado, qtd_parcelas, data_primeira_parcela,"
        " valor_parcela_fixa) VALUES (?,?,?,?,?,?,?,?)",
        (GNI, "CEF", "Capital de giro", CP, 1500000.0, 48, "2025-11", PMT),
    )
    eid = cur.lastrowid
    conn.executemany(
        "INSERT INTO emprestimos_parcelas (emprestimo_id, numero_parcela, competencia,"
        " amortizacao, juros, saldo_devedor, valor_parcela, parcela_paga, saldo_total)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        [(eid, *linha) for linha in cronograma_csv],
    )
    # o razão só tem a amortização acumulada, bem menor que o desembolso
    conn.execute(
        "INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento,"
        " historico, debito, credito, valor) VALUES (?,?,?,?,?,?,?,?,?)",
        (GNI, "2026-07", "2026-07-05", CP, "PG", "AMORT", 237904.0, 0, 0),
    )
    conn.commit(); conn.close()
    return eid


# nº, competência, amort, juros, sd principal, pmt, parcela paga, saldo total
CRONO = [
    (1, "2025-11", 0.0,      CAR,      1500000.0, CAR, CAR,      2089643.87),
    (2, "2025-12", 0.0,      CAR,      1500000.0, CAR, CAR,      2069835.16),
    (3, "2026-01", 0.0,      CAR,      1500000.0, CAR, CAR,      2050026.45),
    (4, "2026-02", 0.0,      CAR,      1500000.0, CAR, CAR,      2030217.74),
    (5, "2026-03", 0.0,      CAR,      1500000.0, CAR, CAR,      2010409.03),
    (6, "2026-04", 0.0,      CAR,      1500000.0, PMT, PMT,      1963655.33),
    (7, "2026-05", 26953.70, 19800.00, 1473046.30, PMT, PMT,     1916901.63),
    (8, "2026-06", 27309.49, 19444.21, 1445736.81, PMT, PMT * 2, 1823394.23),  # DUAS
    (9, "2026-07", 27669.97, 19083.73, 1418066.84, PMT, PMT,     1776640.54),
    (10, "2026-08", 28035.22, 18718.48, 1390031.63, PMT, None,   1776640.54),
    (11, "2026-09", 28405.28, 18348.42, 1361626.35, PMT, None,   1776640.54),
]
TOTAL_PAGO = round(CAR * 5 + PMT * 5, 2)     # 5 de carência + 4 vencimentos, um deles em dobro

print("\n=== 1. o quadro sai da planilha, não do razão ===")
montar(CRONO)
resp = None
A.app.config["TESTING"] = True
cli = A.app.test_client()
with cli.session_transaction() as sess:
    sess["usuario_logado"] = {"id": 1, "role": "admin", "nome": "T"}
r = cli.get("/endividamento-bancario/gnileb")
check("página abre", r.status_code == 200, f"({r.status_code})")
h = r.get_data(as_text=True)
check("fonte é o controle da planilha", "Controle (planilha)" in h)

print("\n=== 2. os três números batem com a planilha ===")
conn = get_conn()
parc = conn.execute("SELECT * FROM emprestimos_parcelas ORDER BY numero_parcela").fetchall()
conn.close()
pagas = [p for p in parc if p["parcela_paga"]]
total_pago = round(sum(p["parcela_paga"] for p in pagas), 2)
check("total pago = soma da coluna Parcela paga", abs(total_pago - TOTAL_PAGO) < 0.01,
      f"({total_pago:.2f})")
check("total pago maior que o do razão (que é só amortização)", total_pago > 237904.0)
n_pagas = sum(max(1, round(p["parcela_paga"] / p["valor_parcela"])) for p in pagas)
check("parcela dobrada conta como duas", n_pagas == 10, f"({n_pagas}, são 9 vencimentos)")
saldo = pagas[-1]["saldo_total"]
check("saldo a pagar = saldo devedor da última paga", abs(saldo - 1776640.54) < 0.01, f"({saldo})")
check("saldo do principal fica abaixo do contratado",
      pagas[-1]["saldo_devedor"] < 1500000.0, f"({pagas[-1]['saldo_devedor']})")

print("\n=== 3. a série mensal usa o PAGO, não o previsto ===")
comps = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
pg = A._pagamentos_mensais_bancario(GNI, comps)
check("carência: jan = 19.808,71", abs(pg["2026-01"] - CAR) < 0.01, f"({pg['2026-01']:.2f})")
check("depois da carência: mai = 46.753,70", abs(pg["2026-05"] - PMT) < 0.01, f"({pg['2026-05']:.2f})")
check("junho traz as DUAS parcelas", abs(pg["2026-06"] - PMT * 2) < 0.01, f"({pg['2026-06']:.2f})")
check("julho volta a uma", abs(pg["2026-07"] - PMT) < 0.01, f"({pg['2026-07']:.2f})")
check("mês ainda não pago não entra", pg["2026-08"] == 0.0, f"({pg['2026-08']:.2f})")

print("\n=== 4. sem controle de pagamento, cai no previsto (planilha só do banco) ===")
CRONO_SEM_PAGO = [(n, c, a, j, sd, pmt, None, st) for (n, c, a, j, sd, pmt, _p, st) in CRONO]
montar(CRONO_SEM_PAGO)
pg2 = A._pagamentos_mensais_bancario(GNI, ["2026-06", "2026-08"])
check("usa o PMT previsto quando não há coluna paga", abs(pg2["2026-06"] - PMT) < 0.01,
      f"({pg2['2026-06']:.2f})")
check("inclusive em mês futuro", abs(pg2["2026-08"] - PMT) < 0.01, f"({pg2['2026-08']:.2f})")

print("\n=== 5. o importador lê a planilha de controle real ===")
real = Path("/Users/fabiomoura/Library/CloudStorage/OneDrive-BibliotecasCompartilhadas-"
            "BPS4OUTSOURCING/Intranet BPS4 - Op. CONTABILIDADE/04 - Grupo Markbuilding/"
            "00 - MKB/Apresentação Mensal/BPS4/2026/07/Controle emprestimo bancário Gnileb.xlsx")
if real.exists():
    eid = montar(CRONO)
    conn = get_conn()
    res = importar_cronograma(real, eid, conn)
    conn.close()
    check("48 parcelas lidas", res.get("registros") == 48, f"({res})")
    check("9 com pagamento registrado", res.get("com_pagamento") == 9)
    check("total pago = 332.812,04", abs(res.get("total_pago", 0) - 332812.04) < 0.01,
          f"({res.get('total_pago')})")
else:
    print("  (pulado: planilha real não está nesta máquina)")

print("\n" + ("TODAS AS PROVAS PASSARAM" if ok else "HOUVE FALHA"))
sys.exit(0 if ok else 1)
