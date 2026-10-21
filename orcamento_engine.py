"""
orcamento_engine.py — Orçado x Realizado (Fase 3 do trabalho Orçamento).

  calcular(conn, empresa, ano, mes, modo, abrir_por, filtros, linha) -> dict

- Orçado: tabela `orcamento` (Rel_OrcRel importado). Realizado: tabela `razao`, contas 3 e 4,
  centro sem ponto. Os dois casam por mês + conta + centro, no sinal do razão (crédito menos débito).
- Linhas: as da DRE gerencial do FinHub, pela mesma `classificar_conta` e as mesmas fórmulas
  (_aplicar_calc_ger). Conta sem grupo no de-para vai para "Sem linha na DRE".
- Consolidado (D5/D6): soma MKB e Gnileb, centro de mesmo código é o mesmo centro, e elimina só a
  Equivalência Patrimonial da Gnileb (CONTAS_EP), igual à DRE consolidada.
- Gnileb (D7): sem orçamento por enquanto, e o razão dela não tem centro de custo.
- Mês sem razão importado não tem realizado: sai em `meses_sem_realizado`, nunca como zero.

O chamador decide quais empresas a sessão enxerga; aqui só se aceita a chave já validada.
"""

from collections import defaultdict

from config import EMPRESAS
from dre_engine import (CONTAS_EP, DRE_META_GERENCIAL, _GER_GRUPOS_DIRETOS,
                        _aplicar_calc_ger, classificar_conta)

MODOS = ("mes", "acumulado")
DIMENSOES = {"linha": "Linha da DRE", "servico": "Serviço", "coordenador": "Coordenador",
             "filial": "Filial", "centro": "Centro de custo"}
FILTROS = ("servico", "coordenador", "filial", "centro")
FILTROS_CONTA = ("conta", "descricao")  # conta: código ou o começo dele; descrição: contém, sem acento
SEM_CENTRO = "Sem centro de custo"
SEM_VALOR = "Não informado"
SEM_LINHA = ("SEM_LINHA", "Sem linha na DRE")

# Grupo do de-para -> linha da DRE gerencial (mesma soma de calcular_dre_gerencial)
_GRUPO_PARA_LINHA = {"ROB": "ROB", "DED_ABAT": "DED", "DED_IMPOS": "DED", "ENC_DESP": "ENC_FIN",
                     "ENC_REC": "ENC_FIN", "OUTROS_OP": "OUTROS_OP", "IRPJ_CSLL": "IRPJ_CSLL"}
_GRUPO_PARA_LINHA.update({g: g for g in _GER_GRUPOS_DIRETOS})
_BASE_GER = ["ROB", "DED", "ENC_FIN", "OUTROS_OP", "IRPJ_CSLL"] + list(_GER_GRUPOS_DIRETOS)
LINHAS = [(lid, rotulo, tipo) for lid, rotulo, tipo, _ in DRE_META_GERENCIAL if lid != "EBITDA"]
IDS_LINHA = {lid for lid, _, _ in LINHAS} | {SEM_LINHA[0]}


def linha_da_conta(conta: str) -> str:
    return _GRUPO_PARA_LINHA.get(classificar_conta(conta), SEM_LINHA[0])


def _validar(empresa, ano, mes, modo, abrir_por, filtros, linha):
    if not all(isinstance(v, str) for v in (empresa, modo, abrir_por)) or not (linha is None or isinstance(linha, str)):
        raise ValueError("Parâmetro inválido.")
    if filtros is not None and not isinstance(filtros, dict):
        raise ValueError("Filtro inválido.")
    if empresa not in EMPRESAS and empresa != "consolidado":
        raise ValueError("Empresa inválida.")
    if isinstance(ano, bool) or not isinstance(ano, int) or not 2000 <= ano <= 2100:
        raise ValueError("Ano inválido.")
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise ValueError("Mês inválido.")
    if modo not in MODOS:
        raise ValueError("Escolha No mês ou Acumulado.")
    if abrir_por not in DIMENSOES:
        raise ValueError("Abertura inválida.")
    if linha is not None and linha not in IDS_LINHA:
        raise ValueError("Linha da DRE inválida.")
    for chave, valores in (filtros or {}).items():
        if chave not in FILTROS + FILTROS_CONTA or not isinstance(valores, (list, tuple, set)):
            raise ValueError("Filtro inválido.")
        if any(not isinstance(v, str) or len(v) > 120 for v in valores):
            raise ValueError("Filtro inválido.")


