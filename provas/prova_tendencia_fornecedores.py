"""
prova_tendencia_fornecedores.py — trava a tendência (▲ aumento / ▼ redução) na
tela de Despesas e Custos por Fornecedor, nos QUATRO níveis das duas visões.

A tela de Receita por Cliente já marcava movimentação atípica e filtrava por
ela; a de fornecedores não tinha nada. Agora tem, e nos dois níveis de cada
visão -- conta e fornecedor dentro dela, fornecedor e conta dentro dele --
porque olhando custo a pergunta nunca é só "que conta subiu", é "quem, dentro
dela, puxou".

Detalhe que a receita não precisava tratar: despesa tem valor NEGATIVO. A
tendência é medida em MAGNITUDE, então "aumento" quer dizer que a linha pesou
mais, não que o número subiu na reta numérica.

Rodar:  DB_PATH=<temp.db> python provas/prova_tendencia_fornecedores.py
"""
import os, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
if not os.environ.get("DB_PATH"):
    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prova_tend.db")

from ingestion import get_conn, criar_schema, seed_empresas                # noqa: E402
from dre_engine import _tendencia, analisar_despesas_fornecedores          # noqa: E402
import app as A                                                            # noqa: E402

EMP    = 1
COMPS  = ["2026-05", "2026-06", "2026-07"]
CONTA1 = "4.1.1.02.03.012"   # SERV ASSESSORIA/CONSULTORIA
CONTA2 = "4.4.1.03.09.001"   # OUTRAS DESPESAS

ok = True
def check(nome, cond, extra=""):
    global ok
    print(("  OK   " if cond else "  FALHA ") + nome + (f"  {extra}" if extra else ""))
    ok = ok and bool(cond)


print("\n=== 1. a régua da tendência ===")
t, p = _tendencia({"2026-05": 10.0, "2026-06": 10.0, "2026-07": 45.0}, COMPS)
check("subiu 350% → aumento", t == "aumento" and p > 300, f"({t}, {p:.0f}%)")
t, p = _tendencia({"2026-05": 20.0, "2026-06": 20.0, "2026-07": 2.0}, COMPS)
check("caiu 90% → redução", t == "reducao" and p < -80, f"({t}, {p:.0f}%)")
t, p = _tendencia({"2026-05": 10.0, "2026-06": 10.0, "2026-07": 11.0}, COMPS)
check("oscilação de 10% não vira alarme", t is None, f"({t}, {p:.0f}%)")
# despesa é negativa: sem magnitude, o sinal inverteria a leitura
t, p = _tendencia({"2026-05": -10.0, "2026-06": -10.0, "2026-07": -45.0}, COMPS)
check("gasto que subiu (valores negativos) → aumento", t == "aumento", f"({t}, {p:.0f}%)")
t, p = _tendencia({"2026-05": -20.0, "2026-06": -20.0, "2026-07": -2.0}, COMPS)
check("gasto que caiu (valores negativos) → redução", t == "reducao", f"({t}, {p:.0f}%)")
t, p = _tendencia({"2026-05": 0.0, "2026-06": 10.0, "2026-07": 10.0}, COMPS)
check("mês zerado no meio não entra na média", t is None, f"({t}, {p:.0f}%)")
t, p = _tendencia({"2026-07": 10.0}, ["2026-07"])
check("um mês só: sem base de comparação", t is None)


