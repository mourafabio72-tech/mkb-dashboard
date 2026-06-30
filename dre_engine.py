"""
dre_engine.py — MKB-Dashboard  Sprint 2
Motor de cálculo da DRE com:
  - Eliminação da Equivalência Patrimonial (coluna Ajuste)
  - DRE mensal (meses lado a lado)
  - Formato sem centavos
"""

import json
from pathlib import Path
from ingestion import get_conn
from config import EMPRESAS

# ─── MAPEAMENTO DE CONTAS ─────────────────────────────────────────────────────

_MAP_PATH = Path(__file__).parent / "account_map.json"
_PREFIXOS: list[tuple[str, str]] = []

# Contas-reflexo do balancete a ignorar na conciliação DRE × Balancete.
# Espelham um total já detalhado em outro ramo e dobrariam o valor:
#   3.1.2.01.02 "Impostos Incidentes s/ Receita" espelha o detalhe de
#   PIS/COFINS/ISS em 3.1.3.* (que é onde o razão de fato lança).
EXCLUIR_BALANCETE = ("3.1.2.01.02",)

def _get_prefixos() -> list[tuple[str, str]]:
    global _PREFIXOS
    if not _PREFIXOS:
        with open(_MAP_PATH, encoding="utf-8") as f:
            data = json.load(f)
        mapa = {k: v for k, v in data.items() if not k.startswith("_")}
        # De-para customizado (banco) estende/sobrepõe o JSON. Mesmo prefixo →
        # custom vence; prefixo novo → adicionado. Prioridade ainda é por
        # comprimento (prefixo mais longo casa primeiro).
        try:
            conn = get_conn()
            tem_tabela = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_map_custom'"
            ).fetchone()
            if tem_tabela:
                for prefixo, grupo in conn.execute(
                    "SELECT prefixo, grupo FROM account_map_custom"
                ).fetchall():
                    mapa[prefixo] = grupo
            conn.close()
        except Exception:
            pass
        _PREFIXOS = sorted(mapa.items(), key=lambda x: len(x[0]), reverse=True)
    return _PREFIXOS


def invalidar_prefixos() -> None:
    """Zera o cache do de-para — chamar após editar account_map_custom."""
    global _PREFIXOS
    _PREFIXOS = []


def classificar_conta(cod: str) -> str:
    for prefixo, grupo in _get_prefixos():
        if cod.startswith(prefixo):
            return grupo
    return "NAO_CLASSIFICADO"


def grupos_disponiveis() -> list[tuple[str, str]]:
    """Lista (grupo, label) para o seletor do de-para — exclui NAO_CLASSIFICADO."""
    return [(g, GRUPO_LABELS.get(g, g)) for g in _ORDEM_GRUPOS if g != "NAO_CLASSIFICADO"]


def conciliar_balancete(empresa_id: int, competencia: str) -> dict:
    """Compara a DRE detalhada (movimento acumulado do Razão até a competência)
    contra o saldo do balancete, conta a conta (contas de resultado 3.x/4.x).
    Retorna as diferenças ordenadas por valor absoluto + totais."""
    ano      = competencia[:4]
    comp_ini = f"{ano}-01"

    conn = get_conn()
    tbl = _tabela_lancamentos(conn)

    # DRE: movimento acumulado por conta (Jan → competência), só resultado.
    # Comparação por MOVIMENTO (soma dos lançamentos) -- bate com o balancete
    # para a grande maioria das contas. Quando uma conta diverge e a causa é um
    # lançamento que entra só no saldo corrido do Protheus (retroativo, sem
    # linha detalhada), o drill-down evidencia "lançamento não detalhado".
    dre_rows = conn.execute(
        f"""
        SELECT conta_cod, SUM(valor)
        FROM {tbl}
        WHERE empresa_id = ? AND competencia >= ? AND competencia <= ?
          AND (conta_cod LIKE '3.%' OR conta_cod LIKE '4.%')
        GROUP BY conta_cod
        """,
        (empresa_id, comp_ini, competencia)
    ).fetchall()
    dre = {c: round(v or 0.0, 2) for c, v in dre_rows}

    # Movimento do razão por conta E por mês (para localizar em que mês está a
    # diferença de uma conta).
    from collections import defaultdict
    dre_mes_rows = conn.execute(
        f"""
        SELECT conta_cod, competencia, SUM(valor)
        FROM {tbl}
        WHERE empresa_id = ? AND competencia >= ? AND competencia <= ?
          AND (conta_cod LIKE '3.%' OR conta_cod LIKE '4.%')
        GROUP BY conta_cod, competencia
        """,
        (empresa_id, comp_ini, competencia)
    ).fetchall()
    dre_mes: dict[str, dict[str, float]] = defaultdict(dict)
    for cod, comp, val in dre_mes_rows:
        dre_mes[cod][comp] = round(val or 0.0, 2)

    tem_bal = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='balancete'"
    ).fetchone()
    bal_rows = conn.execute(
        """
        SELECT conta_cod, descricao, saldo_atual
        FROM balancete
        WHERE empresa_id = ? AND competencia = ?
          AND (conta_cod LIKE '3.%' OR conta_cod LIKE '4.%')
        """,
        (empresa_id, competencia)
    ).fetchall() if tem_bal else []

    # Saldo acumulado do razão por conta (SALDO ATUAL do último lançamento da
    # competência mais recente ≤ alvo). Ordena por competência DESC e id DESC
    # (robusto à ordem de importação dos meses). Usado só para CONCILIAR uma
    # conta quando o saldo bate com o balancete -- nunca para criar diferença.
    razao_saldo_rows = conn.execute(
        """
        SELECT conta_cod, saldo_atual FROM (
            SELECT conta_cod, saldo_atual,
                   ROW_NUMBER() OVER (
                       PARTITION BY conta_cod ORDER BY competencia DESC, id DESC
                   ) AS rn
            FROM razao
            WHERE empresa_id = ? AND competencia <= ?
              AND saldo_atual IS NOT NULL
              AND (conta_cod LIKE '3.%' OR conta_cod LIKE '4.%')
        ) WHERE rn = 1
        """,
        (empresa_id, competencia)
    ).fetchall()
    razao_saldo = {c: round(v or 0.0, 2) for c, v in razao_saldo_rows}
    conn.close()

    # Só contas analíticas (folha) do balancete -- evita somar sintéticas.
    # Exclui também as contas-reflexo do balancete (EXCLUIR_BALANCETE): contas
    # que espelham um total já detalhado em outro ramo (ex.: 3.1.2.01.02
    # "Impostos Incidentes" espelha o detalhe em 3.1.3.* PIS/COFINS/ISS) e
    # dobrariam o valor na conciliação.
    bal_codes = {r[0] for r in bal_rows}
    def _is_leaf(c: str) -> bool:
        return not any(o != c and o.startswith(c + ".") for o in bal_codes)
    def _excluida(c: str) -> bool:
        return any(c == p or c.startswith(p) for p in EXCLUIR_BALANCETE)
    bal_leaves = [
        (r[0], r[1], round(r[2] or 0.0, 2))
        for r in bal_rows if _is_leaf(r[0]) and not _excluida(r[0])
    ]
    bal_por_conta = {cod: saldo for cod, _desc, saldo in bal_leaves}

    # Valor efetivo do razão por conta:
    #   - se a conta tem saldo no razão E esse saldo bate com o balancete →
    #     usa o SALDO (concilia; cobre lançamentos retroativos que entram só no
    #     saldo, não como linha de movimento);
    #   - caso contrário → usa o MOVIMENTO (soma dos lançamentos) -- seguro,
    #     mesmo comportamento de antes. Nunca cria diferença a partir do saldo.
    razao_val: dict[str, float] = {}
    conciliadas_saldo: set[str] = set()
    for cod in (set(dre) | set(bal_por_conta)):
        mov = round(dre.get(cod, 0.0), 2)
        bal = bal_por_conta.get(cod)
        sal = razao_saldo.get(cod)
        if bal is not None and sal is not None and abs(round(sal - bal, 2)) < 0.01:
            razao_val[cod] = round(bal, 2)   # conciliado pelo saldo
            conciliadas_saldo.add(cod)
        else:
            razao_val[cod] = mov

    # Agrega cada fonte por GRUPO da DRE (mesma régua account_map / de-para) e
    # guarda as contas que compõem cada grupo, para drill-down.
    g_dre = defaultdict(float)
    contas_dre = defaultdict(dict)   # grupo -> {cod: valor}
    for cod, val in razao_val.items():
        g = classificar_conta(cod)
        g_dre[g] += val
        contas_dre[g][cod] = round(val, 2)
    g_bal = defaultdict(float)
    contas_bal = defaultdict(dict)   # grupo -> {cod: (desc, saldo)}
    for cod, desc, saldo in bal_leaves:
        g = classificar_conta(cod)
        g_bal[g] += saldo
        contas_bal[g][cod] = (desc, round(saldo, 2))

    # O balancete lança a receita LÍQUIDA de abatimentos/devoluções (sem linha
    # separada), enquanto o razão lança receita BRUTA + abatimentos à parte.
    # Para comparar na mesma base, "regrossa" o balancete: devolve o abatimento
    # (valor do razão) à Receita Bruta do balancete e cria a linha de
    # abatimentos. Net no resultado é zero -- só reclassifica ROB ↔ DED_ABAT.
    abat_dre = round(g_dre.get("DED_ABAT", 0.0), 2)
    if abat_dre and round(g_bal.get("DED_ABAT", 0.0), 2) == 0.0:
        g_bal["ROB"]      = g_bal.get("ROB", 0.0) - abat_dre
        g_bal["DED_ABAT"] = g_bal.get("DED_ABAT", 0.0) + abat_dre

    tot_dre = round(sum(g_dre.values()), 2)
    tot_bal = round(sum(g_bal.values()), 2)

    linhas = []
    for grupo in (set(g_dre) | set(g_bal)):
        dv = round(g_dre.get(grupo, 0.0), 2)
        bv = round(g_bal.get(grupo, 0.0), 2)
        diff = round(dv - bv, 2)
        if abs(diff) < 0.01:
            continue

        # Drill-down: contas do grupo (união dos códigos das duas fontes)
        cods = set(contas_dre.get(grupo, {})) | set(contas_bal.get(grupo, {}))
        contas = []
        for c in cods:
            cdv = contas_dre.get(grupo, {}).get(c, 0.0)
            cdesc, cbv = contas_bal.get(grupo, {}).get(c, ("", 0.0))
            cdiff = round(cdv - cbv, 2)
            if abs(cdiff) >= 0.01:
                meses = [
                    {"competencia": comp, "valor": val}
                    for comp, val in sorted(dre_mes.get(c, {}).items())
                    if abs(val) >= 0.01
                ]
                contas.append({
                    "cod": c, "descricao": cdesc,
                    "dre": round(cdv, 2), "balancete": round(cbv, 2), "diff": cdiff,
                    "meses": meses,
                    # parte do saldo do balancete que não está nos movimentos do
                    # razão (lançamento retroativo que entra só no saldo corrido).
                    # Só faz sentido quando a conta existe nas duas fontes.
                    "nao_detalhado": round(cbv - cdv, 2) if (cdv and cbv) else 0.0,
                })
        contas.sort(key=lambda x: -abs(x["diff"]))

        linhas.append({
            "grupo":       grupo,
            "grupo_label": GRUPO_LABELS.get(grupo, grupo),
            "dre":         dv,
            "balancete":   bv,
            "diff":        diff,
            "so_dre":       bv == 0.0,
            "so_balancete": dv == 0.0,
            "contas":      contas,
        })

    linhas.sort(key=lambda x: -abs(x["diff"]))
    return {
        "linhas":     linhas,
        "tot_dre":    tot_dre,
        "tot_bal":    tot_bal,
        "tot_diff":   round(tot_dre - tot_bal, 2),
        "qtd_diff":   len(linhas),
        "tem_balancete": bool(bal_leaves),
    }