def _centros(conn, empresa_ids):
    """codigo -> {servico, coordenador, filial, descricao}. No consolidado, o mesmo código é o
    mesmo centro (D5): vale o cadastro da primeira empresa da lista (MKB)."""
    cad = {}
    for eid in empresa_ids:
        for codigo, desc, servico, coord, filial in conn.execute(
                "SELECT codigo, descricao, servico, coordenador, filial FROM centros_custo WHERE empresa_id = ?", (eid,)):
            cad.setdefault(codigo, dict(descricao=desc, servico=servico, coordenador=coord, filial=filial))
    return cad


def _rotulo(dim, centro, cad):
    if dim == "linha":
        return None
    if not centro:
        return SEM_CENTRO
    info = cad.get(centro)
    if dim == "centro":
        return f"{centro} · {info['descricao']}" if info and info["descricao"] != centro else centro
    return (info or {}).get(dim) or SEM_VALOR


def _sem_acento(texto) -> str:
    import unicodedata
    return unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode().lower()


def _passa_conta(filtros, conta, descr) -> bool:
    for valor in (filtros or {}).get("conta") or []:
        if not conta.startswith(valor.strip()):
            return False
    for valor in (filtros or {}).get("descricao") or []:
        if _sem_acento(valor).strip() not in _sem_acento(descr.get(conta, "")):
            return False
    return True


def _passa(filtros, centro, cad):
    for chave, valores in (filtros or {}).items():
        if not valores or chave in FILTROS_CONTA:
            continue
        valor = centro if chave == "centro" else ((cad.get(centro) or {}).get(chave) or (SEM_VALOR if centro else SEM_CENTRO))
        if (valor or SEM_CENTRO) not in valores:
            return False
    return True


def _periodo(conn, empresa, ano, mes_ini, mes_fim):
    """Empresas, meses e marcas do período; mês sem razão de qualquer empresa sai em sem_razao."""
    consolidado = empresa == "consolidado"
    chaves = ["mkb", "gnileb"] if consolidado else [empresa]
    ids = [EMPRESAS[k]["id"] for k in chaves]
    meses = [f"{ano}-{m:02d}" for m in range(mes_ini, mes_fim + 1)]
    marcas = ",".join("?" * len(ids))
    com_razao = {(e, c) for e, c in conn.execute(
        f"SELECT DISTINCT empresa_id, competencia FROM razao WHERE empresa_id IN ({marcas}) AND competencia BETWEEN ? AND ?",
        (*ids, meses[0], meses[-1]))}
    # no consolidado, o mês fica sem realizado se faltar o razão de QUALQUER das empresas
    sem_razao = {EMPRESAS[k]["sigla"]: [c for c in meses if (EMPRESAS[k]["id"], c) not in com_razao] for k in chaves}
    return dict(consolidado=consolidado, chaves=chaves, ids=ids, meses=meses, marcas=marcas, sem_razao=sem_razao)


def _lancamentos(conn, per, eliminado: list):
    """(0 orçado | 1 realizado, empresa, mês, conta, centro, valor), contas de resultado, conta sem espaço e
    centro sem ponto. No consolidado, a equivalência patrimonial da Gnileb sai e soma em eliminado[0]."""
    gnileb_id = EMPRESAS["gnileb"]["id"]
    marcas, ids = per["marcas"], per["ids"]
    consultas = (
        # as duas consultas com a mesma regra: só contas de resultado (3 e 4), conta sem espaço, centro sem ponto
        (0, f"""SELECT empresa_id, competencia, trim(conta_cod), replace(trim(COALESCE(centro_custo, '')), '.', ''), SUM(valor)
                FROM orcamento WHERE empresa_id IN ({marcas}) AND competencia BETWEEN ? AND ?
                  AND (trim(conta_cod) LIKE '3%' OR trim(conta_cod) LIKE '4%')
                GROUP BY 1, 2, 3, 4"""),
        (1, f"""SELECT empresa_id, competencia, trim(conta_cod), replace(trim(COALESCE(centro_custo, '')), '.', ''), SUM(valor)
                FROM razao WHERE empresa_id IN ({marcas}) AND competencia BETWEEN ? AND ?
                  AND (trim(conta_cod) LIKE '3%' OR trim(conta_cod) LIKE '4%')
                GROUP BY 1, 2, 3, 4"""),
    )
    for indice, sql in consultas:
        for eid, comp, conta, centro, valor in conn.execute(sql, (*ids, per["meses"][0], per["meses"][-1])):
            conta, centro = (conta or "").strip(), (centro or "").strip()
            if per["consolidado"] and eid == gnileb_id and conta in CONTAS_EP:
                eliminado[0] += valor or 0.0
                continue
            yield indice, eid, comp, conta, centro, round(valor or 0.0, 2)  # em centavos: árvore e cálculo somam igual


