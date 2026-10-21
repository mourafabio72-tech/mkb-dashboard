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

# 5a. árvore da DRE (Fase 6): mesmas contas, organizadas em bloco > grupo do 5º nível > analítica, por mês
conn.execute("INSERT INTO contas (cod, empresa_id, descricao) VALUES ('3.1.1.01.01', 1, 'RECEITA BRUTA DE SERVICOS')")
conn.execute("INSERT INTO contas (cod, empresa_id, descricao) VALUES (?, 1, 'RECEITA - SERVICOS')", (ROB,))
conn.commit()
arv = oe.arvore(conn, "mkb", 2026, 1, 3)
porid = {l["id"]: l for l in arv["linhas"]}
confere(arv["linhas"][0]["id"] == "TOTAL" and [l["nivel"] for l in arv["linhas"]][:3] == [0, 1, 2], "árvore: Resultado no topo, depois bloco e grupo")
confere([m for m in arv["total"]["meses"]] == [[1000, 590], [800, 580], [900, None]], "árvore: total por mês = cálculo da Fase 3; março sem razão = sem dado, não zero")
confere(arv["total"]["orcado_comparavel"] == 1800 and arv["total"]["media_orcado_comparavel"] == 900,
        "árvore: acumulado compara com o orçado só dos meses com razão (1800, não 2700)")
pais_ok = all(abs(sum(f["meses"][i][k] or 0 for f in arv["linhas"] if f["pai"] == l["id"]) - (l["meses"][i][k] or 0)) < 1e-9
              for l in arv["linhas"] if any(f["pai"] == l["id"] for f in arv["linhas"]) for i in range(3) for k in (0, 1))
confere(pais_ok, "árvore: cada pai é a soma exata (em centavos) dos filhos, mês a mês")
for mes, esperado in ((1, (1000, 590)), (2, (800, 580))):
    confere(tuple(oe.arvore(conn, "mkb", 2026, mes, mes)["total"]["acumulado"]) == esperado == par(calc(mes=mes)["total"]),
            f"árvore: mês {mes} sozinho = calcular")
confere(arv["total"]["acumulado"] == [2700, 1170], "árvore: acumulado = soma dos meses")
confere(arv["total"]["media"] == [900, 585], "árvore: média do orçado ÷ 3 meses, do realizado ÷ 2 meses com razão")
rec = porid["RECEITA"]
confere(rec["meses"][0] == [1400, 1020] and rec["rotulo"] == "Receita", "árvore: bloco Receita = ROB + deduções (jan 1400 x 1020)")
grupos = [l for l in arv["linhas"] if l["pai"] == "RECEITA"]
for g in grupos:
    filhos = [l for l in arv["linhas"] if l["pai"] == g["id"]]
    confere(filhos and all(abs(sum(f["acumulado"][i] for f in filhos) - g["acumulado"][i]) < .01 for i in (0, 1)),
            f"árvore: grupo {g['codigo']} = soma das analíticas")
confere(porid["g:RECEITA:3.1.1.01.01"]["rotulo"] == "RECEITA BRUTA DE SERVICOS" and porid["c:" + ROB]["rotulo"] == "RECEITA - SERVICOS",
        "árvore: descrição do grupo e da conta pela tabela contas")
confere(porid["g:CUSTOS:4.1.1.01.02"]["rotulo"] == "Grupo 4.1.1.01.02", "árvore: grupo sem descrição vira Grupo <código>")
confere(arv["meses_sem_realizado"] == ["2026-03"] and arv["realizado_ate"] == "28/02/2026", "árvore: realizado disponível até o fim de fevereiro")
cons = oe.arvore(conn, "consolidado", 2026, 1, 1)
confere(tuple(cons["total"]["acumulado"]) == (1000, 890) and cons["eliminado_equivalencia"] == -200, "árvore: consolidado sem a equivalência")
confere(tuple(oe.arvore(conn, "mkb", 2026, 1, 1, {"servico": ["ASSESSORIA"]})["total"]["acumulado"]) == (900, 990), "árvore: filtro de serviço")
for k in ((3, 1), (0, 2), (1, 13), (True, 2)):
    try:
        oe.arvore(conn, "mkb", 2026, *k)
        confere(False, f"árvore: meses {k} deviam recusar")
    except ValueError:
        confere(True, f"árvore: meses {k} recusados")