def contas_nao_classificadas() -> list[dict]:
    """Contas presentes nos dados (Razão/CT2) que não casam com nenhum prefixo
    do de-para — somem da DRE em silêncio. Retorna com valor para diagnóstico."""
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"""
        SELECT l.conta_cod, COALESCE(c.descricao, ''), SUM(l.valor) AS total, e.sigla
        FROM {tbl} l
        LEFT JOIN contas c   ON l.conta_cod = c.cod AND l.empresa_id = c.empresa_id
        JOIN empresas e      ON e.id = l.empresa_id
        GROUP BY l.empresa_id, l.conta_cod
        """
    ).fetchall()
    conn.close()

    out = []
    for cod, desc, total, sigla in rows:
        if classificar_conta(cod) == "NAO_CLASSIFICADO" and total and abs(total) > 0.005:
            out.append({
                "cod": cod, "descricao": desc,
                "total": round(total), "empresa": sigla,
            })
    out.sort(key=lambda x: -abs(x["total"]))
    return out


# ─── CONTAS DE EQUIVALÊNCIA PATRIMONIAL (eliminadas no consolidado) ───────────

# Apenas estas contas são eliminadas; outras do grupo 4.4.1.06 são mantidas
CONTAS_EP = {"4.4.1.06.01.001", "4.4.1.06.02.001"}

# ─── CONTA DE DEPRECIAÇÃO / AMORTIZAÇÃO (memorando no bridge do EBITDA) ──────
# Classificada em DADM_OUTROS (já incluída em "(=) Despesas Operacionais").
CONTA_DEPREC = "4.4.1.03.09.012"


# ─── ESTRUTURA DE LINHAS DA DRE ──────────────────────────────────────────────

GRUPOS_POR_LINHA = {
    "ROB":       ["ROB"],
    "DED":       ["DED_ABAT", "DED_IMPOS"],
    "CPV":       [
        "CPV_PROLAB", "CPV_FOLHA", "CPV_ENCARG",
        "CPV_MATER",  "CPV_SERV",  "CPV_COMERC",  "CPV_RECUP",
        "CPV_ALUG",   "CPV_CONCESSION", "CPV_COMUNIC",
        "CPV_VEIC",   "CPV_ESCRIT",     "CPV_DESLOC",
        "CPV_SEGUROS","CPV_OUTROS",
    ],
    "DADM":      [
        "DADM_PROLAB", "DADM_FOLHA", "DADM_ENCARG",
        "DADM_MATER",  "DADM_SERV",  "DADM_COMERC",  "DADM_TRIBUT",
        "DADM_ALUG",   "DADM_CONCESSION", "DADM_COMUNIC",
        "DADM_VEIC",   "DADM_VIAGEM",     "DADM_SEGUROS",
        "DADM_OUTROS", "DADM_ACORDOS",
    ],
    "ENC_FIN":   ["ENC_DESP", "ENC_REC"],
    "OUTROS_OP": ["OUTROS_OP"],
    "IRPJ_CSLL": ["IRPJ_CSLL"],
}

DRE_META = [
    # (linha_id,   label,                                 tipo,            secao)
    ("ROB",        "(+) Receita Operacional Bruta",       "subtotal",      "receita"),
    ("DED",        "(-) Deduções das Vendas",             "subtotal",      "receita"),
    ("ROL",        "(=) Receita Operacional Líquida",     "resultado",     "receita"),
    ("CPV",        "(-) Custo das Vendas",                "subtotal",      "custo"),
    ("LB",         "(=) Lucro Bruto",                     "resultado",     "custo"),
    ("DADM",       "(-) Despesas Administrativas",        "subtotal",      "despesa"),
    ("ENC_FIN",    "(+/-) Encargos Financeiros Líq.",     "subtotal",      "financeiro"),
    ("OUTROS_OP",  "(+/-) Outros Resultados",             "subtotal",      "financeiro"),
    ("LAIR",       "(=) Resultado antes IRPJ e CSLL",     "resultado",     "resultado"),
    ("IRPJ_CSLL",  "(-) Provisão IRPJ e CSLL",           "subtotal",      "resultado"),
    ("LL",         "(=) Resultado Líquido",               "resultado_final","resultado"),
    ("EBITDA",     "EBITDA",                              "ebitda",        "ebitda"),
]

_CALC = {
    "ROL":    lambda g: g["ROB"] + g["DED"],
    "LB":     lambda g: g["ROL"] + g["CPV"],
    "LAIR":   lambda g: g["LB"] + g["DADM"] + g["ENC_FIN"] + g["OUTROS_OP"],
    "LL":     lambda g: g["LAIR"] + g["IRPJ_CSLL"],
    "EBITDA": lambda g: g["LAIR"] - g["ENC_FIN"],
}

# Linhas que são somas de grupos (as demais são calculadas)
_LINHAS_SOMA = list(GRUPOS_POR_LINHA.keys())


def _aplicar_calc(result: dict) -> dict:
    """Aplica as linhas calculadas a um dict de grupos."""
    for linha, fn in _CALC.items():
        result[linha] = fn(result)
    return result


# ─── DRE POR EMPRESA ─────────────────────────────────────────────────────────