def _filtradas(conn, per, filtros, eliminado):
    """_lancamentos com os filtros de conta e de descrição aplicados (a descrição vem da tabela contas)."""
    linhas = list(_lancamentos(conn, per, eliminado))
    if not (filtros or {}).get("conta") and not (filtros or {}).get("descricao"):
        return linhas
    descr = _descricoes(conn, per["ids"], {l[3] for l in linhas}) if (filtros or {}).get("descricao") else {}
    return [l for l in linhas if _passa_conta(filtros, l[3], descr)]


def _meta(conn, empresa, ano, per, eliminado):
    marcas = per["marcas"]
    return dict(
        meses_sem_realizado=[c for c in per["meses"] if any(c in f for f in per["sem_razao"].values())],
        sem_razao_por_empresa={sigla: f for sigla, f in per["sem_razao"].items() if f},
        sem_orcamento=not conn.execute(
            f"SELECT 1 FROM orcamento WHERE empresa_id IN ({marcas}) AND substr(competencia, 1, 4) = ? LIMIT 1",
            (*per["ids"], str(ano))).fetchone(),
        eliminado_equivalencia=round(-eliminado[0], 2) if per["consolidado"] else 0.0)


def calcular(conn, empresa: str, ano: int, mes: int, modo: str = "mes", abrir_por: str = "linha",
             filtros: dict | None = None, linha: str | None = None, mes_ini: int | None = None) -> dict:
    """Uma coluna. O período é mes_ini..mes (quando mes_ini vem), ou o mês, ou o acumulado do ano (modo)."""
    _validar(empresa, ano, mes, modo, abrir_por, filtros, linha)
    if mes_ini is not None and (isinstance(mes_ini, bool) or not isinstance(mes_ini, int) or not 1 <= mes_ini <= mes):
        raise ValueError("Mês inicial inválido.")
    inicio = mes_ini if mes_ini is not None else (mes if modo == "mes" else 1)
    per = _periodo(conn, empresa, ano, inicio, mes)
    cad = _centros(conn, per["ids"])
    valores = defaultdict(lambda: [0.0, 0.0])  # (chave de abertura, linha da DRE) -> [orçado, realizado]
    eliminado = [0.0]
    cache_linha = {}
    for indice, _eid, _comp, conta, centro, valor in _filtradas(conn, per, filtros, eliminado):
        lid = cache_linha.get(conta)
        if lid is None:
            lid = cache_linha[conta] = linha_da_conta(conta)
        if linha is not None and lid != linha and linha in _BASE_GER + [SEM_LINHA[0]]:
            continue
        if not _passa(filtros, centro, cad):
            continue
        valores[(_rotulo(abrir_por, centro, cad), lid)][indice] += valor

    return _montar(valores, abrir_por, linha, dict(
        empresa=empresa, ano=ano, mes=mes, modo=modo, abrir_por=abrir_por, competencias=per["meses"],
        **_meta(conn, empresa, ano, per, eliminado)))