# 5c. Fase 7: abertura por dimensão com Receita, Custo e Despesa e MC (D8), filtros de conta e lançamentos
dim = oe.por_dimensao(conn, "mkb", 2026, 1, 1, "servico")
porrot = {l["rotulo"]: l for l in dim["linhas"]}
confere(porrot["ASSESSORIA"]["receita"] == [900, 990] and porrot["ASSESSORIA"]["mc"] == [900, 990], "dimensão: ASSESSORIA receita líquida 900 x 990")
confere(porrot["FACILITIES"]["custo_despesa"] == [-400, -380] and porrot["FACILITIES"]["mc"] == [100, -380],
        "dimensão: FACILITIES MC = 500 - 400 e 0 - 380 (conta sem linha fora da MC)")
confere(all(l["mc"] == [round(l["receita"][i] + l["custo_despesa"][i], 2) for i in (0, 1)] for l in dim["linhas"] + [dim["total"]]),
        "dimensão: MC = Receita + Custo e Despesa em toda linha")
confere(dim["total"]["mc"] == [1000, 640] and dim["total"]["variacao"] == -360 and dim["total"]["mc_pct"] == [71.4, 62.7],
        "dimensão: total MC 1000 x 640, variação -360, MC % sobre a receita líquida")
for d in ("coordenador", "filial", "centro"):
    confere(oe.por_dimensao(conn, "mkb", 2026, 1, 1, d)["total"]["mc"] == [1000, 640], f"dimensão: por {d} soma a mesma MC")
for d in ("servico", "coordenador", "filial", "centro"):  # drilldown: a chave da linha, como filtro, isola a linha
    for l in oe.por_dimensao(conn, "mkb", 2026, 1, 1, d)["linhas"]:
        sozinha = oe.por_dimensao(conn, "mkb", 2026, 1, 1, d, {d: [l["chave"]]})
        confere(len(sozinha["linhas"]) == 1 and sozinha["total"]["mc"] == l["mc"],
                f"drilldown: {d} = {l['chave']!r} isola a linha e a MC dela")
tri = oe.por_dimensao(conn, "mkb", 2026, 1, 3, "centro")
confere(tri["meses_considerados"] == ["2026-01", "2026-02"] and tri["total"]["mc"][0] == 1800,
        "dimensão: com março sem razão, o orçado considera só jan e fev")
confere(oe.por_dimensao(conn, "mkb", 2026, 3, 3, "centro")["total"]["mc"][1] is None, "dimensão: período sem razão = realizado sem dado")
confere(oe.por_dimensao(conn, "consolidado", 2026, 1, 1, "centro")["total"]["mc"] == [1000, 940],
        "dimensão: consolidado soma a receita da Gnileb (300) e não a equivalência")
filtro_conta = oe.arvore(conn, "mkb", 2026, 1, 1, {"conta": ["3."]})
confere(filtro_conta["total"]["acumulado"] == [1400, 1020], "filtro de conta: começo '3.' fica só com a receita")
filtro_desc = oe.arvore(conn, "mkb", 2026, 1, 1, {"descricao": ["servicos"]})
confere(filtro_desc["total"]["acumulado"] == [1500, 1130], "filtro de descrição: 'servicos' acha RECEITA - SERVICOS, sem acento e sem caixa")
confere(oe.por_dimensao(conn, "mkb", 2026, 1, 1, "centro", {"conta": ["4."]})["total"]["mc"] == [-400, -380], "filtro de conta vale na abertura")
lanc = oe.lancamentos(conn, "mkb", 2026, 1, 2, ROB)
confere(lanc["total"] == 2130 and lanc["quantidade"] == 3 and lanc["descricao"] == "RECEITA - SERVICOS",
        "lançamentos: ROB em jan e fev somam o realizado (1100 + 30 + 1000)")
confere(oe.lancamentos(conn, "mkb", 2026, 1, 1, ROB, {"servico": ["ASSESSORIA"]})["total"] == 1100, "lançamentos: filtro de serviço")
confere(oe.lancamentos(conn, "consolidado", 2026, 1, 1, EP)["quantidade"] == 0, "lançamentos: equivalência fora no consolidado")
confere(oe.lancamentos(conn, "gnileb", 2026, 1, 1, EP)["total"] == 200, "lançamentos: equivalência aparece na Gnileb sozinha")
for k in (dict(conta=""), dict(conta="x" * 41), dict(mes_ini=2, mes_fim=1)):
    base = dict(empresa="mkb", ano=2026, mes_ini=1, mes_fim=1, conta=ROB); base.update(k)
    try:
        oe.lancamentos(conn, **base)
        confere(False, f"lançamentos: {k} devia recusar")
    except ValueError:
        confere(True, f"lançamentos: {k} recusado")