def montar():
    conn = get_conn(); criar_schema(conn); seed_empresas(conn)
    conn.execute("DELETE FROM razao WHERE empresa_id=?", (EMP,))
    conn.executemany(
        "INSERT OR REPLACE INTO contas (cod, empresa_id, descricao) VALUES (?,?,?)",
        [(CONTA1, EMP, "SERV ASSESSORIA/CONSULTORIA"), (CONTA2, EMP, "OUTRAS DESPESAS")],
    )
    rows = []
    # ALFA dispara em julho; BETA despenca; GAMA fica igual, em outra conta.
    perfis = [
        ("ALFA CONSULTORIA",  CONTA1, "000000101", [10000, 10000, 45000]),
        ("BETA SERVICOS",     CONTA1, "000000202", [20000, 20000,  2000]),
        ("GAMA MANUTENCAO",   CONTA2, "000000303", [ 5000,  5000,  5000]),
    ]
    for nome, conta, nf, valores in perfis:
        for comp, v in zip(COMPS, valores):
            rows.append((EMP, comp, f"{comp}-10", conta, f"LOTE-{nf}",
                         f"PROV.REF.A NF.{nf} DE {nome}", v, 0, -v))
    conn.executemany(
        "INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento,"
        " historico, debito, credito, valor) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()


print("\n=== 2. visão CONTA: a conta e o fornecedor dentro dela ===")
montar()
a = analisar_despesas_fornecedores(EMP, COMPS)
g1 = next(g for g in a["por_grupo"] if g["id"] == CONTA1)
g2 = next(g for g in a["por_grupo"] if g["id"] == CONTA2)
check("conta com movimento atípico é marcada", g1["tendencia"] == "aumento", f"({g1['tendencia']})")
check("conta estável não é marcada", g2["tendencia"] is None, f"({g2['tendencia']})")
f_alfa = next(f for f in g1["fornecedores"] if "ALFA" in f["nome"])
f_beta = next(f for f in g1["fornecedores"] if "BETA" in f["nome"])
check("fornecedor que disparou: aumento", f_alfa["tendencia"] == "aumento", f"({f_alfa['tendencia']})")
check("fornecedor que despencou: redução", f_beta["tendencia"] == "reducao", f"({f_beta['tendencia']})")

print("\n=== 3. visão FORNECEDOR: o fornecedor e a conta dentro dele ===")
alfa = next(f for f in a["por_fornecedor"] if "ALFA" in f["nome"])
beta = next(f for f in a["por_fornecedor"] if "BETA" in f["nome"])
gama = next(f for f in a["por_fornecedor"] if "GAMA" in f["nome"])
check("ALFA: aumento", alfa["tendencia"] == "aumento", f"({alfa['tendencia']})")
check("BETA: redução",  beta["tendencia"] == "reducao", f"({beta['tendencia']})")
check("GAMA: estável",  gama["tendencia"] is None, f"({gama['tendencia']})")
check("conta dentro do fornecedor também é marcada",
      alfa["grupos"][0]["tendencia"] == "aumento", f"({alfa['grupos'][0]['tendencia']})")
check("as duas visões concordam no mesmo par conta×fornecedor",
      alfa["grupos"][0]["tendencia"] == f_alfa["tendencia"])

print("\n=== 4. a tela entrega o filtro e as marcas ===")
A.app.config["TESTING"] = True
cli = A.app.test_client()
with cli.session_transaction() as sess:
    sess["usuario_logado"] = {"id": 1, "role": "admin", "nome": "T"}
r = cli.get("/despesas/fornecedores/mkb?de=2026-05&ate=2026-07&visao=grupo")
check("página abre", r.status_code == 200, f"({r.status_code})")
h = r.get_data(as_text=True)
check("barra de filtro de tendência", 'data-tend="aumento"' in h and 'data-tend="reducao"' in h)
check("coluna Tend. no cabeçalho", "Tend." in h)
check("ícone de aumento na tabela", "df-trend-up" in h)
check("ícone de redução na tabela", "df-trend-down" in h)
check("linha carrega a própria tendência", 'data-tendencia="aumento"' in h)
check("linha carrega a tendência das filhas", 'data-tend-filhas=' in h)
check("filtro combina texto e tendência", "_bateTend" in h and "filtrarLinhasPivot" in h)

r2 = cli.get("/despesas/fornecedores/mkb?de=2026-05&ate=2026-07&visao=fornecedor")
check("visão por fornecedor também", r2.status_code == 200 and "df-trend-up" in r2.get_data(as_text=True))

print("\n" + ("TODAS AS PROVAS PASSARAM" if ok else "HOUVE FALHA"))
sys.exit(0 if ok else 1)
