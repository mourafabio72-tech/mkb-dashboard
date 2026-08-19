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
    ajustes_por_competencia, remover_todos_ajustes, reverter_ajustes_saldo,
    detectar_retroativos,
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

print("\n=== 7. ajuste de mês anterior não some do radar ===")
montar_base()
aplicar_ajustes_saldo(EMP, "2026-03", [CONTA])      # aprovado lá atrás
check("ajuste gravado em março", n_ajustes("2026-03") == 1)
comps = ajustes_por_competencia(EMP)
check("aparece no resumo por competência",
      any(c["competencia"] == "2026-03" and c["qtd"] == 1 for c in comps),
      f"({comps})")
outras = [c for c in comps if c["competencia"] != COMP]
check("é listado como 'outra competência' quando a tela está em julho", bool(outras))
check("remover_todos_ajustes limpa tudo",
      remover_todos_ajustes(EMP) >= 1 and not ajustes_por_competencia(EMP))

print("\n=== 8. origem acusa o gap de balancete ===")
# março e julho têm balancete; o erro entra em maio, sem balancete de mai/jun
conn = get_conn()
conn.execute("DELETE FROM razao WHERE empresa_id=?", (EMP,))
conn.executemany(
    "INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento,"
    " historico, debito, credito, valor) VALUES (?,?,?,?,?,?,?,?,?)",
    [(EMP, "2026-03", "2026-03-31", CONTA, "MAR", "acum ok", 0, 0, ACUM_OK),
     (EMP, "2026-05", "2026-05-31", CONTA, "MAI", "erro",    0, 0, ERRO),
     (EMP, COMP,      "2026-07-31", CONTA, "JUL", "julho",   0, 0, MOV_JUL)],
)
conn.commit(); conn.close()
p8 = next((x for x in propor_ajustes_saldo(EMP, COMP) if x["conta_cod"] == CONTA), None)
check("ainda propõe o ajuste", p8 is not None)
check("último mês conferido = 2026-03", p8 and p8["ultima_ok"] == "2026-03", f"({p8 and p8['ultima_ok']})")
check("primeiro mês divergente conferido = 2026-07", p8 and p8["origem"] == COMP)
check("marca o gap (não finge saber o mês exato)", p8 and p8["origem_gap"])

def acum(comp_ate="2026-12"):
    """Movimento acumulado da conta no razão (ajustes e estornos inclusos)."""
    conn = get_conn()
    v = conn.execute(
        "SELECT SUM(valor) FROM razao WHERE empresa_id=? AND conta_cod=? AND competencia<=?",
        (EMP, CONTA, comp_ate)
    ).fetchone()[0] or 0.0
    conn.close()
    return round(v, 2)

def mes(comp):
    conn = get_conn()
    v = conn.execute(
        "SELECT SUM(valor) FROM razao WHERE empresa_id=? AND conta_cod=? AND competencia=?",
        (EMP, CONTA, comp)
    ).fetchone()[0] or 0.0
    conn.close()
    return round(v, 2)

print("\n=== 9. estorno no mês de origem: acumulado E mês voltam ao razão puro ===")
montar_base()
aplicar_ajustes_saldo(EMP, "2026-03", [CONTA])
check("março ficou com o ajuste", abs(mes("2026-03") - (-3213468.57 + 408.0)) < 0.01)
res = reverter_ajustes_saldo(EMP)                     # destino=None
check("estornou 1 lançamento", res["revertidos"] == 1, f"({res})")
check("março voltou ao razão puro", abs(mes("2026-03") - (-3213468.57)) < 0.01, f"({mes('2026-03')})")
check("julho intacto", abs(mes(COMP) - MOV_JUL) < 0.01, f"({mes(COMP)})")
check("sai do painel de alerta (líquido zero)", not ajustes_por_competencia(EMP))
conn = get_conn()
n_hist = conn.execute(
    "SELECT COUNT(*) FROM razao WHERE empresa_id=? AND documento IN"
    " ('AJUSTE-SALDO','REVERSAO-AJUSTE')", (EMP,)).fetchone()[0]
