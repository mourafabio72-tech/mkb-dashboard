"""Prova do cálculo Orçado x Realizado (orcamento_engine.py), com base sintética e conta feita à mão.

Base (2026):
  centros MKB: 010206911 (ASSESSORIA, Ana, RJ) e 010209804 (FACILITIES, sem coordenador, SP)
  orçado MKB  jan: ROB 1000 (c1) + 500 (c2), DED -100 (c1), CPV_FOLHA -400 (c2)
              fev: ROB 1200 (c1), CPV_FOLHA -400 (c2)
              mar: ROB 900 (c1)                                       (mês sem razão)
  razão MKB   jan: ROB 1100 (c1, '01.02.069.11'), DED -110 (c1), CPV_FOLHA -380 (c2),
                   conta sem linha -50 (c2), ROB 30 sem centro
              fev: ROB 1000 (c1), CPV_FOLHA -420 (c2)
  razão Gnileb jan: ROB 300 sem centro, equivalência patrimonial 200 (4.4.1.06.01.001)

  MKB jan, por linha: ROB 1500 x 1130, DED -100 x -110, ROL 1400 x 1020, CPV_FOLHA -400 x -380,
                      LB 1000 x 640, LL 1000 x 640, Sem linha 0 x -50; total 1000 x 590
  MKB acumulado fev: total jan + fev = (1000 + 800) x (590 + 580) = 1800 x 1170
  Consolidado jan: MKB 1000 x 590 + Gnileb 0 x 500 - equivalência 200 = 1000 x 890
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prova.db")

from ingestion import criar_schema, get_conn, seed_empresas  # noqa: E402
import orcamento_engine as oe  # noqa: E402

falhas = []


def confere(cond, msg):
    print(("ok    " if cond else "FALHA ") + msg)
    if not cond:
        falhas.append(msg)


conn = get_conn()
criar_schema(conn)
seed_empresas(conn)
C1, C2 = "010206911", "010209804"
ROB, DED, FOLHA, SEM, EP = "3.1.1.01.01.001", "3.1.3.01.02.001", "4.1.1.01.02.015", "4.2.1.01.01.001", "4.4.1.06.01.001"
conn.executemany("INSERT INTO centros_custo (empresa_id, codigo, descricao, servico, coordenador, filial, tipo) VALUES (1,?,?,?,?,?,'')",
                 [(C1, "Centro A", "ASSESSORIA", "Ana", "RJ"), (C2, "Centro B", "FACILITIES", "", "SP")])
conn.execute("INSERT INTO orcamento_lotes (empresa_id, ano, usuario, linhas, total) VALUES (1, 2026, 'prova', 0, 0)")
conn.executemany("INSERT INTO orcamento (empresa_id, competencia, conta_cod, centro_custo, valor, lote_id) VALUES (1,?,?,?,?,1)", [
    ("2026-01", ROB, C1, 1000), ("2026-01", ROB, C2, 500), ("2026-01", DED, C1, -100), ("2026-01", FOLHA, C2, -400),
    ("2026-02", ROB, C1, 1200), ("2026-02", FOLHA, C2, -400), ("2026-03", ROB, C1, 900)])
razao = [
    (1, "2026-01", ROB, "01.02.069.11", 1100), (1, "2026-01", DED, "01.02.069.11", -110), (1, "2026-01", FOLHA, "01.02.098.04", -380),
    (1, "2026-01", SEM, "01.02.098.04", -50), (1, "2026-01", ROB, None, 30),
    (1, "2026-02", ROB, "01.02.069.11", 1000), (1, "2026-02", FOLHA, "01.02.098.04", -420),
    (2, "2026-01", ROB, None, 300), (2, "2026-01", EP, None, 200)]
for n, (eid, comp, conta, centro, valor) in enumerate(razao):
    conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, centro_custo, valor) VALUES (?,?,?,?,?,?,?)",
                 (eid, comp, comp + "-10", conta, f"D{n}", centro, valor))
conn.commit()


def calc(**k):
    base = dict(empresa="mkb", ano=2026, mes=1, modo="mes", abrir_por="linha")
    base.update(k)
    return oe.calcular(conn, **base)


def linha(r, lid):
    return next((l for l in r["linhas"] if l.get("id") == lid), None)


def par(l):
    return (l["orcado"], l["realizado"])


# 1. por linha da DRE
r = calc()
confere(par(linha(r, "ROB")) == (1500, 1130), "linha: ROB 1500 x 1130 (centro com ponto casa sem ponto; sem centro entra)")
confere(par(linha(r, "DED")) == (-100, -110) and par(linha(r, "ROL")) == (1400, 1020), "linha: DED e ROL calculada")
confere(par(linha(r, "CPV_FOLHA")) == (-400, -380) and par(linha(r, "LB")) == (1000, 640), "linha: folha e lucro bruto")
confere(par(linha(r, "LL")) == (1000, 640), "linha: resultado líquido pela fórmula da DRE gerencial")
confere(par(linha(r, "SEM_LINHA")) == (0, -50), "linha: conta sem grupo vai para Sem linha na DRE")
confere(par(r["total"]) == (1000, 590) and r["total"]["variacao"] == -410 and r["total"]["pct"] == 59.0, "linha: total, variação e %")
confere(not any(l.get("id") == "EBITDA" for l in r["linhas"]), "linha: sem EBITDA")
confere(r["meses_sem_realizado"] == [] and r["sem_orcamento"] is False, "linha: janeiro tem razão e orçamento")

# 2. toda abertura soma o mesmo total
for dim in ("servico", "coordenador", "filial", "centro"):
    t = calc(abrir_por=dim)["total"]
    confere(par(t) == (1000, 590), f"abertura: por {dim} soma o mesmo total")
r = calc(abrir_por="servico")
rot = {l["rotulo"]: par(l) for l in r["linhas"]}
confere(rot.get("ASSESSORIA") == (900, 990) and rot.get("FACILITIES") == (100, -430) and rot.get(oe.SEM_CENTRO) == (0, 30),
        "abertura: por serviço com a conta à mão (sem centro à parte)")
r = calc(abrir_por="coordenador")
confere({l["rotulo"] for l in r["linhas"]} == {"Ana", oe.SEM_VALOR, oe.SEM_CENTRO}, "abertura: coordenador vazio vira Não informado")
r = calc(abrir_por="centro", linha="ROB")
confere(par(r["total"]) == (1500, 1130), "abertura: por centro só da linha ROB = linha ROB")
r = calc(abrir_por="centro", linha="ROL")
confere(par(r["total"]) == (1400, 1020), "abertura: por centro de um subtotal (ROL)")

# 3. filtros
r = calc(filtros={"servico": ["ASSESSORIA"]})
confere(par(r["total"]) == (900, 990), "filtro: só ASSESSORIA")
r = calc(filtros={"filial": ["SP"], "centro": [C2]})
confere(par(r["total"]) == (100, -430), "filtro: filial e centro juntos")
r = calc(filtros={"servico": [oe.SEM_CENTRO]})
confere(par(r["total"]) == (0, 30), "filtro: Sem centro de custo")

# 4. acumulado e mês sem razão
m1, m2 = calc()["total"], calc(mes=2)["total"]
ac = calc(mes=2, modo="acumulado")
confere(par(ac["total"]) == (m1["orcado"] + m2["orcado"], m1["realizado"] + m2["realizado"]) == (1800, 1170), "acumulado: soma dos meses")
ac3 = calc(mes=3, modo="acumulado")
confere(ac3["meses_sem_realizado"] == ["2026-03"] and ac3["total"]["orcado"] == 2700, "acumulado: março sem razão marcado, orçado entra")
confere(calc(mes=3)["meses_sem_realizado"] == ["2026-03"], "mês: sem razão marcado, não zero calado")

# 5. Gnileb e consolidado
g = calc(empresa="gnileb")
confere(g["sem_orcamento"] is True and par(g["total"]) == (0, 500), "gnileb: sem orçamento, realizado do razão (EP incluída)")
cons = calc(empresa="consolidado")
confere(par(cons["total"]) == (1000, 890) and cons["eliminado_equivalencia"] == -200, "consolidado: MKB + Gnileb - equivalência patrimonial")
confere(par(linha(cons, "OUTROS_OP")) == (0, 0), "consolidado: equivalência fora de Outros Resultados")
confere(par(calc(empresa="consolidado", abrir_por="centro")["total"]) == (1000, 890), "consolidado: abertura soma o mesmo total")
confere(dict((l["rotulo"], par(l)) for l in calc(empresa="consolidado", abrir_por="filial")["linhas"]).get(oe.SEM_CENTRO) == (0, 330),
        "consolidado: Gnileb (sem centro) junto do sem centro da MKB")

# 5b. furos achados pelo verificador (2026-10-20), em base própria de abril e maio
conn.executemany("INSERT INTO orcamento (empresa_id, competencia, conta_cod, centro_custo, valor, lote_id) VALUES (1,?,?,?,?,1)", [
    ("2026-04", ROB, C1, 0.3), ("2026-04", DED, C1, -0.1), ("2026-04", DED, C1 + " ", -0.2),   # ROL = resíduo de 5e-17
    ("2026-04", "1.1.1.01.01.001", C1, 999), ("2026-04", "2.1.1.01.01.001", C1, 7),       # contas patrimoniais
    ("2026-05", ROB, "01.02.069.11", 40)])                                                   # centro com ponto no orçado
for n, (comp, conta, valor) in enumerate([("2026-04", ROB, 100), ("2026-05", " " + ROB, 77), ("2026-05", ROB + "  ", 11)]):
    conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, centro_custo, valor) VALUES (1,?,?,?,?,?,?)",
                 (comp, comp + "-10", conta, f"F{n}", "01.02.069.11", valor))
conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, centro_custo, valor) VALUES (2,'2026-06','2026-06-10',?, 'G1', NULL, 5)", (ROB,))
conn.commit()
abr = calc(mes=4)
confere(linha(abr, "ROL")["pct"] is None and abr["total"]["orcado"] == 0, "furo: resíduo de ponto flutuante não vira % absurdo")
confere(linha(abr, "SEM_LINHA") is None, "furo: conta patrimonial (1 e 2) fora do orçado")
mai = calc(mes=5, abrir_por="centro")
confere([(l["rotulo"].split(" ")[0], l["orcado"], l["realizado"]) for l in mai["linhas"]] == [(C1, 40, 88)],
        "furo: centro com ponto no orçado casa; conta com espaço à esquerda entra no realizado")
jun = calc(empresa="consolidado", mes=6)
confere(jun["meses_sem_realizado"] == ["2026-06"] and jun["sem_razao_por_empresa"] == {"MKB": ["2026-06"]},
        "furo: consolidado marca o mês quando falta o razão de uma das empresas")
for k in (dict(filtros=[1]), dict(filtros="abc"), dict(empresa=["mkb"]), dict(abrir_por=["linha"]), dict(linha=["ROB"])):
    try:
        calc(**k)
        confere(False, f"furo: {k} devia recusar")
    except ValueError:
        confere(True, f"furo: {k} recusado com ValueError")

# 6. entrada inválida
for k in (dict(empresa="xyz"), dict(ano=1999), dict(ano="2026"), dict(mes=13), dict(mes=True), dict(modo="ano"),
          dict(abrir_por="conta"), dict(linha="DROP"), dict(filtros={"conta": ["x"]}), dict(filtros={"servico": "A"}),
          dict(filtros={"servico": [1]})):
    try:
        calc(**k)
        confere(False, f"inválido: {k} devia recusar")
    except ValueError:
        confere(True, f"inválido: {k} recusado")

# 7. SQL só parametrizado
import ast  # noqa: E402
arvore = ast.parse((RAIZ / "orcamento_engine.py").read_text(encoding="utf-8"))
interpolados = []
for no in ast.walk(arvore):
    if isinstance(no, ast.JoinedStr):
        texto = "".join(p.value for p in no.values if isinstance(p, ast.Constant))
        if any(palavra in texto.upper() for palavra in ("SELECT", " WHERE ", "INSERT", "DELETE", "UPDATE ")):
            interpolados += [ast.unparse(p.value) for p in no.values if isinstance(p, ast.FormattedValue)]
confere(interpolados and set(interpolados) == {"marcas"}, f"sql: f-string de SQL só interpola os marcadores ({len(interpolados)} achados)")
atribuicoes = [ast.unparse(n.value) for n in ast.walk(arvore) if isinstance(n, ast.Assign)
               and any(isinstance(a, ast.Name) and a.id == "marcas" for a in n.targets)]
confere(atribuicoes == ["','.join('?' * len(ids))"], "sql: marcas só nasce de '?' repetido pelo número de empresas")

conn.close()
print()
print(f"{len(falhas)} falha(s)" if falhas else "prova_orcamento_calculo: tudo ok")
sys.exit(1 if falhas else 0)