def _por_linha(pares):
    """{linha base: [orc, real]} -> linhas da DRE gerencial com os subtotais calculados."""
    saida = {}
    for indice in (0, 1):
        base = {k: 0.0 for k in _BASE_GER}
        for lid, par in pares.items():
            if lid in base:
                base[lid] += par[indice]
        base.update(DEPREC_VALOR=0.0, EP_TOTAL_VALOR=0.0)
        _aplicar_calc_ger(base)
        for lid, _, _ in LINHAS:
            saida.setdefault(lid, [0.0, 0.0])[indice] = base.get(lid, 0.0)
    sem = pares.get(SEM_LINHA[0], [0.0, 0.0])
    if sem[0] or sem[1]:
        saida[SEM_LINHA[0]] = list(sem)
    return saida


def _linha_saida(rotulo, orc, real, **extra):
    orc, real = round(orc, 2) + 0.0, round(real, 2) + 0.0  # + 0.0 tira o -0,0; resíduo de ponto flutuante (0,3 - 0,1 - 0,2) não vira % absurdo
    variacao = real - orc
    return dict(rotulo=rotulo, orcado=round(orc, 2), realizado=round(real, 2), variacao=round(variacao, 2),
                pct=round(real / orc * 100, 1) if orc else None, **extra)


def _montar(valores, abrir_por, linha, meta):
    if abrir_por == "linha":
        pares = defaultdict(lambda: [0.0, 0.0])
        for (_, lid), par in valores.items():
            pares[lid][0] += par[0]
            pares[lid][1] += par[1]
        dre = _por_linha(pares)
        rotulos = {lid: rot for lid, rot, _ in LINHAS}
        tipos = {lid: tipo for lid, _, tipo in LINHAS}
        rotulos[SEM_LINHA[0]], tipos[SEM_LINHA[0]] = SEM_LINHA[1], "grupo"
        ordem = [lid for lid, _, _ in LINHAS] + [SEM_LINHA[0]]
        linhas = [_linha_saida(rotulos[lid], *dre[lid], id=lid, tipo=tipos[lid]) for lid in ordem if lid in dre]
        total = dre["LL"]
        total = [total[0] + dre.get(SEM_LINHA[0], [0, 0])[0], total[1] + dre.get(SEM_LINHA[0], [0, 0])[1]]
    else:
        # Abertura por dimensão: cada linha é o resultado (soma das contas de resultado) daquele valor.
        # Com `linha` escolhida, é só aquela linha da DRE (base ou subtotal) aberta pela dimensão.
        por_rotulo = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
        for (rot, lid), par in valores.items():
            por_rotulo[rot][lid][0] += par[0]
            por_rotulo[rot][lid][1] += par[1]
        linhas, total = [], [0.0, 0.0]
        for rot, pares in por_rotulo.items():
            dre = _por_linha(pares)
            alvo = linha or "LL"
            orc, real = dre.get(alvo, [0.0, 0.0])
            if linha is None and SEM_LINHA[0] in dre:
                orc += dre[SEM_LINHA[0]][0]
                real += dre[SEM_LINHA[0]][1]
            if not orc and not real:
                continue
            linhas.append(_linha_saida(rot, orc, real))
            total[0] += orc
            total[1] += real
        linhas.sort(key=lambda l: (l["rotulo"] in (SEM_CENTRO, SEM_VALOR), -abs(l["orcado"]) - abs(l["realizado"])))
    meta["linhas"] = linhas
    meta["total"] = _linha_saida("Total", *total)
    meta["dimensao"] = DIMENSOES[abrir_por]
    meta["linha_dre"] = linha
    return meta


def opcoes_filtro(conn, empresa: str) -> dict:
    """Valores possíveis de serviço, coordenador, filial e centro, do cadastro de centros."""
    chaves = ["mkb", "gnileb"] if empresa == "consolidado" else [empresa]
    cad = _centros(conn, [EMPRESAS[k]["id"] for k in chaves if k in EMPRESAS])
    saida = {d: sorted({(c.get(d) or SEM_VALOR) for c in cad.values()}) for d in ("servico", "coordenador", "filial")}
    saida["centro"] = sorted(cad)
    return saida


# ─── Fase 6: DRE em árvore, por mês ──────────────────────────────────────────