for k in (dict(abrir_por="linha"), dict(abrir_por="conta"), dict(filtros={"conta": "3"})):
    base = dict(empresa="mkb", ano=2026, mes_ini=1, mes_fim=1, abrir_por="centro"); base.update(k)
    try:
        oe.por_dimensao(conn, **base)
        confere(False, f"dimensão: {k} devia recusar")
    except ValueError:
        confere(True, f"dimensão: {k} recusado")

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
          dict(abrir_por="conta"), dict(linha="DROP"), dict(filtros={"cnpj": ["x"]}), dict(filtros={"servico": "A"}),
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
confere(atribuicoes.count("','.join('?' * len(ids))") == 1 and set(atribuicoes) <= {"','.join('?' * len(ids))", "per['marcas']", "','.join('?' * len(lote))"},
        "sql: marcas só nasce de '?' repetido pelo número de empresas (em _periodo, e repassado por per['marcas'])")

# 5d. furos do verificador de ataque da Fase 7 (2026-10-21): junho próprio, sem mexer nos meses de cima
DADM = "4.4.1.01.01.001"
conn.execute("INSERT INTO contas (cod, empresa_id, descricao) VALUES (?, 1, 'PRÓ-LABORE ADMINISTRAÇÃO')", (DADM,))
conn.executemany("INSERT INTO orcamento (empresa_id, competencia, conta_cod, centro_custo, valor, lote_id) VALUES (1,?,?,?,?,1)",
                 [("2026-06", ROB, C1, 100), ("2026-06", DADM, C1, -30)])
conn.executemany("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, centro_custo, valor) VALUES (1,?,?,?,?,?,?)",
                 [("2026-06", "2026-06-10", ROB, "J1", C1, 120), ("2026-06", "2026-06-10", DADM, "J2", C1, -40)])
conn.commit()
jun = {l["rotulo"]: l for l in oe.por_dimensao(conn, "mkb", 2026, 6, 6, "servico")["linhas"]}
confere(jun["ASSESSORIA"]["custo_despesa"] == [-30, -40] and jun["ASSESSORIA"]["mc"] == [70, 80],
        "dimensão: despesa administrativa (DADM_) entra em Custo e despesa")
confere(oe.arvore(conn, "mkb", 2026, 6, 6, {"descricao": ["administracao"]})["total"]["acumulado"] == [-30, -40],
        "filtro de descrição: 'administracao' acha 'PRÓ-LABORE ADMINISTRAÇÃO' (tira o acento dos dois lados)")
confere(oe.arvore(conn, "mkb", 2026, 6, 6, {"conta": ["1.01"]})["total"]["acumulado"] == [0, 0],
        "filtro de conta: '1.01' é começo do código, não pedaço do meio")
confere(linha(calc(filtros={"conta": ["4."]}), "ROB")["realizado"] == 0 and linha(calc(), "ROB")["realizado"] != 0,
        "filtro de conta vale também no calcular")
teto = oe.MAX_LANCAMENTOS
oe.MAX_LANCAMENTOS = 1
try:
    corte = oe.lancamentos(conn, "mkb", 2026, 1, 2, ROB)
finally:
    oe.MAX_LANCAMENTOS = teto
confere(len(corte["linhas"]) == 1 and corte["cortado"] and corte["quantidade"] == 3 and corte["total"] == 2130,
        "lançamentos: acima do teto corta as linhas, avisa e o total soma todas")
for conta in ("1.1.1", "2.1"):
    try:
        oe.lancamentos(conn, "mkb", 2026, 1, 1, conta)
        confere(False, f"lançamentos: conta {conta} fora do resultado devia recusar")
    except ValueError:
        confere(True, f"lançamentos: conta {conta} fora do resultado recusada")