def _tabela_lancamentos(conn) -> str:
    """Retorna 'v_lancamentos' se a view existir, senão 'lancamentos'."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_lancamentos'"
    ).fetchone()
    return "v_lancamentos" if exists else "lancamentos"


def calcular_dre(empresa_id: int, competencia: str) -> dict:
    """Calcula DRE resumida para uma empresa/competência."""
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"SELECT conta_cod, valor FROM {tbl} WHERE empresa_id=? AND competencia=?",
        (empresa_id, competencia)
    ).fetchall()
    conn.close()

    grupos: dict[str, float] = {}
    nao_class = []

    for cod, valor in rows:
        grupo = classificar_conta(cod)
        if grupo == "NAO_CLASSIFICADO":
            nao_class.append((cod, valor))
            continue
        grupos[grupo] = grupos.get(grupo, 0.0) + valor

    result = {linha: sum(grupos.get(g, 0.0) for g in gs)
              for linha, gs in GRUPOS_POR_LINHA.items()}
    _aplicar_calc(result)

    result["_nao_classificado"] = sum(v for _, v in nao_class)
    result["_nao_class_contas"] = nao_class
    return result


# ─── AJUSTE — ELIMINAÇÃO DA EQUIVALÊNCIA PATRIMONIAL ─────────────────────────

def calcular_ajuste(competencia: str) -> dict:
    """
    Retorna o ajuste de eliminação da Equivalência Patrimonial da Gnileb.
    Inverte o sinal das contas EP para neutralizá-las no consolidado.
    """
    gnileb_id = EMPRESAS["gnileb"]["id"]
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"SELECT conta_cod, valor FROM {tbl} "
        "WHERE empresa_id=? AND competencia=? AND conta_cod IN (?,?)",
        (gnileb_id, competencia, *CONTAS_EP)
    ).fetchall()
    conn.close()

    ep_total = sum(valor for _, valor in rows)

    # O ajuste é o inverso: elimina a EP do OUTROS_OP
    ajuste: dict[str, float] = {linha: 0.0 for linha in _LINHAS_SOMA}
    ajuste["OUTROS_OP"] = -ep_total   # inverte sinal para eliminar

    # Propaga para as linhas calculadas
    _aplicar_calc(ajuste)
    return ajuste


# ─── CONSOLIDADO (MKB + GNILEB + AJUSTE) ─────────────────────────────────────

def calcular_consolidado(competencia: str) -> dict:
    """Consolida MKB + Gnileb com eliminação da Equivalência Patrimonial."""
    mkb    = calcular_dre(EMPRESAS["mkb"]["id"],    competencia)
    gnileb = calcular_dre(EMPRESAS["gnileb"]["id"], competencia)
    ajuste = calcular_ajuste(competencia)

    result = {}
    for linha in _LINHAS_SOMA:
        result[linha] = (mkb.get(linha, 0.0)
                       + gnileb.get(linha, 0.0)
                       + ajuste.get(linha, 0.0))
    _aplicar_calc(result)
    return result


# ─── TODAS AS VISÕES (por empresa + ajuste + consolidado) ────────────────────

def calcular_todas_empresas(competencia: str) -> dict:
    """
    Retorna dict com DRE das 4 visões: mkb, gnileb, ajuste, consolidado.
    """
    mkb    = calcular_dre(EMPRESAS["mkb"]["id"],    competencia)
    gnileb = calcular_dre(EMPRESAS["gnileb"]["id"], competencia)
    ajuste = calcular_ajuste(competencia)

    # Consolidado a partir dos já calculados (evita recalcular)
    cons = {}
    for linha in _LINHAS_SOMA:
        cons[linha] = (mkb.get(linha, 0.0)
                     + gnileb.get(linha, 0.0)
                     + ajuste.get(linha, 0.0))
    _aplicar_calc(cons)

    return {
        "mkb":         mkb,
        "gnileb":      gnileb,
        "ajuste":      ajuste,
        "consolidado": cons,
    }


# ─── DRE MENSAL (meses lado a lado) ──────────────────────────────────────────

def calcular_dre_mensal(empresa_chave: str, competencias: list) -> dict:
    """
    Retorna { competencia: dre_dict } para todos os meses pedidos.
    empresa_chave: 'mkb' | 'gnileb' | 'consolidado'
    """
    resultado = {}
    for comp in competencias:
        if empresa_chave == "consolidado":
            resultado[comp] = calcular_consolidado(comp)
        else:
            emp_id = EMPRESAS.get(empresa_chave, {}).get("id")
            if emp_id:
                resultado[comp] = calcular_dre(emp_id, comp)
    return resultado


def calcular_dre_mensal_detalhada(empresa_id: int, competencias: list) -> dict:
    """
    Retorna { competencia: lista_de_grupos_detalhados }
    Cada item da lista é o mesmo formato de calcular_dre_detalhada().
    """
    return {comp: calcular_dre_detalhada(empresa_id, comp) for comp in competencias}


# ─── DADOS PARA GRÁFICOS DO DASHBOARD ────────────────────────────────────────

# Nomes amigáveis dos segmentos de receita por código de conta
_SEGMENTO_LABELS = {
    "3.1.1.01.01.001": "Gerenciamento Predial",
    "3.1.1.01.01.002": "Serviços Operacionais",
    "3.1.1.01.01.003": "Manutenção Predial",
    "3.1.1.01.01.004": "Assessoria / Consultoria",
    "3.1.1.01.01.005": "Limpeza e Conservação",
}


def calcular_rob_por_segmento(competencias: list) -> list:
    """
    Retorna lista [{label, valor}] com ROB acumulado por conta de receita
    (todas as empresas consolidadas, todos os meses somados).
    Apenas contas com prefixo 3.1.1.
    """
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"""
        SELECT l.conta_cod, c.descricao, SUM(l.valor) as total
        FROM {tbl} l
        LEFT JOIN contas c ON l.conta_cod = c.cod AND l.empresa_id = c.empresa_id
        WHERE l.conta_cod LIKE '3.1.1.%'
          AND l.competencia IN ({','.join('?' * len(competencias))})
        GROUP BY l.conta_cod
        ORDER BY total DESC
        """,
        competencias
    ).fetchall()
    conn.close()

    resultado = []
    for cod, desc, total in rows:
        if total and total > 0:
            label = _SEGMENTO_LABELS.get(cod) or (desc or cod).title()
            resultado.append({"label": label, "valor": round(total)})
    return resultado


def _top_contas(prefixos_like: list, competencias: list, n: int) -> list:
    """Retorna top N contas de débito (custo/despesa) para os prefixos dados."""
    condicoes = " OR ".join(f"l.conta_cod LIKE ?" for _ in prefixos_like)
    params = prefixos_like + competencias + [n]
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"""
        SELECT l.conta_cod, c.descricao, SUM(l.valor) as total
        FROM {tbl} l
        LEFT JOIN contas c ON l.conta_cod = c.cod AND l.empresa_id = c.empresa_id
        WHERE ({condicoes})
          AND l.competencia IN ({','.join('?' * len(competencias))})
        GROUP BY l.conta_cod
        HAVING total < 0
        ORDER BY total ASC
        LIMIT ?
        """,
        params
    ).fetchall()
    conn.close()
    return [
        {"label": _abrev(desc or cod), "valor": abs(round(total))}
        for cod, desc, total in rows
    ]


def _abrev(label: str, max_chars: int = 30) -> str:
    """Abrevia descrição longa mantendo legibilidade."""
    s = label.title()
    return s if len(s) <= max_chars else s[:max_chars - 1] + "…"


def calcular_top_custo(competencias: list, n: int = 10) -> list:
    """Top N contas de CUSTO (CPV — contas 4.1.1.*)."""
    return _top_contas(["4.1.1.%"], competencias, n)


def calcular_top_despesa(competencias: list, n: int = 10) -> list:
    """Top N contas de DESPESA ADMINISTRATIVA (contas 4.4.1.01.*, 4.4.1.02.*, 4.4.1.03.*)."""
    return _top_contas(
        ["4.4.1.01.%", "4.4.1.02.%", "4.4.1.03.%"],
        competencias, n
    )


# Mantém compatibilidade com chamadas anteriores
def calcular_top_contas_custo(competencias: list, n: int = 5) -> list:
    return _top_contas(
        ["4.1.1.%", "4.4.1.01.%", "4.4.1.02.%", "4.4.1.03.%"],
        competencias, n
    )


def calcular_serie_mensal(competencias: list) -> dict:
    """
    Retorna dicts de série mensal (Consolidado) para os gráficos.
    {
        'labels':  ['Jan/2026', 'Fev/2026', ...],
        'rob':     [6635689, 6814748, ...],
        'lb':      [694209,  605814, ...],
        'ebitda':  [...],
        'lair':    [...],
        'margem_lb':    [10.5, 8.9, ...],   # % sobre ROB
        'margem_ebitda':[...],
    }
    """
    mensal = calcular_dre_mensal("consolidado", competencias)
    labels, rob, lb, ebitda, lair = [], [], [], [], []
    margem_lb, margem_ebitda = [], []

    for comp in competencias:
        d = mensal.get(comp, {})
        r = d.get("ROB", 0) or 1
        labels.append(_mes_label_simples(comp))
        rob.append(round(d.get("ROB", 0)))
        lb.append(round(d.get("LB", 0)))
        ebitda.append(round(d.get("EBITDA", 0)))
        lair.append(round(d.get("LAIR", 0)))
        margem_lb.append(round(d.get("LB", 0) / r * 100, 1))
        margem_ebitda.append(round(d.get("EBITDA", 0) / r * 100, 1))

    return {
        "labels": labels,
        "rob": rob,
        "lb": lb,
        "ebitda": ebitda,
        "lair": lair,
        "margem_lb": margem_lb,
        "margem_ebitda": margem_ebitda,
    }


def _mes_label_simples(competencia: str) -> str:
    meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    try:
        ano, mes = competencia.split("-")
        return f"{meses[int(mes)-1]}/{ano[2:]}"
    except Exception:
        return competencia


# ─── DRE DETALHADA ────────────────────────────────────────────────────────────

GRUPO_LABELS = {
    "ROB":               "Receita Operacional Bruta",
    "DED_ABAT":          "Abatimentos e Devoluções",
    "DED_IMPOS":         "Impostos s/ Receita (ISS / PIS / COFINS)",
    # Custos operacionais
    "CPV_PROLAB":        "Pró-labore / Honorários (Custo)",
    "CPV_FOLHA":         "Folha de Pagamento (Custo)",
    "CPV_ENCARG":        "Encargos s/ Folha (Custo)",
    "CPV_MATER":         "Material Aplicado (Custo)",
    "CPV_SERV":          "Serviço Contratado (Custo)",
    "CPV_COMERC":        "Comercial (Custo)",
    "CPV_RECUP":         "Recuperação de Impostos",
    "CPV_ALUG":          "Aluguéis (Custo)",
    "CPV_CONCESSION":    "Concessionárias (Custo)",
    "CPV_COMUNIC":       "Comunicação (Custo)",
    "CPV_VEIC":          "Veículos (Custo)",
    "CPV_ESCRIT":        "Escritório (Custo)",
    "CPV_DESLOC":        "Deslocamento e Viagens (Custo)",
    "CPV_SEGUROS":       "Seguros (Custo)",
    "CPV_OUTROS":        "Outros Custos Diretos",
    # Despesas operacionais
    "DADM_PROLAB":       "Pró-labore / Honorários (Adm.)",
    "DADM_FOLHA":        "Folha de Pagamento (Adm.)",
    "DADM_ENCARG":       "Encargos s/ Folha (Adm.)",
    "DADM_MATER":        "Material Aplicado (Adm.)",
    "DADM_SERV":         "Serviço Contratado (Adm.)",
    "DADM_COMERC":       "Comercial (Adm.)",
    "DADM_TRIBUT":       "Tributos e Contribuições",
    "DADM_ALUG":         "Aluguéis (Adm.)",
    "DADM_CONCESSION":   "Concessionárias (Adm.)",
    "DADM_COMUNIC":      "Comunicação (Adm.)",
    "DADM_VEIC":         "Veículos (Adm.)",
    "DADM_VIAGEM":       "Viagem (Adm.)",
    "DADM_SEGUROS":      "Seguros (Adm.)",
    "DADM_OUTROS":       "Outros Despesas (Adm.)",
    "DADM_ACORDOS":      "Acordos Judiciais",
    # Financeiro e outros
    "ENC_DESP":          "Despesas Financeiras",
    "ENC_REC":           "Receitas Financeiras",
    "OUTROS_OP":         "Outros Resultados Operacionais",
    "IRPJ_CSLL":         "Provisão IRPJ e CSLL",
    "NAO_CLASSIFICADO":  "Não classificado",
}

_ORDEM_GRUPOS = [
    "ROB", "DED_ABAT", "DED_IMPOS",
    "CPV_PROLAB", "CPV_FOLHA", "CPV_ENCARG",
    "CPV_MATER",  "CPV_SERV",  "CPV_COMERC",  "CPV_RECUP",
    "CPV_ALUG",   "CPV_CONCESSION", "CPV_COMUNIC",
    "CPV_VEIC",   "CPV_ESCRIT",     "CPV_DESLOC",
    "CPV_SEGUROS","CPV_OUTROS",
    "DADM_PROLAB", "DADM_FOLHA", "DADM_ENCARG",
    "DADM_MATER",  "DADM_SERV",  "DADM_COMERC",  "DADM_TRIBUT",
    "DADM_ALUG",   "DADM_CONCESSION", "DADM_COMUNIC",
    "DADM_VEIC",   "DADM_VIAGEM",     "DADM_SEGUROS",
    "DADM_OUTROS", "DADM_ACORDOS",
    "ENC_DESP", "ENC_REC",
    "OUTROS_OP", "IRPJ_CSLL", "NAO_CLASSIFICADO",
]

_GRUPO_PARA_LINHA = {
    g: linha
    for linha, grupos in GRUPOS_POR_LINHA.items()
    for g in grupos
}


def calcular_dre_detalhada(empresa_id: int, competencia: str) -> list:
    """Retorna lista de grupos com contas detalhadas para uma empresa/competência."""
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"""
        SELECT l.conta_cod, c.descricao, l.valor
        FROM {tbl} l
        LEFT JOIN contas c ON l.conta_cod = c.cod AND l.empresa_id = c.empresa_id
        WHERE l.empresa_id = ? AND l.competencia = ?
        ORDER BY l.conta_cod
        """,
        (empresa_id, competencia)
    ).fetchall()
    conn.close()

    grupos_dict: dict[str, list] = {}
    for cod, desc, valor in rows:
        if valor == 0.0:
            continue
        grupo = classificar_conta(cod)
        grupos_dict.setdefault(grupo, []).append({
            "cod": cod, "descricao": desc or cod, "valor": valor,
        })

    resultado = []
    for grupo in _ORDEM_GRUPOS:
        contas = grupos_dict.get(grupo)
        if not contas:
            continue
        contas_ord = sorted(contas, key=lambda x: x["cod"])
        resultado.append({
            "grupo":     grupo,
            "linha_dre": _GRUPO_PARA_LINHA.get(grupo, ""),
            "label":     GRUPO_LABELS.get(grupo, grupo),
            "subtotal":  sum(c["valor"] for c in contas_ord),
            "contas":    contas_ord,
        })
    return resultado


# ─── DRE GERENCIAL — estrutura expandida (~30 linhas) ────────────────────────

# Linhas da DRE Gerencial: grupos individuais visíveis + linhas calculadas
DRE_META_GERENCIAL = [
    # (linha_id,        label,                                  tipo,            secao)
    ("ROB",             "(+) Receita Operacional Bruta",        "grupo_pos",     "receita"),
    ("DED",             "(-) Deduções das Vendas",              "grupo",         "receita"),
    ("ROL",             "(=) Receita Operacional Líquida",      "resultado",     "receita"),
    # Custos
    ("CPV_PROLAB",      "(-) Pró-labore / Honorários",          "grupo",         "custo"),
    ("CPV_FOLHA",       "(-) Folha de Pagamento",               "grupo",         "custo"),
    ("CPV_ENCARG",      "(-) Encargos s/ Folha",                "grupo",         "custo"),
    ("CPV_MATER",       "(-) Material Aplicado",                "grupo",         "custo"),
    ("CPV_SERV",        "(-) Serviço Contratado",               "grupo",         "custo"),
    ("CPV_COMERC",      "(-) Comercial",                        "grupo",         "custo"),
    ("CPV_RECUP",       "(+) Recuperação de Impostos",          "grupo_pos",     "custo"),
    ("CPV_ALUG",        "(-) Aluguéis",                         "grupo",         "custo"),
    ("CPV_CONCESSION",  "(-) Concessionárias",                  "grupo",         "custo"),
    ("CPV_COMUNIC",     "(-) Comunicação",                      "grupo",         "custo"),
    ("CPV_VEIC",        "(-) Veículos",                         "grupo",         "custo"),
    ("CPV_ESCRIT",      "(-) Escritório",                       "grupo",         "custo"),
    ("CPV_DESLOC",      "(-) Deslocamento e Viagens",           "grupo",         "custo"),
    ("CPV_SEGUROS",     "(-) Seguros",                          "grupo",         "custo"),
    ("CPV_OUTROS",      "(-) Outros Custos Diretos",            "grupo",         "custo"),
    ("CPV_TOTAL",       "(=) Custos Operacionais",              "resultado",     "custo"),
    ("LB",              "(=) Lucro Bruto",                      "resultado",     "custo"),
    # Despesas
    ("DADM_PROLAB",     "(-) Pró-labore / Honorários",          "grupo",         "despesa"),
    ("DADM_FOLHA",      "(-) Folha de Pagamento",               "grupo",         "despesa"),
    ("DADM_ENCARG",     "(-) Encargos s/ Folha",                "grupo",         "despesa"),
    ("DADM_MATER",      "(-) Material Aplicado",                "grupo",         "despesa"),
    ("DADM_SERV",       "(-) Serviço Contratado",               "grupo",         "despesa"),
    ("DADM_COMERC",     "(-) Comercial",                        "grupo",         "despesa"),
    ("DADM_TRIBUT",     "(-) Tributos e Contribuições",         "grupo",         "despesa"),
    ("DADM_ALUG",       "(-) Aluguéis",                         "grupo",         "despesa"),
    ("DADM_CONCESSION", "(-) Concessionárias",                  "grupo",         "despesa"),
    ("DADM_COMUNIC",    "(-) Comunicação",                      "grupo",         "despesa"),
    ("DADM_VEIC",       "(-) Veículos",                         "grupo",         "despesa"),
    ("DADM_VIAGEM",     "(-) Viagem",                           "grupo",         "despesa"),
    ("DADM_SEGUROS",    "(-) Seguros",                          "grupo",         "despesa"),
    ("DADM_OUTROS",     "(-) Outros Despesas",                  "grupo",         "despesa"),
    ("DADM_ACORDOS",    "(-) Acordos Judiciais",                "grupo",         "despesa"),
    ("DADM_TOTAL",      "(=) Despesas Operacionais",            "resultado",     "despesa"),
    # Financeiro e final
    ("ENC_FIN",         "(+/-) Encargos Financeiros Líq.",      "subtotal",      "financeiro"),
    ("OUTROS_OP",       "(+/-) Outros Resultados",              "subtotal",      "financeiro"),
    ("LAIR",            "(=) Resultado antes IRPJ e CSLL",      "resultado",     "resultado"),
    ("IRPJ_CSLL",       "(-) Provisão IRPJ e CSLL",            "subtotal",      "resultado"),
    ("LL",              "(=) Resultado Líquido",                "resultado_final","resultado"),
    ("EBITDA",          "EBITDA",                               "ebitda",        "ebitda"),
]

# IDs dos grupos "diretos" na DRE Gerencial (cada grupo = uma linha)
_GER_GRUPOS_DIRETOS = [
    "CPV_PROLAB", "CPV_FOLHA", "CPV_ENCARG", "CPV_MATER",  "CPV_SERV",
    "CPV_COMERC", "CPV_RECUP", "CPV_ALUG",   "CPV_CONCESSION", "CPV_COMUNIC",
    "CPV_VEIC",   "CPV_ESCRIT","CPV_DESLOC", "CPV_SEGUROS","CPV_OUTROS",
    "DADM_PROLAB","DADM_FOLHA","DADM_ENCARG","DADM_MATER", "DADM_SERV",
    "DADM_COMERC","DADM_TRIBUT","DADM_ALUG", "DADM_CONCESSION","DADM_COMUNIC",
    "DADM_VEIC",  "DADM_VIAGEM","DADM_SEGUROS","DADM_OUTROS","DADM_ACORDOS",
]

# Linhas de soma no DRE Gerencial (os grupos diretos + ROB/DED/ENC_FIN/OUTROS_OP/IRPJ_CSLL)
# DEPREC_VALOR/EP_TOTAL_VALOR: valores "puros" (não agregados em grupo) das contas
# de Depreciação/Amortização e Equivalência Patrimonial — usados para reverter
# esses itens no cálculo do EBITDA (ver _CALC_GER["EBITDA"] e montar_bridge_ebitda).
_LINHAS_SOMA_GER = (["ROB", "DED", "ENC_FIN", "OUTROS_OP", "IRPJ_CSLL"]
                    + _GER_GRUPOS_DIRETOS
                    + ["DEPREC_VALOR", "EP_TOTAL_VALOR"])

_CPVS = [g for g in _GER_GRUPOS_DIRETOS if g.startswith("CPV_")]
_DADMS = [g for g in _GER_GRUPOS_DIRETOS if g.startswith("DADM_")]

# Composição (em grupos do account_map / _ORDEM_GRUPOS) das linhas
# "agregadas" da DRE Gerencial que também são drilláveis no dashboard.
# Usado por _merge_detalhe_gerencial (app.py) para montar a lista de
# contas de cada linha a partir dos grupos individuais já calculados.
#   DED        = Deduções (Abatimentos + Impostos s/ Receita)
#   ROL        = Receita Líquida = ROB + DED
#   CPV_TOTAL  = Custos Operacionais = soma de todos os grupos CPV_*
#   DADM_TOTAL = Despesas Operacionais = soma de todos os grupos DADM_*
#   ENC_FIN    = Resultado Financeiro = Despesas Financeiras + Receitas Financeiras
# LL (Resultado Final) não entra aqui: seu drill-down não é uma lista de
# contas, e sim a "ponte" (bridge) com os subtotais ROL→...→LL — ver
# montar_bridge_resultado_final(). EBITDA idem — ver montar_bridge_ebitda().
GRUPOS_AGREGADOS_GER = {
    "DED":        ["DED_ABAT", "DED_IMPOS"],
    "ROL":        ["ROB", "DED_ABAT", "DED_IMPOS"],
    "CPV_TOTAL":  _CPVS,
    "DADM_TOTAL": _DADMS,
    "ENC_FIN":    ["ENC_DESP", "ENC_REC"],
}

_CALC_GER = {
    "ROL":       lambda g: g["ROB"] + g["DED"],
    "CPV_TOTAL": lambda g: sum(g.get(k, 0.0) for k in _CPVS),
    "LB":        lambda g: g["ROL"] + g["CPV_TOTAL"],
    "DADM_TOTAL":lambda g: sum(g.get(k, 0.0) for k in _DADMS),
    "LAIR":      lambda g: g["LB"] + g["DADM_TOTAL"] + g["ENC_FIN"] + g["OUTROS_OP"],
    "LL":        lambda g: g["LAIR"] + g["IRPJ_CSLL"],
    # EBITDA "Ajustado": além de LAIR - Resultado Financeiro, reverte também
    # Depreciação/Amortização (despesa não-caixa) e Equivalência Patrimonial
    # (resultado não-operacional) — mesma lógica da "ponte" em
    # montar_bridge_ebitda(), porém aplicada diretamente ao cabeçalho da linha.
    "EBITDA":    lambda g: (g["LAIR"] - g["ENC_FIN"]
                            - g.get("DEPREC_VALOR", 0.0)
                            - g.get("EP_TOTAL_VALOR", 0.0)),
}


def _aplicar_calc_ger(result: dict) -> dict:
    """Aplica as linhas calculadas do DRE Gerencial."""
    for linha, fn in _CALC_GER.items():
        result[linha] = fn(result)
    return result


def calcular_dre_gerencial(empresa_id: int, competencia: str) -> dict:
    """
    Calcula DRE Gerencial (granular) para uma empresa/competência.
    Retorna dict com ~30 linhas individuais + linhas calculadas.
    """
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"SELECT conta_cod, valor FROM {tbl} WHERE empresa_id=? AND competencia=?",
        (empresa_id, competencia)
    ).fetchall()
    conn.close()

    grupos: dict[str, float] = {}
    deprec_valor = 0.0
    ep_total_valor = 0.0
    for cod, valor in rows:
        grupo = classificar_conta(cod)
        if grupo != "NAO_CLASSIFICADO":
            grupos[grupo] = grupos.get(grupo, 0.0) + valor
        # Valores "puros" (fora da agregação por grupo) usados na reversão do
        # EBITDA Ajustado — ver _CALC_GER["EBITDA"].
        if cod == CONTA_DEPREC:
            deprec_valor += valor
        if cod in CONTAS_EP:
            ep_total_valor += valor

    # Soma ROB e DED normalmente (agrupam vários sub-grupos)
    result: dict[str, float] = {}
    result["ROB"]       = grupos.get("ROB", 0.0)
    result["DED"]       = grupos.get("DED_ABAT", 0.0) + grupos.get("DED_IMPOS", 0.0)
    result["ENC_FIN"]   = grupos.get("ENC_DESP", 0.0) + grupos.get("ENC_REC", 0.0)
    result["OUTROS_OP"] = grupos.get("OUTROS_OP", 0.0)
    result["IRPJ_CSLL"] = grupos.get("IRPJ_CSLL", 0.0)
    result["DEPREC_VALOR"]   = deprec_valor
    result["EP_TOTAL_VALOR"] = ep_total_valor

    # Grupos diretos (um grupo = uma linha)
    for g in _GER_GRUPOS_DIRETOS:
        result[g] = grupos.get(g, 0.0)

    _aplicar_calc_ger(result)
    return result


def calcular_ajuste_gerencial(competencia: str) -> dict:
    """
    Ajuste gerencial: elimina Equivalência Patrimonial da Gnileb no consolidado.
    Retorna dict no mesmo formato que calcular_dre_gerencial().
    """
    gnileb_id = EMPRESAS["gnileb"]["id"]
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"SELECT conta_cod, valor FROM {tbl} "
        "WHERE empresa_id=? AND competencia=? AND conta_cod IN (?,?)",
        (gnileb_id, competencia, *CONTAS_EP)
    ).fetchall()
    conn.close()

    ep_total = sum(v for _, v in rows)
    ajuste: dict[str, float] = {k: 0.0 for k in _LINHAS_SOMA_GER}
    ajuste["OUTROS_OP"] = -ep_total
    _aplicar_calc_ger(ajuste)
    return ajuste


def calcular_todas_empresas_gerencial(competencia: str) -> dict:
    """
    Retorna {mkb, gnileb, ajuste, consolidado} usando a DRE Gerencial.
    """
    mkb    = calcular_dre_gerencial(EMPRESAS["mkb"]["id"],    competencia)
    gnileb = calcular_dre_gerencial(EMPRESAS["gnileb"]["id"], competencia)
    ajuste = calcular_ajuste_gerencial(competencia)

    cons: dict[str, float] = {}
    for linha in _LINHAS_SOMA_GER:
        cons[linha] = (mkb.get(linha, 0.0)
                     + gnileb.get(linha, 0.0)
                     + ajuste.get(linha, 0.0))
    _aplicar_calc_ger(cons)

    return {"mkb": mkb, "gnileb": gnileb, "ajuste": ajuste, "consolidado": cons}


def calcular_dre_gerencial_mensal(competencias: list) -> dict:
    """
    Retorna {competencia: consolidado_gerencial} para cálculo de YTD e média.
    """
    return {comp: calcular_todas_empresas_gerencial(comp)["consolidado"]
            for comp in competencias}


def calcular_dre_detalhada_gerencial(empresa_id: int, competencia: str) -> list:
    """
    Retorna contas detalhadas agrupadas pelos novos grupos gerenciais.
    Mesmo formato de calcular_dre_detalhada() mas com os novos grupos.
    """
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"""
        SELECT l.conta_cod, c.descricao, l.valor
        FROM {tbl} l
        LEFT JOIN contas c ON l.conta_cod = c.cod AND l.empresa_id = c.empresa_id
        WHERE l.empresa_id = ? AND l.competencia = ?
        ORDER BY l.conta_cod
        """,
        (empresa_id, competencia)
    ).fetchall()
    conn.close()

    grupos_dict: dict[str, list] = {}
    for cod, desc, valor in rows:
        if valor == 0.0:
            continue
        grupo = classificar_conta(cod)
        grupos_dict.setdefault(grupo, []).append({
            "cod": cod, "descricao": desc or cod, "valor": valor,
        })

    resultado = []
    for grupo in _ORDEM_GRUPOS:
        contas = grupos_dict.get(grupo)
        if not contas:
            continue
        contas_ord = sorted(contas, key=lambda x: x["cod"])
        resultado.append({
            "grupo":    grupo,
            "label":    GRUPO_LABELS.get(grupo, grupo),
            "subtotal": sum(c["valor"] for c in contas_ord),
            "contas":   contas_ord,
        })
    return resultado


def montar_bridge_ebitda(dados: dict, det_mkb: list, det_gnileb: list) -> list:
    """
    Monta a "ponte" (bridge) de reconciliação do EBITDA AJUSTADO partindo do
    Resultado Líquido (LL), trazendo todos os itens somados/revertidos para
    se chegar ao EBITDA — incluindo depreciação e equivalência patrimonial,
    que também compõem o ajuste:

        (=) Resultado Líquido (LL)
        (+)    Reversão da Provisão de IRPJ e CSLL
        (+/-)  Reversão do Resultado Financeiro
        (+)    Depreciação / Amortização (reversão)
        (+/-)  Equivalência Patrimonial — por conta (reversão)
        (=) EBITDA Ajustado

    `dados` é o retorno de calcular_todas_empresas_gerencial(competencia)
    (chaves: mkb, gnileb, ajuste, consolidado). `det_mkb`/`det_gnileb` são o
    retorno de calcular_dre_detalhada_gerencial() para cada empresa.

    Retorna lista no mesmo formato de _merge_detalhe_gerencial()
    ([{cod, descricao, mkb, gnileb, total}]), pronta para o template
    renderizar como "filhas" da linha EBITDA (mesmo padrão de ROB/DED/ROL).

    Observação: o total final ("(=) EBITDA Ajustado") passa a diferir do
    valor da linha-mãe "EBITDA" (que segue a fórmula simples
    LAIR − Resultado Financeiro, sem reverter depreciação/equivalência) —
    é justamente esse o ajuste pedido: somar de volta a depreciação
    (despesa não-caixa) e excluir o resultado de equivalência patrimonial
    (não-operacional) do EBITDA.
    """
    mkb_d = dados["mkb"]
    gni_d = dados["gnileb"]
    aju_d = dados["ajuste"]

    def _linha(cod, descricao, m, g, extra=0.0):
        return {
            "cod": cod, "descricao": descricao,
            "mkb": m, "gnileb": g, "total": m + g + extra,
        }

    itens = [
        _linha("_LL", "(=) Resultado Líquido (LL)",
               mkb_d["LL"], gni_d["LL"], aju_d["LL"]),
        _linha("_REV_IRPJ", "(+) Reversão da Provisão de IRPJ e CSLL",
               -mkb_d["IRPJ_CSLL"], -gni_d["IRPJ_CSLL"], -aju_d["IRPJ_CSLL"]),
        _linha("_REV_ENCFIN", "(+/-) Reversão do Resultado Financeiro",
               -mkb_d["ENC_FIN"], -gni_d["ENC_FIN"], -aju_d["ENC_FIN"]),
    ]

    # ── Depreciação / Amortização — reversão (soma de volta ao EBITDA) ──────
    for g in det_mkb:
        if g["grupo"] == "DADM_OUTROS":
            for c in g["contas"]:
                if c["cod"] == CONTA_DEPREC:
                    itens.append(_linha(
                        c["cod"], f"(+) {c['descricao']} (reversão)",
                        -c["valor"], 0.0,
                    ))

    # ── Equivalência Patrimonial — reversão (exclui resultado não-operac.) ──
    for g in det_gnileb:
        if g["grupo"] == "OUTROS_OP":
            for c in g["contas"]:
                if c["cod"] in CONTAS_EP:
                    itens.append(_linha(
                        c["cod"], f"(+/-) {c['descricao']} (reversão)",
                        0.0, -c["valor"],
                    ))

    # ── Subtotal final: EBITDA Ajustado = soma de todos os itens acima ──────
    total_geral = sum(i["total"]   for i in itens)
    mkb_geral    = sum(i["mkb"]    for i in itens)
    gni_geral    = sum(i["gnileb"] for i in itens)
    itens.append(_linha("_EBITDA_AJ", "(=) EBITDA Ajustado",
                         mkb_geral, gni_geral, total_geral - mkb_geral - gni_geral))

    return itens


def montar_bridge_resultado_final(dados: dict) -> list:
    """
    Monta a "ponte" (bridge) de reconciliação do RESULTADO FINAL (Resultado
    Líquido — LL) partindo da Receita Operacional Líquida (ROL), trazendo os
    subtotais somados/subtraídos até chegar ao LL:

        (=) Receita Operacional Líquida (ROL)
        (-)    Custos Operacionais
        (-)    Despesas Operacionais
        (+/-)  Encargos Financeiros Líq.
        (+/-)  Outros Resultados
        (-)    Provisão de IRPJ e CSLL
        (=) Resultado Líquido (LL)

    `dados` é o retorno de calcular_todas_empresas_gerencial(competencia)
    (chaves: mkb, gnileb, ajuste, consolidado).

    Diferente de montar_bridge_ebitda(), esta ponte usa diretamente os
    SUBTOTAIS já calculados (ROL, CPV_TOTAL, DADM_TOTAL, ENC_FIN, OUTROS_OP,
    IRPJ_CSLL) — não desce ao nível de conta, pois cada um desses subtotais
    já é (ou pode ser) drillável individualmente na própria DRE.

    Retorna lista no mesmo formato de _merge_detalhe_gerencial()
    ([{cod, descricao, mkb, gnileb, total}]), pronta para o template
    renderizar como "filhas" da linha LL (mesmo padrão de ROL/EBITDA).
    """
    mkb_d = dados["mkb"]
    gni_d = dados["gnileb"]
    aju_d = dados["ajuste"]

    def _linha(cod, descricao, m, g, extra=0.0):
        return {
            "cod": cod, "descricao": descricao,
            "mkb": m, "gnileb": g, "total": m + g + extra,
        }

    itens = [
        _linha("_ROL",    "(=) Receita Operacional Líquida",
               mkb_d["ROL"], gni_d["ROL"], aju_d["ROL"]),
        _linha("_CPVTOT", "(-) Custos Operacionais",
               mkb_d["CPV_TOTAL"], gni_d["CPV_TOTAL"], aju_d["CPV_TOTAL"]),
        _linha("_DADMTOT","(-) Despesas Operacionais",
               mkb_d["DADM_TOTAL"], gni_d["DADM_TOTAL"], aju_d["DADM_TOTAL"]),
        _linha("_ENCFIN2","(+/-) Encargos Financeiros Líq.",
               mkb_d["ENC_FIN"], gni_d["ENC_FIN"], aju_d["ENC_FIN"]),
        _linha("_OUTROS2","(+/-) Outros Resultados",
               mkb_d["OUTROS_OP"], gni_d["OUTROS_OP"], aju_d["OUTROS_OP"]),
        _linha("_IRPJ2",  "(-) Provisão IRPJ e CSLL",
               mkb_d["IRPJ_CSLL"], gni_d["IRPJ_CSLL"], aju_d["IRPJ_CSLL"]),
    ]

    # ── Subtotal final: Resultado Líquido = soma de todos os itens acima ────
    total_geral = sum(i["total"]   for i in itens)
    mkb_geral    = sum(i["mkb"]    for i in itens)
    gni_geral    = sum(i["gnileb"] for i in itens)
    itens.append(_linha("_LL_BRIDGE", "(=) Resultado Líquido",
                         mkb_geral, gni_geral, total_geral - mkb_geral - gni_geral))

    return itens


# ─── ANÁLISE DE RECEITA POR CLIENTE ──────────────────────────────────────────
# Extrai o nome do cliente do campo "histórico" do Razão (CT1), no padrão
# Protheus:  "VL.NF.000160    - SITA BRASIL"
# Disponível apenas para competências em que o CT1 (Razão) foi importado —
# o CT2 (Comparativo) não traz histórico/lançamento individual.

import re as _re_cli

# Captura número da NF (grupo 1) e nome do cliente (grupo 2):
#   "VL.NF.000160    - SITA BRASIL"  →  ("000160", "SITA BRASIL")
_RE_CLIENTE_NF = _re_cli.compile(r'VL\.\s*NF\.\s*(\d+)\s*-\s*(.+)$', _re_cli.IGNORECASE)

_SEM_CLIENTE = "(Sem identificação)"
_SEM_NF      = "—"


def extrair_cliente(historico: str | None) -> str:
    """
    Extrai o nome do cliente de um histórico de lançamento de receita bruta
    (conta 3.1.1.x — linha 'VL.NF.{numero} - {CLIENTE}').

    Atenção: o Protheus grava o histórico com largura fixa (~38 caracteres),
    portanto nomes longos podem aparecer truncados de forma diferente em
    lançamentos distintos (ex.: 'EXECUTIVE OFFICE TOW' em vez de
    'EXECUTIVE OFFICE TOWER'). Não há como recuperar o nome completo a partir
    apenas deste campo — o valor é exibido como consta na origem.
    """
    nf, nome = _extrair_nf_cliente(historico)
    return nome


def _extrair_nf_cliente(historico: str | None) -> tuple:
    """Retorna (numero_nf, nome_cliente) a partir do histórico 'VL.NF.{n} - {CLIENTE}'."""
    if not historico:
        return None, _SEM_CLIENTE
    m = _RE_CLIENTE_NF.search(historico.strip())
    if m:
        numero = m.group(1).strip()
        nome   = m.group(2).strip() or _SEM_CLIENTE
        return numero, nome
    return None, _SEM_CLIENTE


def analisar_receita_clientes(empresa_id: int, competencias: list) -> dict:
    """
    Monta a análise de Receita Bruta (contas 3.1.1.x) por Cliente × Mês,
    a partir dos lançamentos individuais do Razão (CT1), com drill-down
    por Nota Fiscal (em vez de conta contábil — todas as linhas de
    receita bruta usam a mesma conta de faturamento por natureza).

    Retorna:
        {
          "clientes": [
              {"nome": str, "totais": {comp: valor}, "total_geral": float,
               "notas": [{"numero": str, "data": "YYYY-MM-DD" | None,
                          "totais": {comp: valor}, "total_geral": float}, ...]},
              ...  # ordenado por total_geral desc
          ],
          "competencias": [...],            # apenas as que têm CT1 disponível
          "competencias_sem_ct1": [...],    # competências pedidas sem Razão importado
          "totais_mes": {comp: valor},
          "total_geral": float,
        }
    """
    conn = get_conn()

    # Quais dessas competências têm CT1 (Razão) disponível para esta empresa?
    comp_ct1 = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT competencia FROM razao WHERE empresa_id = ?",
            (empresa_id,)
        ).fetchall()
    }
    comps_ok    = [c for c in competencias if c in comp_ct1]
    comps_falta = [c for c in competencias if c not in comp_ct1]

    clientes: dict[str, dict] = {}

    if comps_ok:
        placeholders = ",".join("?" * len(comps_ok))
        rows = conn.execute(
            f"""
            SELECT r.competencia, r.data_lanc, r.historico, r.valor
            FROM razao r
            WHERE r.empresa_id = ? AND r.conta_cod LIKE '3.1.1%'
              AND r.competencia IN ({placeholders})
            """,
            [empresa_id, *comps_ok]
        ).fetchall()

        for comp, data_lanc, hist, valor in rows:
            if not valor:
                continue
            numero_nf, nome = _extrair_nf_cliente(hist)
            cli = clientes.setdefault(nome, {"totais": {}, "notas": {}})
            cli["totais"][comp] = cli["totais"].get(comp, 0.0) + valor

            chave_nf = numero_nf or f"_sem_nf_{(hist or '')[:40]}"
            nf = cli["notas"].setdefault(
                chave_nf, {"numero": numero_nf or _SEM_NF, "data": data_lanc, "totais": {}}
            )
            nf["totais"][comp] = nf["totais"].get(comp, 0.0) + valor
            if not nf["data"] and data_lanc:
                nf["data"] = data_lanc

    conn.close()

    # Monta lista final ordenada por total geral (desc)
    lista = []
    for nome, dados in clientes.items():
        total_geral = sum(dados["totais"].values())
        notas = []
        for info in dados["notas"].values():
            notas.append({
                "numero":      info["numero"],
                "data":        info["data"],
                "totais":      info["totais"],
                "total_geral": sum(info["totais"].values()),
            })
        notas.sort(key=lambda x: (x["data"] or "", x["numero"] or ""))
        lista.append({
            "nome":        nome,
            "totais":      dados["totais"],
            "total_geral": total_geral,
            "notas":       notas,
        })
    lista.sort(key=lambda x: x["total_geral"], reverse=True)

    totais_mes = {comp: sum(c["totais"].get(comp, 0.0) for c in lista) for comp in comps_ok}
    total_geral = sum(totais_mes.values())

    return {
        "clientes":            lista,
        "competencias":        comps_ok,
        "competencias_sem_ct1": comps_falta,
        "totais_mes":          totais_mes,
        "total_geral":         total_geral,
    }


# ─── ANÁLISE DE DESPESAS POR FORNECEDOR ──────────────────────────────────────
# Extrai o nome do fornecedor do campo "histórico" do Razão (CT1), no padrão
# Protheus "[OPERAÇÃO] NF.<numero> DE <FORNECEDOR>" (e variantes "S/NF ... -"),
# e consolida pelo código do fornecedor (`parceiro_cod` = "Cli_For/Lj" do CT2)
# quando disponível -- muito mais estável que o nome, que vem truncado de
# formas diferentes entre lançamentos (ex.: "TELEXPERTS"/"TELEXPERT"/"TELEXP"
# sempre têm o mesmo código). Linhas sem código são "resgatadas" casando o
# nome extraído com um nome já associado a um código conhecido.
#
# Quando o cadastro mestre `fornecedores_cadastro` está populado (ver
# fornecedores_parser.py), usa a razão social oficial; caso contrário, usa o
# melhor nome aproximado disponível, marcado como tal (`aproximado=True`).
#
# Disponível apenas para competências em que o CT1 (Razão) foi importado.

_RE_FORN_DE    = _re_cli.compile(r'NF\.?\s*(\d+)\s+DE\s+(.+)$', _re_cli.IGNORECASE)
_RE_FORN_TRACO = _re_cli.compile(r'NF\.?\s*(\d+)\s*[-–]\s*(.+)$', _re_cli.IGNORECASE)

_SEM_FORNECEDOR = "(Lançamentos sem fornecedor identificado)"

# ── "Tentar novamente" identificar razão social — correspondência aproximada ──
# (fuzzy matching, stdlib `difflib`) entre nomes extraídos do histórico
# (truncados/aproximados) e o cadastro mestre `fornecedores_cadastro`. Roda
# automaticamente a cada carregamento da análise (sem botão/ação do usuário) --
# ver `_resolver_por_similaridade()` dentro de `analisar_despesas_fornecedores`.
import difflib as _difflib
import re as _re_fuzzy

_RE_FUZZY_LIMPA = _re_fuzzy.compile(r'[^A-Z0-9 ]+')


def _normaliza_nome_fuzzy(nome: str | None) -> str:
    """
    Normaliza um nome para comparação aproximada: maiúsculas, remove pontuação
    /acentos residuais e colapsa espaços -- ex. 'Telexperts Ltda.' e
    'TELEXPERTS LTDA' comparam iguais; '4 IRMÃOS COM. LTDA' ~ '4 IRMAOS'.
    """
    if not nome:
        return ""
    s = nome.upper().strip()
    s = _RE_FUZZY_LIMPA.sub(" ", s)
    return _re_fuzzy.sub(r'\s+', ' ', s).strip()


def _sao_variacoes(a: str, b: str) -> bool:
    """
    True se dois nomes (já normalizados por `_normaliza_nome_fuzzy`) parecem
    ser variações do MESMO fornecedor -- ex. 'BPS4' e 'BPS4 GESTAO CONTA'
    (provável re-cadastro do mesmo fornecedor sob código novo no Protheus:
    o nome curto é um PREFIXO de "palavra inteira" do nome completo) -- ou
    nomes de tamanho parecido com alta similaridade (pequenas variações de
    grafia/truncamento). Exige tamanho mínimo de 4 chars no nome curto e
    que o prefixo termine em fronteira de palavra, para evitar falso positivo
    entre siglas curtas de empresas diferentes (ex. 'BPS' não casa com
    'BPSAGRO CONSULTORIA').
    """
    if not a or not b:
        return False
    if a == b:
        return True
    curto, longo = (a, b) if len(a) <= len(b) else (b, a)
    if len(curto) < 4:
        return False
    if longo.startswith(curto) and (len(longo) == len(curto) or longo[len(curto)] == ' '):
        return True
    return _difflib.SequenceMatcher(None, a, b).ratio() >= 0.88

# Grupos de folha/encargos/pró-labore -- excluídos desta análise por pedido do
# usuário (o objetivo é acompanhar a evolução de custos/despesas operacionais,
# não de folha de pagamento, que tem análise própria em DP). Prefixos:
# 4.1.1.01.x (custo) e 4.4.1.01.x (administrativo).
GRUPOS_EXCLUIDOS_DESPESA = {
    "CPV_PROLAB", "CPV_FOLHA", "CPV_ENCARG",
    "DADM_PROLAB", "DADM_FOLHA", "DADM_ENCARG",
}

# ── Filtro Custo × Despesa (toggle "Tipo" na tela de Despesas por Fornecedor) ──
# Reaproveita a estrutura de linhas da DRE (`GRUPOS_POR_LINHA`) já existente:
#   "Custo"   = linha CPV  (4.1.x -- Custo das Vendas: material aplicado,
#               serviços, aluguéis, veículos etc. ligados à operação -- reduz
#               a Receita até o Lucro Bruto)
#   "Despesa" = todo o restante não-excluído (4.4.x/4.5.x -- DADM:
#               administrativas; ENC_FIN: juros/encargos financeiros;
#               OUTROS_OP: outros resultados operacionais; IRPJ_CSLL) --
#               reduz o resultado abaixo do Lucro Bruto
# É um split binário e exaustivo sobre os grupos não-excluídos (validado:
# 100% das contas 4.x não-folha caem em CPV ou em DADM/ENC_FIN/OUTROS_OP).
GRUPOS_CUSTO = set(GRUPOS_POR_LINHA["CPV"]) - GRUPOS_EXCLUIDOS_DESPESA


def _extrair_nf_fornecedor(historico: str | None) -> tuple:
    """
    Retorna (numero_nf | None, nome_extraido | None) a partir do histórico
    de um lançamento de despesa/custo. Padrões reconhecidos:
        "PROV.REF.A NF.000000135 DE 4 IRMAOS"        → ("000000135", "4 IRMAOS")
        "MULTA S/NF.043814 - ARBI /LEBLON OFFICE"    → ("043814", "ARBI /LEBLON OFFICE")
    Lançamentos sem NF/fornecedor no histórico (tarifas, PIS/COFINS s/ NF,
    rendimentos de aplicação etc.) retornam (None, None).
    """
    if not historico:
        return None, None
    h = historico.strip()
    m = _RE_FORN_DE.search(h)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = _RE_FORN_TRACO.search(h)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


def analisar_despesas_fornecedores(empresa_id: int, competencias: list, tipo: str = "todos") -> dict:
    """
    Monta a análise de Despesas e Custos (contas 4.x, EXCETO os grupos de
    folha/encargos/pró-labore -- ver GRUPOS_EXCLUIDOS_DESPESA) por
    CONTA CONTÁBIL (classificação primária -- código + descrição oficial do
    plano de contas, ex.: "SERV DE INFORMATICA") × Fornecedor × Mês, a partir
    dos lançamentos individuais do Razão (CT1). A classificação por GRUPO DRE
    (`classificar_conta`) é usada para (a) excluir folha/encargos/pró-labore e
    (b) aplicar o filtro `tipo` Custo×Despesa -- mas NÃO é mais a dimensão de
    exibição (era um "balde" largo demais; a conta contábil dá uma visão bem
    mais granular da evolução de cada custo/despesa).

    Parâmetros:
        tipo: filtro Custo × Despesa (toggle "Tipo" no template) --
            "todos"   (padrão) -- inclui tudo (Custo + Despesa)
            "custo"   -- somente linha CPV da DRE (4.1.x -- Custo das Vendas:
                         material aplicado, serviços, aluguéis, veículos etc.
                         ligados à operação -- ver GRUPOS_CUSTO)
            "despesa" -- somente o restante não-excluído (4.4.x/4.5.x --
                         administrativas, financeiras/juros, outros
                         resultados, IRPJ/CSLL)

    Constrói a base agregada uma única vez (já filtrada por `tipo`) e monta, a
    partir dela, DUAS visões de pivot (para o toggle "Ver por Conta ↔
    Fornecedor" no template) -- ambas com o mesmo total geral.

    Cada combinação (conta × fornecedor) carrega ainda um 3º nível de
    drill-down -- `lancamentos`: a lista de Notas Fiscais (ou lançamentos sem
    NF identificável) que compõem aquele total, com data, número da NF,
    histórico original e valores mês a mês. É a MESMA lista (mesma base
    agregada) exibida nas duas visões -- ao expandir um fornecedor (visão
    Conta) ou uma conta (visão Fornecedor), o usuário chega ao detalhe das NFs.

    Identificação do fornecedor -- além do pipeline existente (código
    Cli_For/Lj → cadastro oficial → nome canônico mais frequente → nome
    extraído aproximado), esta função tenta automaticamente "promover" nomes
    aproximados à razão social oficial via correspondência aproximada (fuzzy
    matching, `_resolver_por_similaridade`): quando a similaridade com algum
    nome do cadastro mestre é alta (cutoff 0.84), usa-se o nome oficial e o
    fornecedor passa a ser identificado por aquele código (`via_similaridade
    =True`, `aproximado=False`) -- roda sozinho, a cada carregamento da página.

    Alinhamento entre recadastros (Passo 3.6, `clusters`/`grupo_por_codigo`) --
    é comum o Protheus registrar o MESMO fornecedor real sob CÓDIGOS de
    cadastro diferentes ao longo do tempo (recadastro, ex.: "BPS4" código
    43220141 até Mar/2026 e "BPS4 GESTAO CONTA" código 62660141 a partir de
    Abr/2026 -- mesmo contrato recorrente, valores idênticos, nomes que são
    variações um do outro). Para cobrir esse caso -- que o agrupamento por
    código sozinho NÃO detecta, pois cada código já tem seu próprio nome
    "oficial" ou canônico -- esta função roda uma 2ª passada de clustering
    sobre os nomes já resolvidos (`nome_base_por_codigo`): dois códigos cujos
    nomes normalizados (`_normaliza_nome_fuzzy`) são "variações" entre si
    (`_sao_variacoes` -- match exato, prefixo por fronteira de palavra ex.
    "BPS4"/"BPS4 GESTAO CONTA", ou similaridade ≥ 0.88) são fundidos em um
    único grupo (`("grp", (códigos...))`). Do grupo, escolhe-se o nome de
    exibição preferindo os de cadastro oficial (`aproximado=False`) e, entre
    esses (ou na ausência deles, entre todos), o MAIS CURTO -- alinhado com a
    decisão do usuário de que é aceitável exibir a forma curta quando ela já
    identifica a empresa de forma inequívoca. Entradas resultantes de uma
    fusão carregam `alinhado=True`, sinalizado no template com o badge
    "⇄ nomes alinhados" -- convidando o usuário a abrir o drill-down até o
    nível de NF para conferir os históricos originais de cada código fundido
    (e reportar se, em algum caso, o agrupamento estiver errado).

    Retorna:
        {
          "por_grupo":      [{"id": <código da conta>, "label": <descrição oficial
                              ou "Conta X (sem descrição no plano de contas)">,
                              "totais": {comp: valor}, "total_geral", "fornecedores": [
                                  {"nome", "aproximado", "via_similaridade", "alinhado",
                                   "totais", "total_geral", "lancamentos": [
                                       {"numero": str, "data": "YYYY-MM-DD"|None,
                                        "historico": str|None, "totais": {comp: valor},
                                        "total_geral": float}, ...
                                   ]  # ordenado por (data, número) -- 3º nível de drill-down
                              ]}, ...],   # ordenado por total_geral (maior despesa primeiro)
                            # (chave do dict mantida como "por_grupo" por compat.
                            #  com o template/rota -- a dimensão agora é a conta)
          "por_fornecedor": [{"nome", "aproximado", "via_similaridade", "alinhado",
                              "totais", "total_geral",
                              "grupos": [{"id": <código da conta>, "label": <descrição>,
                                          "totais", "total_geral", "lancamentos": [...]}, ...]
                                          # mesma lista de NFs do nível acima -- 3º nível aqui também
                             }, ...],     # idem
                            # "alinhado" aqui é True se QUALQUER combinação (conta×fornecedor)
                            # que compõe esta linha veio de um grupo fundido (Passo 3.6)
          "competencias":            [...],   # apenas as que têm CT1 disponível
          "competencias_sem_ct1":    [...],   # competências pedidas sem Razão importado
          "totais_mes":              {comp: valor},
          "total_geral":             float,
          "tem_cadastro_fornecedores": bool,  # controla o aviso "nome aproximado" no template
        }
    """
    from collections import defaultdict

    conn = get_conn()

    # Quais dessas competências têm CT1 (Razão) disponível para esta empresa?
    comp_ct1 = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT competencia FROM razao WHERE empresa_id = ?",
            (empresa_id,)
        ).fetchall()
    }
    comps_ok    = [c for c in competencias if c in comp_ct1]
    comps_falta = [c for c in competencias if c not in comp_ct1]

    cadastro_rows = conn.execute(
        "SELECT cliente_cod, razao_social, nome_fantasia FROM fornecedores_cadastro"
    ).fetchall()
    cadastro = {r[0]: r[1] for r in cadastro_rows}
    tem_cadastro = bool(cadastro)

    # Índice para correspondência aproximada (fuzzy matching) -- nome oficial
    # normalizado (razão social OU nome fantasia) → (código, razão social).
    # Usado no Passo 4 para "tentar novamente" identificar fornecedores cujo
    # nome só foi possível extrair de forma aproximada (truncada) do histórico,
    # promovendo-os à razão social oficial quando a similaridade for alta --
    # ver `_resolver_por_similaridade()`.
    candidatos_fuzzy: dict[str, tuple[str, str]] = {}
    for cod, razao, fantasia in cadastro_rows:
        for nome_cand in (razao, fantasia):
            if nome_cand:
                chave_norm = _normaliza_nome_fuzzy(nome_cand)
                if chave_norm:
                    candidatos_fuzzy.setdefault(chave_norm, (cod, razao))
    _cache_fuzzy: dict[str, tuple[str, str] | None] = {}

    def _resolver_por_similaridade(nome: str | None):
        """
        "Tenta novamente" identificar a razão social oficial de um nome
        aproximado via correspondência aproximada (fuzzy matching) contra o
        cadastro mestre de fornecedores -- roda automaticamente, sem ação do
        usuário. Retorna (codigo, razao_social) em caso de correspondência
        com similaridade alta (cutoff 0.84), ou None. Resultado cacheado por
        nome (a mesma string aproximada aparece em muitos lançamentos).
        """
        if not nome or not candidatos_fuzzy:
            return None
        if nome not in _cache_fuzzy:
            chave_norm = _normaliza_nome_fuzzy(nome)
            achado = None
            if chave_norm in candidatos_fuzzy:
                achado = candidatos_fuzzy[chave_norm]
            else:
                proximos = _difflib.get_close_matches(chave_norm, candidatos_fuzzy.keys(), n=1, cutoff=0.84)
                if proximos:
                    achado = candidatos_fuzzy[proximos[0]]
            _cache_fuzzy[nome] = achado
        return _cache_fuzzy[nome]

    # Descrição oficial de cada conta (plano de contas) -- classificação
    # PRIMÁRIA desta análise: cada conta-código vira sua própria "linha"
    # (granularidade muito maior que o agrupamento por grupo DRE). Fonte:
    # tabela `contas`, alimentada pelo importador `plano_contas_parser`
    # (autoritativo) e/ou por importações anteriores de CT2.
    descricoes_conta = {
        r[0]: r[1] for r in conn.execute(
            "SELECT cod, descricao FROM contas WHERE empresa_id = ? AND descricao IS NOT NULL AND descricao != ''",
            (empresa_id,)
        ).fetchall()
    }

    linhas = []
    if comps_ok:
        placeholders = ",".join("?" * len(comps_ok))
        linhas = conn.execute(
            f"""
            SELECT competencia, conta_cod, historico, valor, parceiro_cod, data_lanc
            FROM razao
            WHERE empresa_id = ? AND conta_cod LIKE '4.%'
              AND competencia IN ({placeholders})
            """,
            [empresa_id, *comps_ok]
        ).fetchall()

    conn.close()

    # ── Passo 1: classifica (exclusão + filtro Custo×Despesa), extrai fornecedor ──
    # A classificação por GRUPO DRE (`classificar_conta`/`GRUPO_LABELS`) é usada
    # para (a) aplicar a exclusão de folha/encargos/pró-labore e (b) aplicar o
    # filtro `tipo` (Custo × Despesa) -- mas NÃO é mais a dimensão PRIMÁRIA de
    # classificação desta análise, que passou a ser a CONTA CONTÁBIL em si
    # (código + descrição oficial do plano de contas), bem mais granular que o
    # "balde" de grupo DRE (ex.: "SERV DE INFORMATICA" em vez de
    # "Serviço Contratado (Custo)").
    pre = []   # [(competencia, conta_cod, codigo|None, nome_extraido|None, numero_nf|None, historico, data_lanc, valor)]
    nome_por_codigo: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for comp, conta_cod, hist, valor, codigo, data_lanc in linhas:
        if not valor:
            continue
        grupo_dre = classificar_conta(conta_cod)
        if grupo_dre in GRUPOS_EXCLUIDOS_DESPESA:
            continue
        eh_custo = grupo_dre in GRUPOS_CUSTO
        if tipo == "custo" and not eh_custo:
            continue
        if tipo == "despesa" and eh_custo:
            continue
        numero_nf, nome_extraido = _extrair_nf_fornecedor(hist)
        if codigo and nome_extraido:
            nome_por_codigo[codigo][nome_extraido] += 1
        pre.append((comp, conta_cod, codigo or None, nome_extraido, numero_nf, hist, data_lanc, valor))

    # ── Passo 2: nome canônico por código (mais frequente; empate → mais longo) ──
    canonico_por_codigo = {
        codigo: max(contagem.items(), key=lambda kv: (kv[1], len(kv[0])))[0]
        for codigo, contagem in nome_por_codigo.items()
    }

    # ── Passo 3: lookup nome → código, para resgatar linhas sem código ──────────
    nome_para_codigo = {}
    for codigo, contagem in nome_por_codigo.items():
        for nome in contagem:
            nome_para_codigo.setdefault(nome, codigo)

    # ── Passo 3.5: "nome base" de cada código -- cadastro oficial > identificado
    #               por similaridade > nome canônico aproximado -- centraliza a
    #               lógica antes repetida em cada ramo do Passo 4, e serve de
    #               insumo para o agrupamento de re-cadastros do Passo 3.6 ──────
    nome_base_por_codigo: dict[str, tuple[str, bool, bool]] = {}   # codigo -> (nome, aproximado, via_similaridade)
    for codigo, nome_canon in canonico_por_codigo.items():
        if codigo in cadastro:
            nome_base_por_codigo[codigo] = (cadastro[codigo], False, False)
        else:
            achado = _resolver_por_similaridade(nome_canon)
            if achado:
                nome_base_por_codigo[codigo] = (achado[1], False, True)
            else:
                nome_base_por_codigo[codigo] = (nome_canon, True, False)

    # ── Passo 3.6: agrupa CÓDIGOS DIFERENTES cujo nome final é variação do
    #               mesmo fornecedor -- ex. "BPS4" (cód. 43220141) e "BPS4
    #               GESTAO CONTA" (cód. 62660141): mesmo prestador, re-cadastrado
    #               no Protheus sob código novo (valores e histórico idênticos
    #               entre os meses confirmam). Alinha a exibição sob um único
    #               nome -- prioriza a razão social oficial (se algum código do
    #               grupo estiver no cadastro mestre); na ausência, usa o nome
    #               mais curto (alinhamento solicitado pelo usuário -- nomes
    #               truncados costumam ser prefixo do nome completo). Roda
    #               automaticamente, independente do cadastro estar importado.
    clusters: list[dict] = []
    for codigo, (nome, aprox, via_sim) in nome_base_por_codigo.items():
        nome_norm = _normaliza_nome_fuzzy(nome)
        destino = next((cl for cl in clusters if any(_sao_variacoes(nome_norm, n) for n in cl["nomes_norm"])), None)
        if destino is None:
            destino = {"codigos": [], "nomes_norm": [], "candidatos": []}
            clusters.append(destino)
        destino["codigos"].append(codigo)
        destino["nomes_norm"].append(nome_norm)
        destino["candidatos"].append((nome, aprox, via_sim))

    grupo_por_codigo: dict[str, tuple] = {}
    for cl in clusters:
        if len(cl["codigos"]) <= 1:
            continue
        chave_grupo = ("grp", tuple(sorted(cl["codigos"])))
        oficiais   = [c for c in cl["candidatos"] if not c[1]]
        escolhidos = oficiais or cl["candidatos"]
        nome_esc, aprox_esc, via_esc = min(escolhidos, key=lambda c: len(c[0]))
        for cod in cl["codigos"]:
            grupo_por_codigo[cod] = (chave_grupo, nome_esc, aprox_esc, via_esc)

    def _resolve_por_codigo(codigo: str, fallback_nome: str | None):
        """Resolve (chave, nome, aproximado, via_similaridade) para um código
        já confirmado -- usa o agrupamento de re-cadastro (3.6) quando existir,
        senão o nome base individual do código (3.5)."""
        if codigo in grupo_por_codigo:
            return grupo_por_codigo[codigo]
        nome, aprox, via_sim = nome_base_por_codigo.get(codigo, (fallback_nome or _SEM_FORNECEDOR, True, False))
        return ("cod", codigo), nome, aprox, via_sim

    # ── Passo 4: resolve a identidade final do fornecedor de cada linha e
    #             agrega por (conta_cod, fornecedor) -- base única p/ as 2 visões ──
    agregados: dict[tuple, dict] = {}
    for comp, conta_cod, codigo, nome_extraido, numero_nf, hist, data_lanc, valor in pre:
        aproximado = True
        via_similaridade = False
        if codigo:
            chave, nome, aproximado, via_similaridade = _resolve_por_codigo(codigo, nome_extraido)
        elif nome_extraido and nome_extraido in nome_para_codigo:
            chave, nome, aproximado, via_similaridade = _resolve_por_codigo(nome_para_codigo[nome_extraido], nome_extraido)
        elif nome_extraido:
            # "Tenta novamente" identificar a razão social oficial via fuzzy
            # matching ANTES de cair no nome aproximado puro -- se achar, passa
            # a agrupar pelo código oficial encontrado (consolidação melhor).
            achado = _resolver_por_similaridade(nome_extraido)
            if achado:
                cod_fuzzy, nome = achado
                chave, aproximado, via_similaridade = ("cod", cod_fuzzy), False, True
            else:
                chave, nome = ("nome", nome_extraido), nome_extraido
        else:
            chave, nome, aproximado = ("sem_forn",), _SEM_FORNECEDOR, False

        item = agregados.setdefault((conta_cod, chave), {
            "nome": nome, "aproximado": aproximado, "via_similaridade": via_similaridade,
            "alinhado": chave[0] == "grp",   # nome alinhado entre 2+ códigos de cadastro (Passo 3.6 -- ex. re-cadastro)
            "totais": {}, "lancamentos": {},
        })
        item["totais"][comp] = item["totais"].get(comp, 0.0) + valor
        # Preserva a melhor identificação já vista para esta combinação
        # (oficial/similaridade > aproximado mais completo)
        if not aproximado:
            item["nome"], item["aproximado"], item["via_similaridade"] = nome, False, via_similaridade
        elif item["aproximado"] and len(nome) > len(item["nome"]):
            item["nome"] = nome

        # 3º nível de drill-down: Nota Fiscal (ou lançamento sem NF identificável)
        chave_nf = numero_nf or f"_sem_nf_{(hist or '')[:40]}"
        nf = item["lancamentos"].setdefault(
            chave_nf, {"numero": numero_nf or _SEM_NF, "data": data_lanc, "historico": hist, "totais": {}}
        )
        nf["totais"][comp] = nf["totais"].get(comp, 0.0) + valor
        if not nf["data"] and data_lanc:
            nf["data"] = data_lanc

    # ── Passo 5: monta as duas visões de pivot a partir da mesma base agregada ──
    # "por_grupo" manteve o nome (o template/rota dependem dessa chave do
    # retorno), mas a dimensão agora é a CONTA CONTÁBIL -- "id" = código da
    # conta, "label" = descrição oficial do plano de contas (fallback para o
    # próprio código, sinalizando ausência no plano, quando não cadastrada).
    por_grupo: dict[str, dict]      = {}
    por_fornecedor: dict[tuple, dict] = {}

    def _rotulo_conta(cod: str) -> str:
        desc = descricoes_conta.get(cod)
        return f"{desc} ({cod})" if desc else f"Conta {cod} (sem descrição no plano de contas)"

    for (conta_cod, chave), dados in agregados.items():
        total_linha = sum(dados["totais"].values())
        rotulo = _rotulo_conta(conta_cod)

        # Monta a lista de Notas Fiscais (3º nível de drill-down), ordenada por
        # (data, número) -- MESMA lista compartilhada pelas duas visões (a base
        # agregada é única; só a organização em árvore Conta↔Fornecedor muda).
        lancamentos = []
        for info in dados["lancamentos"].values():
            lancamentos.append({
                "numero":      info["numero"],
                "data":        info["data"],
                "historico":   info["historico"],
                "totais":      info["totais"],
                "total_geral": sum(info["totais"].values()),
            })
        lancamentos.sort(key=lambda x: (x["data"] or "", x["numero"] or ""))

        g = por_grupo.setdefault(conta_cod, {
            "id": conta_cod, "label": rotulo,
            "totais": {}, "fornecedores": [],
        })
        for comp, v in dados["totais"].items():
            g["totais"][comp] = g["totais"].get(comp, 0.0) + v
        g["fornecedores"].append({
            "nome": dados["nome"], "aproximado": dados["aproximado"],
            "via_similaridade": dados.get("via_similaridade", False),
            "alinhado": dados.get("alinhado", False),
            "totais": dados["totais"], "total_geral": total_linha,
            "lancamentos": lancamentos,
        })

        f = por_fornecedor.setdefault(chave, {
            "nome": dados["nome"], "aproximado": dados["aproximado"],
            "via_similaridade": dados.get("via_similaridade", False),
            "alinhado": dados.get("alinhado", False),
            "totais": {}, "grupos": [],
        })
        for comp, v in dados["totais"].items():
            f["totais"][comp] = f["totais"].get(comp, 0.0) + v
        if not dados["aproximado"]:
            f["nome"], f["aproximado"] = dados["nome"], False
            f["via_similaridade"] = dados.get("via_similaridade", False)
        f["alinhado"] = f.get("alinhado", False) or dados.get("alinhado", False)
        f["grupos"].append({
            "id": conta_cod, "label": rotulo,
            "totais": dados["totais"], "total_geral": total_linha,
            "lancamentos": lancamentos,
        })

    lista_grupos = []
    for conta_cod, dados in por_grupo.items():
        dados["fornecedores"].sort(key=lambda x: x["total_geral"])   # maior despesa (mais negativo) primeiro
        lista_grupos.append({**dados, "total_geral": sum(dados["totais"].values())})
    lista_grupos.sort(key=lambda x: x["total_geral"])

    lista_fornecedores = []
    for _chave, dados in por_fornecedor.items():
        dados["grupos"].sort(key=lambda x: x["total_geral"])
        lista_fornecedores.append({**dados, "total_geral": sum(dados["totais"].values())})
    lista_fornecedores.sort(key=lambda x: x["total_geral"])

    totais_mes  = {comp: sum(g["totais"].get(comp, 0.0) for g in lista_grupos) for comp in comps_ok}
    total_geral = sum(totais_mes.values())

    return {
        "por_grupo":                 lista_grupos,
        "por_fornecedor":            lista_fornecedores,
        "competencias":              comps_ok,
        "competencias_sem_ct1":      comps_falta,
        "totais_mes":                totais_mes,
        "total_geral":               total_geral,
        "tem_cadastro_fornecedores": tem_cadastro,
    }


# ─── FORMATAÇÃO ──────────────────────────────────────────────────────────────

def fmt_brl(valor: float) -> str:
    """Formata sem centavos: 6717455.81 → '6.717.456'  |  -1234 → '(1.234)'"""
    neg = valor < 0
    s = f"{round(abs(valor)):,}".replace(",", ".")
    return f"({s})" if neg else s


def pct_rob(valor: float, rob: float) -> str:
    """Percentual sobre ROB: '14,3%'"""
    if not rob:
        return "—"
    return f"{valor / rob * 100:.1f}%".replace(".", ",")


def variacao_pct(atual: float, anterior: float) -> tuple:
    """Retorna (delta_valor, pct_str, sinal) ou (None, '—', '')."""
    if not anterior:
        return None, "—", ""
    delta = atual - anterior
    pct   = delta / abs(anterior) * 100
    sinal = "pos" if delta >= 0 else "neg"
    return delta, f"{pct:.1f}%".replace(".", ","), sinal


# ─── TESTE RÁPIDO ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    comp = "2026-04"
    print(f"\n=== AJUSTE EP — {comp} ===")
    aj = calcular_ajuste(comp)
    print(f"  OUTROS_OP Ajuste: {fmt_brl(aj['OUTROS_OP'])}")
    print(f"  LAIR Ajuste:      {fmt_brl(aj['LAIR'])}")

    print(f"\n=== CONSOLIDADO c/ Ajuste — {comp} ===")
    todas = calcular_todas_empresas(comp)
    cons  = todas["consolidado"]
    for lid, lbl, _, _ in DRE_META:
        v = cons.get(lid, 0.0)
        print(f"  {lbl:<45} {fmt_brl(v):>15}  {pct_rob(v, cons['ROB'])}")

    print(f"\n=== DRE MENSAL CONSOLIDADO ===")
    mensal = calcular_dre_mensal("consolidado", ["2026-01","2026-02","2026-03","2026-04"])
    print(f"  {'Linha':<30} {'Jan':>12} {'Fev':>12} {'Mar':>12} {'Abr':>12}")
    for lid, lbl, _, _ in DRE_META:
        if lid == "EBITDA":
            continue
        row = f"  {lbl[:30]:<30}"
        for comp in ["2026-01","2026-02","2026-03","2026-04"]:
            row += f" {fmt_brl(mensal[comp].get(lid, 0)):>12}"
        print(row)