# Nível 1 pela DRE gerencial (D3): bloco -> linhas base que ele soma
BLOCOS = [
    ("RECEITA", "Receita", ("ROB", "DED")),
    ("CUSTOS", "Custos", tuple(g for g in _GER_GRUPOS_DIRETOS if g.startswith("CPV_"))),
    ("DESPESAS", "Despesas", tuple(g for g in _GER_GRUPOS_DIRETOS if g.startswith("DADM_"))),
    ("FINANCEIRO", "Resultado financeiro", ("ENC_FIN",)),
    ("OUTROS", "Outros resultados", ("OUTROS_OP",)),
    ("IRPJ", "IRPJ e CSLL", ("IRPJ_CSLL",)),
    ("SEM", "Sem linha na DRE", (SEM_LINHA[0],)),
]
_BLOCO_DA_LINHA = {lid: b for b, _, lids in BLOCOS for lid in lids}
NIVEL_GRUPO = 5  # o 5º nível do código (3.1.1.01.01) é o grupo que aparece entre o bloco e a analítica


def _grupo(conta: str) -> str:
    partes = conta.split(".")
    return ".".join(partes[:NIVEL_GRUPO]) if len(partes) > NIVEL_GRUPO else conta


def _descricoes(conn, ids, codigos) -> dict:
    """código -> descrição da tabela `contas`; vale a da primeira empresa da lista (MKB no consolidado)."""
    saida = {}
    codigos = sorted(codigos)
    for eid in ids:
        for i in range(0, len(codigos), 500):
            lote = codigos[i:i + 500]
            marcas = ",".join("?" * len(lote))
            for cod, desc in conn.execute(f"SELECT trim(cod), descricao FROM contas WHERE empresa_id = ? AND trim(cod) IN ({marcas})",
                                          (eid, *lote)):
                if desc and cod not in saida:
                    saida[cod] = " ".join(str(desc).split())[:120]
    return saida


def _ultimo_dia(comp: str) -> str:
    import calendar
    ano, mes = int(comp[:4]), int(comp[5:7])
    return f"{calendar.monthrange(ano, mes)[1]:02d}/{mes:02d}/{ano}"


def arvore(conn, empresa: str, ano: int, mes_ini: int, mes_fim: int, filtros: dict | None = None) -> dict:
    """Linhas da árvore (Resultado no topo, bloco, grupo do 5º nível, analítica) com [orçado, realizado] por mês,
    Acumulado e Média. Média do orçado = acumulado ÷ meses do período; do realizado = acumulado ÷ meses com razão."""
    for v in (mes_ini, mes_fim):
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 12:
            raise ValueError("Mês inválido.")
    if mes_ini > mes_fim:
        raise ValueError("O mês inicial vem depois do final.")
    _validar(empresa, ano, mes_fim, "mes", "linha", filtros, None)
    per = _periodo(conn, empresa, ano, mes_ini, mes_fim)
    cad = _centros(conn, per["ids"])
    meses = per["meses"]
    pos = {c: i for i, c in enumerate(meses)}
    vazio = lambda: [[0.0, 0.0] for _ in meses]  # noqa: E731
    por_conta = defaultdict(vazio)
    eliminado = [0.0]
    for indice, _eid, comp, conta, centro, valor in _filtradas(conn, per, filtros, eliminado):
        if _passa(filtros, centro, cad):
            por_conta[conta][pos[comp]][indice] += valor

    # cada conta arredondada antes de somar: o pai é a soma exata, em centavos, dos filhos que aparecem na tela
    for cels in por_conta.values():
        for c in cels:
            c[0], c[1] = round(c[0], 2), round(c[1], 2)
    descr = _descricoes(conn, per["ids"], set(por_conta) | {_grupo(c) for c in por_conta})
    meses_sem = [c for c in meses if any(c in f for f in per["sem_razao"].values())]
    com_razao = [i for i, c in enumerate(meses) if c not in meses_sem]

    def no(id_, pai, nivel, codigo, rotulo, cels):
        acum = [round(sum(c[0] for c in cels), 2), round(sum(cels[i][1] for i in com_razao), 2) if com_razao else None]
        # orçado só dos meses que têm razão: é contra ele que o realizado acumulado se compara
        orc_cmp = round(sum(cels[i][0] for i in com_razao), 2)
        media = [round(acum[0] / len(meses), 2), round(acum[1] / len(com_razao), 2) if com_razao else None]
        return dict(id=id_, pai=pai, nivel=nivel, codigo=codigo, rotulo=rotulo,
                    meses=[[round(o, 2), None if meses[i] in meses_sem else round(r, 2)] for i, (o, r) in enumerate(cels)],
                    acumulado=acum, media=media, orcado_comparavel=orc_cmp,
                    media_orcado_comparavel=round(orc_cmp / len(com_razao), 2) if com_razao else None)

    def soma(listas):
        tot = vazio()
        for cels in listas:
            for i, (o, r) in enumerate(cels):
                tot[i][0] += o
                tot[i][1] += r
        return tot

    linhas, blocos_cels = [], {}
    for bid, rotulo, _ in BLOCOS:
        contas = sorted(c for c in por_conta if _BLOCO_DA_LINHA.get(linha_da_conta(c)) == bid)
        if not contas:
            continue
        grupos = defaultdict(list)
        for c in contas:
            grupos[_grupo(c)].append(c)
        filhos = []
        for g in sorted(grupos):
            g_cels = soma(por_conta[c] for c in grupos[g])
            filhos.append(no(f"g:{bid}:{g}", bid, 2, g, descr.get(g) or f"Grupo {g}", g_cels))
            for c in grupos[g]:
                filhos.append(no(f"c:{c}", f"g:{bid}:{g}", 3, c, descr.get(c) or c, por_conta[c]))
        blocos_cels[bid] = soma(por_conta[c] for c in contas)
        linhas.append(no(bid, "TOTAL", 1, "", rotulo, blocos_cels[bid]))
        linhas.extend(filhos)
    total = no("TOTAL", None, 0, "", "Resultado", soma(blocos_cels.values()))
    ultimo = [c for c in meses if c not in meses_sem]
    return dict(empresa=empresa, ano=ano, mes_ini=mes_ini, mes_fim=mes_fim, competencias=meses,
                linhas=[total] + linhas, total=total,
                realizado_ate=_ultimo_dia(ultimo[-1]) if ultimo else None,
                **_meta(conn, empresa, ano, per, eliminado))