# 5e. Fase 8: dashboard = tabelas (indicadores, mensal e desvios saem da árvore e da abertura)
for emp, de, ate in (("mkb", 1, 2), ("mkb", 1, 3), ("consolidado", 1, 1), ("mkb", 1, 6)):
    pn = oe.painel(conn, emp, 2026, de, ate)
    tab = oe.por_dimensao(conn, emp, 2026, de, ate, "servico")["total"]
    arv_t = oe.arvore(conn, emp, 2026, de, ate)["total"]
    ind = pn["indicadores"]
    confere([ind["mc"]["orcado"], ind["mc"]["realizado"]] == tab["mc"] and [ind["receita"]["orcado"], ind["receita"]["realizado"]] == tab["receita"]
            and [ind["custo_despesa"]["orcado"], ind["custo_despesa"]["realizado"]] == tab["custo_despesa"]
            and [ind["mc_pct"]["orcado"], ind["mc_pct"]["realizado"]] == tab["mc_pct"],
            f"painel {emp} {de}-{ate}: Receita, Custo e despesa, MC e MC % = tabela por dimensão")
    confere(ind["resultado"]["realizado"] == arv_t["acumulado"][1] and ind["resultado"]["orcado"] == arv_t["orcado_comparavel"]
            and pn["mensal"]["resultado"] == arv_t["meses"], f"painel {emp} {de}-{ate}: Resultado e Resultado por mês = árvore")
    com = [i for i, c in enumerate(pn["competencias"]) if c in pn["meses_considerados"]]
    confere(round(sum(pn["mensal"]["mc"][i][0] for i in com), 2) == ind["mc"]["orcado"] and
            (ind["mc"]["realizado"] is None or round(sum(pn["mensal"]["mc"][i][1] for i in com), 2) == ind["mc"]["realizado"]),
            f"painel {emp} {de}-{ate}: MC por mês soma a MC do período (meses com razão)")
    dc = [abs(d["variacao"]) for d in pn["desvios_centro"]]
    confere(dc == sorted(dc, reverse=True) and len(dc) <= oe.MAX_DESVIOS and
            all(d["variacao"] == round(d["realizado"] - d["orcado"], 2) for d in pn["desvios_conta"]),
            f"painel {emp} {de}-{ate}: desvios do maior para o menor, variação = realizado - orçado")
pn = oe.painel(conn, "mkb", 2026, 1, 3)
confere(pn["mensal"]["mc"][2][1] is None and pn["mensal"]["resultado"][2][1] is None, "painel: mês sem razão sai sem dado no gráfico, não zero")
semr = oe.painel(conn, "mkb", 2026, 3, 3)["indicadores"]
confere(semr["mc"]["realizado"] is None and semr["mc"]["variacao"] is None and semr["resultado"]["variacao"] is None,
        "painel: período sem razão = realizado e variação sem dado")
pn = oe.painel(conn, "mkb", 2026, 1, 6)
ind = pn["indicadores"]
confere(all(ind[k]["variacao"] == round(ind[k]["realizado"] - ind[k]["orcado"], 2) for k in ("receita", "custo_despesa", "mc", "resultado"))
        and ind["mc_pct"]["variacao"] == round(ind["mc_pct"]["realizado"] - ind["mc_pct"]["orcado"], 1), "painel: variação = realizado - orçado (sinal)")
dk = [abs(d["variacao"]) for d in pn["desvios_conta"]]
confere(dk == sorted(dk, reverse=True) and all(d["variacao"] for d in pn["desvios_conta"]) and all(d["codigo"].count(".") >= 5 for d in pn["desvios_conta"])
        and pn["total_desvios_conta"] == len(pn["desvios_conta"]), "painel: desvios por conta da analítica, maior primeiro, sem desvio zero")
confere(pn["orcado_periodo"] == oe.arvore(conn, "mkb", 2026, 1, 6)["total"]["acumulado"][0], "painel: orçado do período inteiro = árvore")
teto = oe.MAX_DESVIOS
oe.MAX_DESVIOS = 1
try:
    corte = oe.painel(conn, "mkb", 2026, 1, 6)
finally:
    oe.MAX_DESVIOS = teto
confere(len(corte["desvios_conta"]) == 1 and corte["total_desvios_conta"] > 1 and len(corte["desvios_centro"]) == 1,
        "painel: corte nos maiores desvios, com o total para declarar")
f = {"servico": ["ASSESSORIA"]}
pf, af = oe.painel(conn, "mkb", 2026, 1, 2, f), oe.arvore(conn, "mkb", 2026, 1, 2, f)["total"]
confere(pf["mensal"]["resultado"] == af["meses"] and pf["indicadores"]["resultado"]["realizado"] == af["acumulado"][1]
        and af["acumulado"] != oe.arvore(conn, "mkb", 2026, 1, 2)["total"]["acumulado"], "painel: filtro vale no Resultado e no mensal")
confere(oe.painel(conn, "mkb", 2026, 3, 3)["indicadores"]["receita"]["realizado"] is None, "painel: receita sem razão = sem dado, não zero")
confere(oe.painel(conn, "mkb", 2026, 1, 1, {"servico": ["ASSESSORIA"]})["indicadores"]["mc"]["realizado"] ==
        oe.por_dimensao(conn, "mkb", 2026, 1, 1, "servico", {"servico": ["ASSESSORIA"]})["total"]["mc"][1], "painel: filtros valem")

conn.close()
print()
print(f"{len(falhas)} falha(s)" if falhas else "prova_orcamento_calculo: tudo ok")
sys.exit(1 if falhas else 0)
