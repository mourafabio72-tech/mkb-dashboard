"""
prova_ajuste_aprovacao.py — trava o fluxo de APROVAÇÃO do AJUSTE-SALDO.

Cenário reproduzido (caso real MKB, Jul/2026, conta 4.1.1.01.02.015):
  · razão e balancete de julho batem na casa do centavo;
  · o razão importado no app carrega 408 a mais de acumulado de um mês anterior;
  · o app ANTES lançava sozinho um AJUSTE-SALDO de +408 em 31/07, estragando o
    mês de julho e apagando o próprio alarme (tela dava check verde).

O que esta prova trava:
  1. importar balancete NÃO grava ajuste nenhum;
  2. a proposta aparece com o valor certo e aponta o MÊS DE ORIGEM;
  3. só o que o usuário aprova é gravado;
  4. aprovar não é definitivo: reenviar sem a conta remove o ajuste;
  5. reimportar o balancete limpa os ajustes daquela competência;
  6. com ajuste aprovado, a conciliação zera mas a diferença CRUA continua
     visível (incluir_ajustes=False) — o zero nunca é vendido como real.

Rodar:  DB_PATH=<temp.db> python provas/prova_ajuste_aprovacao.py
"""
import os, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
if not os.environ.get("DB_PATH"):
    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prova.db")

from ingestion import get_conn, criar_schema, seed_empresas    # noqa: E402
from dre_engine import (                                       # noqa: E402
    conciliar_balancete, propor_ajustes_saldo, ajustes_aplicados,
    aplicar_ajustes_saldo, remover_ajustes_saldo,
)

CONTA   = "4.1.1.01.02.015"
EMP     = 1
COMP    = "2026-07"
MOV_JUL = -580039.18      # razão e balancete de julho, idênticos
ACUM_OK = -3213060.57     # acumulado jan→jun correto (Protheus)
ERRO    = -408.00         # o que o app carrega a mais, nascido em março
BAL_JUL = round(ACUM_OK + MOV_JUL, 2)

ok = True
def check(nome, cond, extra=""):
    global ok
    print(("  OK   " if cond else "  FALHA ") + nome + (f"  {extra}" if extra else ""))
    ok = ok and bool(cond)


def montar_base(com_erro=True):
    """Base mínima: razão de março (acumulado, com ou sem o erro), razão de
    julho, balancete de março (correto) e balancete de julho (correto)."""
    conn = get_conn()
    criar_schema(conn)
    seed_empresas(conn)
    conn.execute("DELETE FROM razao WHERE empresa_id=?", (EMP,))
    conn.execute("DELETE FROM balancete WHERE empresa_id=?", (EMP,))
    acum_mar = round(ACUM_OK + (ERRO if com_erro else 0.0), 2)
    conn.executemany(
        "INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento,"
        " historico, debito, credito, valor) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (EMP, "2026-03", "2026-03-31", CONTA, "MAR", "acumulado jan-mar", 0, 0, acum_mar),
            (EMP, COMP,      "2026-07-31", CONTA, "JUL", "movimento julho",    0, 0, MOV_JUL),
        ],
    )
    conn.executemany(
        "INSERT INTO balancete (empresa_id, competencia, conta_cod, descricao,"
        " saldo_atual, mov_periodo) VALUES (?,?,?,?,?,?)",
        [
            (EMP, "2026-03", CONTA, "AUXILIO ALIMENTACAO", ACUM_OK, ACUM_OK),
            (EMP, COMP,      CONTA, "AUXILIO ALIMENTACAO", BAL_JUL, MOV_JUL),
        ],
    )
    conn.commit()
    conn.close()


def n_ajustes(comp=COMP):
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM razao WHERE empresa_id=? AND competencia=?"
        " AND documento='AJUSTE-SALDO'", (EMP, comp)
    ).fetchone()[0]
    conn.close()
    return n


print("\n=== 1. importar balancete não grava ajuste ===")
montar_base()
check("razão nasce sem AJUSTE-SALDO", n_ajustes() == 0, f"({n_ajustes()})")

print("\n=== 2. proposta traz o valor certo e o mês de origem ===")
props = propor_ajustes_saldo(EMP, COMP)
p = next((x for x in props if x["conta_cod"] == CONTA), None)
check("conta divergente proposta", p is not None)
check("ajuste = +408,00", p and abs(p["ajuste"] - 408.00) < 0.01, f"({p and p['ajuste']})")
check("origem apontada em 2026-03", p and p["origem"] == "2026-03", f"({p and p['origem']})")
check("marcada como nascida em outro mês", p and p["origem_outro_mes"])
check("ainda não aplicada", p and not p["aplicado"])

print("\n=== 3. só o aprovado é gravado ===")
aplicar_ajustes_saldo(EMP, COMP, [])
check("aprovar nada não grava nada", n_ajustes() == 0, f"({n_ajustes()})")
aplicar_ajustes_saldo(EMP, COMP, [CONTA])
check("aprovar a conta grava 1 ajuste", n_ajustes() == 1, f"({n_ajustes()})")
apl = ajustes_aplicados(EMP, COMP)
check("valor gravado = +408,00", apl and abs(apl[0]["valor"] - 408.00) < 0.01)

print("\n=== 4. o zero da tela não esconde a diferença crua ===")
com_aj  = conciliar_balancete(EMP, COMP)
sem_aj  = conciliar_balancete(EMP, COMP, incluir_ajustes=False)
check("com ajuste, concilia", abs(com_aj["tot_diff"]) < 0.01, f"({com_aj['tot_diff']})")
check("sem ajuste, diferença de 408 continua visível",
      abs(abs(sem_aj["tot_diff"]) - 408.00) < 0.01, f"({sem_aj['tot_diff']})")
check("proposta segue listada, agora como aplicada",
      any(x["conta_cod"] == CONTA and x["aplicado"] for x in propor_ajustes_saldo(EMP, COMP)))

print("\n=== 5. aprovação é reversível ===")
aplicar_ajustes_saldo(EMP, COMP, [])
check("desmarcar remove o ajuste", n_ajustes() == 0, f"({n_ajustes()})")
aplicar_ajustes_saldo(EMP, COMP, [CONTA])
check("remover_ajustes_saldo limpa a competência",
      remover_ajustes_saldo(EMP, COMP) == 1 and n_ajustes() == 0)

print("\n=== 6. corrigir o razão de origem dispensa o ajuste ===")
montar_base(com_erro=False)
props = propor_ajustes_saldo(EMP, COMP)
check("sem o erro de março, nada a propor", not props, f"({len(props)} proposta(s))")
check("concilia sem nenhum ajuste",
      abs(conciliar_balancete(EMP, COMP)["tot_diff"]) < 0.01 and n_ajustes() == 0)

print("\n" + ("TODAS AS PROVAS PASSARAM" if ok else "HOUVE FALHA"))
sys.exit(0 if ok else 1)