# ─── Fase 7: abertura por dimensão (Receita, Custo e Despesa, MC) e lançamentos ─

CUSTO_DESPESA = tuple(g for g in _GER_GRUPOS_DIRETOS if g.startswith(("CPV_", "DADM_")))
MAX_LANCAMENTOS = 3000


def por_dimensao(conn, empresa: str, ano: int, mes_ini: int, mes_fim: int, abrir_por: str,
                 filtros: dict | None = None) -> dict:
    """Uma linha por valor da dimensão com Receita (ROB + deduções), Custo e Despesa (custos e despesas
    operacionais) e MC = Receita + Custo e Despesa (D8), em orçado e realizado. Financeiro, outros, IRPJ e
    contas sem linha ficam fora da MC. Com mês sem razão no período, o orçado considera só os meses com
    razão, para a comparação ser do mesmo período (o aviso diz quais meses saíram)."""
    if abrir_por not in DIMENSOES or abrir_por == "linha":
        raise ValueError("Abertura inválida.")
    for v in (mes_ini, mes_fim):
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 12:
            raise ValueError("Mês inválido.")
    if mes_ini > mes_fim:
        raise ValueError("O mês inicial vem depois do final.")
    _validar(empresa, ano, mes_fim, "mes", abrir_por, filtros, None)
    per = _periodo(conn, empresa, ano, mes_ini, mes_fim)
    cad = _centros(conn, per["ids"])
    meses_sem = {c for c in per["meses"] if any(c in f for f in per["sem_razao"].values())}
    com_razao = [c for c in per["meses"] if c not in meses_sem]
    considera = set(com_razao) or set(per["meses"])
    linhas = defaultdict(lambda: {"receita": [0.0, 0.0], "cd": [0.0, 0.0]})
    chaves = {}  # rótulo -> valor cru do filtro, para o drilldown (no centro, o rótulo traz a descrição)
    eliminado = [0.0]
    cache = {}
    for indice, _eid, comp, conta, centro, valor in _filtradas(conn, per, filtros, eliminado):
        if comp not in considera or not _passa(filtros, centro, cad):
            continue
        lid = cache.get(conta)
        if lid is None:
            lid = cache[conta] = linha_da_conta(conta)
        grupo = "receita" if lid in ("ROB", "DED") else ("cd" if lid in CUSTO_DESPESA else None)
        if grupo:
            rot = _rotulo(abrir_por, centro, cad)
            linhas[rot][grupo][indice] += valor
            chaves.setdefault(rot, (centro or SEM_CENTRO) if abrir_por == "centro" else rot)

    def linha(rotulo, v):
        rec, cd = [round(x, 2) for x in v["receita"]], [round(x, 2) for x in v["cd"]]
        mc = [round(rec[i] + cd[i], 2) for i in (0, 1)]
        if not com_razao:  # nenhum mês com razão: o realizado é sem dado, não zero
            rec[1] = cd[1] = mc[1] = None
        return dict(rotulo=rotulo, chave=chaves.get(rotulo), receita=rec, custo_despesa=cd, mc=mc,
                    mc_pct=[round(mc[i] / rec[i] * 100, 1) if rec[i] and mc[i] is not None else None for i in (0, 1)],
                    variacao=round(mc[1] - mc[0], 2) if com_razao else None)

    saida = [linha(r, v) for r, v in linhas.items() if any(v["receita"] + v["cd"])]
    saida.sort(key=lambda l: (l["rotulo"] in (SEM_CENTRO, SEM_VALOR), -abs(l["mc"][0]) - abs(l["mc"][1] or 0)))
    tot = {"receita": [sum(v["receita"][i] for v in linhas.values()) for i in (0, 1)],
           "cd": [sum(v["cd"][i] for v in linhas.values()) for i in (0, 1)]}
    return dict(empresa=empresa, ano=ano, mes_ini=mes_ini, mes_fim=mes_fim, abrir_por=abrir_por,
                dimensao=DIMENSOES[abrir_por], linhas=saida, total=linha("Total", tot),
                meses_considerados=sorted(considera), competencias=per["meses"],
                **_meta(conn, empresa, ano, per, eliminado))


