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
        if chave not in FILTROS or not isinstance(valores, (list, tuple, set)):
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


def _passa(filtros, centro, cad):
    for chave, valores in (filtros or {}).items():
        if not valores:
            continue
        valor = centro if chave == "centro" else ((cad.get(centro) or {}).get(chave) or (SEM_VALOR if centro else SEM_CENTRO))
        if (valor or SEM_CENTRO) not in valores:
            return False
    return True


def calcular(conn, empresa: str, ano: int, mes: int, modo: str = "mes", abrir_por: str = "linha",
             filtros: dict | None = None, linha: str | None = None) -> dict:
    _validar(empresa, ano, mes, modo, abrir_por, filtros, linha)
    consolidado = empresa == "consolidado"
    chaves = ["mkb", "gnileb"] if consolidado else [empresa]
    ids = [EMPRESAS[k]["id"] for k in chaves]
    gnileb_id = EMPRESAS["gnileb"]["id"]
    comp_fim = f"{ano}-{mes:02d}"
    comp_ini = comp_fim if modo == "mes" else f"{ano}-01"
    meses = [f"{ano}-{m:02d}" for m in range(int(comp_ini[5:]), mes + 1)]
    marcas = ",".join("?" * len(ids))

    com_razao = {(e, c) for e, c in conn.execute(
        f"SELECT DISTINCT empresa_id, competencia FROM razao WHERE empresa_id IN ({marcas}) AND competencia BETWEEN ? AND ?",
        (*ids, comp_ini, comp_fim))}
    # no consolidado, o mês fica sem realizado se faltar o razão de QUALQUER das empresas
    sem_razao = {EMPRESAS[k]["sigla"]: [c for c in meses if (EMPRESAS[k]["id"], c) not in com_razao] for k in chaves}
    cad = _centros(conn, ids)

    # (chave de abertura, linha da DRE) -> [orçado, realizado]
    valores = defaultdict(lambda: [0.0, 0.0])
    eliminado = 0.0
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
    cache_linha = {}
    for indice, sql in consultas:
        for eid, comp, conta, centro, valor in conn.execute(sql, (*ids, comp_ini, comp_fim)):
            conta = (conta or "").strip()
            centro = (centro or "").strip()
            if consolidado and eid == gnileb_id and conta in CONTAS_EP:
                eliminado += valor or 0.0
                continue
            lid = cache_linha.get(conta)
            if lid is None:
                lid = cache_linha[conta] = linha_da_conta(conta)
            if linha is not None and lid != linha and linha in _BASE_GER + [SEM_LINHA[0]]:
                continue
            if not _passa(filtros, centro, cad):
                continue
            valores[(_rotulo(abrir_por, centro, cad), lid)][indice] += valor or 0.0

    return _montar(valores, abrir_por, linha, dict(
        empresa=empresa, ano=ano, mes=mes, modo=modo, abrir_por=abrir_por, competencias=meses,
        meses_sem_realizado=[c for c in meses if any(c in faltam for faltam in sem_razao.values())],
        sem_razao_por_empresa={sigla: faltam for sigla, faltam in sem_razao.items() if faltam},
        sem_orcamento=not conn.execute(
            f"SELECT 1 FROM orcamento WHERE empresa_id IN ({marcas}) AND substr(competencia, 1, 4) = ? LIMIT 1",
            (*ids, str(ano))).fetchone(),
        eliminado_equivalencia=round(-eliminado, 2) if consolidado else 0.0))


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