conn.close()
check("histórico preservado: ajuste + estorno no extrato", n_hist == 2, f"({n_hist})")

print("\n=== 10. concentrar o estorno noutro mês fecha o ano e erra os meses ===")
montar_base()
aplicar_ajustes_saldo(EMP, "2026-03", [CONTA])
a_antes = acum()
res = reverter_ajustes_saldo(EMP, destino=COMP)
check("acumulado do ano volta ao razão puro",
      abs(acum() - (a_antes - 408.0)) < 0.01, f"({acum()})")
check("março CONTINUA com o ajuste sobrando",
      abs(mes("2026-03") - (-3213468.57 + 408.0)) < 0.01, f"({mes('2026-03')})")
check("julho fica faltando o mesmo valor",
      abs(mes(COMP) - (MOV_JUL - 408.0)) < 0.01, f"({mes(COMP)})")

print("\n=== 11. estorno é idempotente ===")
n1 = reverter_ajustes_saldo(EMP, destino=COMP)["revertidos"]
check("reverter de novo não duplica", n1 == 0 and abs(mes(COMP) - (MOV_JUL - 408.0)) < 0.01,
      f"({n1}, {mes(COMP)})")

print("\n=== 12. detecta lançamento retroativo pelo saldo anterior ===")
# Balancete de jan fecha em 1.000; o de fev abre em 1.050 sem movimento que
# explique: entraram 50 com data de janeiro DEPOIS que jan foi emitido.
conn = get_conn()
conn.execute("DELETE FROM balancete WHERE empresa_id=?", (EMP,))
conn.executemany(
    "INSERT INTO balancete (empresa_id, competencia, conta_cod, descricao,"
    " saldo_atual, mov_periodo, saldo_ant) VALUES (?,?,?,?,?,?,?)",
    [
        (EMP, "2026-01", CONTA, "AUX", -1000.0, -1000.0,    0.0),
        (EMP, "2026-02", CONTA, "AUX", -2050.0, -1000.0, -1050.0),   # <- salto de 50
        (EMP, "2026-03", CONTA, "AUX", -3050.0, -1000.0, -2050.0),   # <- encadeia certo
        # conta sintética com o mesmo salto: não pode duplicar o achado
        (EMP, "2026-01", "4.1.1.01.02", "SINT", -1000.0, -1000.0,    0.0),
        (EMP, "2026-02", "4.1.1.01.02", "SINT", -2050.0, -1000.0, -1050.0),
        # conta patrimonial: fora do escopo desta tela
        (EMP, "2026-01", "1.1.1.01.01", "CAIXA", 500.0, 500.0,   0.0),
        (EMP, "2026-02", "1.1.1.01.01", "CAIXA", 900.0, 300.0, 600.0),
    ],
)
conn.commit(); conn.close()
ach = detectar_retroativos(EMP)
check("achou exatamente 1 retroativo", len(ach) == 1, f"({[(a['conta_cod'], a['delta']) for a in ach]})")
a = ach[0] if ach else {}
check("aponta o mês a reimportar (jan, não fev)", a.get("competencia") == "2026-01", f"({a.get('competencia')})")
check("aponta o mês que denunciou (fev)", a.get("comp_revela") == "2026-02")
check("delta = -50,00", abs(a.get("delta", 0) + 50.0) < 0.01, f"({a.get('delta')})")
check("ignora conta sintética", all(x["conta_cod"] != "4.1.1.01.02" for x in ach))
check("ignora conta patrimonial", all(not x["conta_cod"].startswith("1.") for x in ach))

print("\n=== 13. mês faltando no meio não vira falso positivo ===")
conn = get_conn()
conn.execute("DELETE FROM balancete WHERE empresa_id=? AND competencia='2026-02'", (EMP,))
conn.commit(); conn.close()
check("sem fev, jan→mar não é comparado", not detectar_retroativos(EMP),
      f"({detectar_retroativos(EMP)})")

print("\n" + ("TODAS AS PROVAS PASSARAM" if ok else "HOUVE FALHA"))
sys.exit(0 if ok else 1)