def lancamentos(conn, empresa: str, ano: int, mes_ini: int, mes_fim: int, conta: str,
                filtros: dict | None = None) -> dict:
    """Lançamentos do razão de uma conta no período, com os filtros de centro; soma = realizado da conta."""
    if not isinstance(conta, str) or not conta.strip().startswith(("3", "4")) or len(conta) > 40:
        raise ValueError("Conta inválida.")
    conta = conta.strip()
    for v in (mes_ini, mes_fim):
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 12:
            raise ValueError("Mês inválido.")
    if mes_ini > mes_fim:
        raise ValueError("O mês inicial vem depois do final.")
    _validar(empresa, ano, mes_fim, "mes", "linha", filtros, None)
    per = _periodo(conn, empresa, ano, mes_ini, mes_fim)
    cad = _centros(conn, per["ids"])
    gnileb_id = EMPRESAS["gnileb"]["id"]
    marcas = per["marcas"]
    linhas, total, n = [], 0.0, 0
    for eid, data, doc, hist, centro, valor in conn.execute(
            f"""SELECT empresa_id, data_lanc, documento, historico, replace(trim(COALESCE(centro_custo, '')), '.', ''), valor
                FROM razao WHERE empresa_id IN ({marcas}) AND competencia BETWEEN ? AND ? AND trim(conta_cod) = ?
                ORDER BY data_lanc, id""", (*per["ids"], per["meses"][0], per["meses"][-1], conta)):
        if per["consolidado"] and eid == gnileb_id and conta in CONTAS_EP:
            continue
        if not _passa(filtros, centro or "", cad):
            continue
        total += valor or 0.0
        n += 1
        if len(linhas) < MAX_LANCAMENTOS:
            linhas.append(dict(empresa=EMPRESAS[next(k for k in EMPRESAS if EMPRESAS[k]["id"] == eid)]["sigla"],
                               data=data, documento=(doc or "")[:40], historico=" ".join(str(hist or "").split())[:200],
                               centro=centro or "", valor=round(valor or 0.0, 2)))
    descr = _descricoes(conn, per["ids"], {conta}).get(conta, conta)
    return dict(conta=conta, descricao=descr, linhas=linhas, total=round(total, 2), quantidade=n,
                cortado=n > len(linhas), limite=MAX_LANCAMENTOS)

