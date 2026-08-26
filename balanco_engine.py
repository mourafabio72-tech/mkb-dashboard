"""
balanco_engine.py — MKB-Dashboard

Balanço Patrimonial a partir do balancete mensal (tabela `balancete`,
saldo_atual assinado: C = +, D = -). Regras validadas contra o
"MKB - BALANCETE 05.2026.xlsx":

- Soma apenas contas-FOLHA (analíticas) sob cada prefixo — o balancete
  também guarda as sintéticas, que duplicariam a soma.
- Cada conta-folha cai em UMA linha só: vence o prefixo mais longo que casa
  (mesma regra do de-para da DRE), então mapeamento novo mais específico
  reclassifica sem tirar a conta da linha antiga na mão.
- Linhas do ATIVO exibem -saldo (devedoras viram positivas; a depreciação,
  credora, sai negativa sozinha).
- Linhas do PASSIVO/PL exibem +saldo.
- "Lucro (Prejuízo) do Exercício" é apurado por diferença patrimonial:
  Ativo − (Passivo + PL mapeado) = -(Σ classe 1 + Σ classe 2). O balancete
  do Protheus não zera as contas de resultado, então a figura de fechamento
  é a apuração correta do resultado ainda não transferido ao PL.
- Contas 1.x/2.x fora do de-para aparecem em "Outras contas (não mapeadas)"
  para nunca fecharem o balanço com furo silencioso. A tela /de-para lista
  essas contas uma a uma e grava o vínculo em `balanco_map_custom`, que
  estende/sobrepõe a estrutura padrão abaixo.
"""

from __future__ import annotations

# ─── BLOCOS DO BALANÇO ───────────────────────────────────────────────────────
# (código, rótulo, sinal de exibição). Ativo mostra -saldo; passivo/PL, +saldo.

BLOCOS = [
    ("AC",   "Ativo Circulante",       -1),
    ("ANC",  "Ativo Não Circulante",   -1),
    ("PERM", "Ativo Permanente",       -1),
    ("PC",   "Passivo Circulante",     +1),
    ("PNC",  "Passivo Não Circulante", +1),
    ("PL",   "Patrimônio Líquido",     +1),
]

BLOCO_LABELS = {cod: label for cod, label, _ in BLOCOS}
BLOCO_SINAL  = {cod: sinal for cod, _, sinal in BLOCOS}
BLOCOS_ATIVO = ("AC", "ANC", "PERM")


# ─── DE-PARA PADRÃO (prefixo de conta → linha do balanço) ────────────────────
# Estende-se pela tela /de-para (tabela balanco_map_custom), não editando aqui.

ESTRUTURA_BASE = {
    "AC": [
        ("Caixa e Equivalentes de Caixa",        ["1.1.1"]),
        ("Contas a Receber",                     ["1.1.2"]),
        ("Créditos sobre Folha",                 ["1.1.3.02"]),
        ("Administração de Bens de Terceiros",   ["1.1.3.03"]),
        ("Tributos a Recuperar",                 ["1.1.3.04"]),
        ("Valores e Créditos Diversos",          ["1.1.3.05", "1.1.6"]),
        ("Despesas do Exercício Seguinte",       ["1.1.4", "1.1.5"]),
    ],
    "ANC": [
        ("Parcelamentos RFB",                    ["1.2.1.01.01"]),
        ("Adiantamentos a Pessoas Ligadas",      ["1.2.1.01.02", "1.2.1.01.03"]),
        ("Despesas Diversas a Apropriar",        ["1.2.1.01.04"]),
    ],
    "PERM": [
        ("Imobilizado",                          ["1.2.3.01", "1.2.4"]),
        ("(-) Depreciação Acumulada",            ["1.2.5.01.99"]),
    ],
    "PC": [
        ("Empréstimos e Financiamentos",         ["2.1.1.01.08.001"]),
        ("Contas a Pagar",                       ["2.1.2", "2.1.5"]),
        ("Impostos sobre o Faturamento",         ["2.1.3.01", "2.1.3.03", "2.1.3.04"]),
        ("Impostos e Contribuições Retidos",     ["2.1.3.02"]),
        ("Obrigações e Provisões Trabalhistas",  ["2.1.4"]),
        ("Parcelamentos Fiscais",                ["2.1.3.05"]),
    ],
    "PNC": [
        ("Empréstimos e Financiamentos",         ["2.2.3"]),
        ("Adiantamentos a Pessoas Ligadas",      ["2.2.1"]),
        ("Parcelamentos Tributários",            ["2.2.4"]),
        ("Obrigações Fiscais",                   ["2.2.6"]),
    ],
    "PL": [
        ("Capital Social",                       ["2.3.1"]),
        ("Lucro (Prejuízo) de Períodos Anteriores", ["2.3.4", "2.3.5", "2.9"]),
    ],
}


# ─── DE-PARA CUSTOMIZADO (banco) ─────────────────────────────────────────────

def _norm_prefixo(p: str) -> str:
    """'1.1.3.05.' e ' 1.1.3.05 ' viram '1.1.3.05' — o casamento aqui é por
    nível de conta, não por texto solto (a tela da DRE aceita ponto no fim)."""
    return (p or "").strip().strip(".").strip()


def custom_map(conn) -> list[tuple[str, str, str]]:
    """[(prefixo, bloco, linha)] gravados pela tela /de-para. Silencioso quando
    a tabela ainda não existe (banco antigo, antes de criar_schema rodar)."""
    try:
        tem = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='balanco_map_custom'"
        ).fetchone()
        if not tem:
            return []
        return [
            (_norm_prefixo(r[0]), r[1], r[2])
            for r in conn.execute(
                "SELECT prefixo, bloco, linha FROM balanco_map_custom ORDER BY prefixo"
            ).fetchall()
        ]
    except Exception:
        return []


def montar_mapa(conn) -> tuple[dict, list]:
    """Funde a estrutura padrão com o de-para customizado.

    Devolve (mapa, ordem):
      mapa  = {prefixo: (bloco, linha)}
      ordem = [(bloco, linha)] na ordem de exibição — linhas padrão primeiro,
              linhas criadas pelo usuário no fim do respectivo bloco.
    """
    mapa: dict[str, tuple[str, str]] = {}
    ordem: list[tuple[str, str]] = []

    for bloco, _label, _sinal in BLOCOS:
        for linha, prefixos in ESTRUTURA_BASE.get(bloco, []):
            ordem.append((bloco, linha))
            for p in prefixos:
                mapa[_norm_prefixo(p)] = (bloco, linha)

    for prefixo, bloco, linha in custom_map(conn):
        if bloco not in BLOCO_LABELS or not prefixo or not linha:
            continue
        mapa[prefixo] = (bloco, linha)          # custom sobrepõe o padrão
        if (bloco, linha) not in ordem:
            ordem.append((bloco, linha))        # rótulo novo = linha nova

    return mapa, ordem


def linhas_disponiveis(conn) -> dict[str, list[str]]:
    """{bloco: [linha, ...]} na ordem de exibição — alimenta o seletor da tela
    /de-para (optgroup por bloco)."""
    _, ordem = montar_mapa(conn)
    out: dict[str, list[str]] = {cod: [] for cod, _l, _s in BLOCOS}
    for bloco, linha in ordem:
        out.setdefault(bloco, []).append(linha)
    return out


def _classificador(mapa: dict):
    """Fecha sobre o mapa e devolve conta → (bloco, linha) | None.
    Prefixo mais longo vence, então cada conta cai em uma linha só."""
    prefixos = sorted(mapa.items(), key=lambda kv: len(kv[0]), reverse=True)

    def classificar(cod: str):
        for p, destino in prefixos:
            if cod == p or cod.startswith(p + "."):
                return destino
        return None

    return classificar


# ─── MOTOR ───────────────────────────────────────────────────────────────────

def _saldos_folha(rows) -> dict:
    """{conta: saldo} apenas das contas analíticas (folha)."""
    saldos = {str(r["conta_cod"]).strip(): float(r["saldo_atual"] or 0) for r in rows}
    sinteticas = set()
    for conta in saldos:
        partes = conta.split(".")
        for i in range(1, len(partes)):
            sinteticas.add(".".join(partes[:i]))
    return {c: v for c, v in saldos.items() if c not in sinteticas}


def _grupo(por_linha: dict, ordem: list, bloco: str) -> dict:
    sinal = BLOCO_SINAL[bloco]
    linhas = [
        (linha, sinal * por_linha.get((bloco, linha), 0.0))
        for b, linha in ordem if b == bloco
    ]
    return {"linhas": linhas, "total": sum(v for _, v in linhas)}


def montar_balanco(conn, empresa_id: int, competencia: str) -> dict | None:
    rows = conn.execute(
        "SELECT conta_cod, saldo_atual FROM balancete "
        "WHERE empresa_id = ? AND competencia = ?",
        (empresa_id, competencia),
    ).fetchall()
    if not rows:
        return None

    folhas = _saldos_folha(rows)
    s1 = sum(v for c, v in folhas.items() if c.startswith("1"))
    s2 = sum(v for c, v in folhas.items() if c.startswith("2"))

    mapa, ordem = montar_mapa(conn)
    classificar = _classificador(mapa)

    por_linha: dict[tuple[str, str], float] = {}
    for cod, saldo in folhas.items():
        destino = classificar(cod)
        if destino:
            por_linha[destino] = por_linha.get(destino, 0.0) + saldo

    ac   = _grupo(por_linha, ordem, "AC")
    anc  = _grupo(por_linha, ordem, "ANC")
    perm = _grupo(por_linha, ordem, "PERM")
    pc   = _grupo(por_linha, ordem, "PC")
    pnc  = _grupo(por_linha, ordem, "PNC")
    pl   = _grupo(por_linha, ordem, "PL")

    # Resultado do exercício por diferença patrimonial (fechamento)
    lucro_exercicio = -(s1 + s2)

    # Contas fora do de-para (aparecem em vez de fechar com furo silencioso)
    ativo_mapeado   = ac["total"] + anc["total"] + perm["total"]
    passivo_mapeado = pc["total"] + pnc["total"] + pl["total"]
    ativo_nao_mapeado   = (-s1) - ativo_mapeado
    passivo_nao_mapeado = s2 - passivo_mapeado

    total_ativo = -s1
    anc_total = anc["total"] + perm["total"]
    pl_total = pl["total"] + lucro_exercicio
    total_passivo = pc["total"] + pnc["total"] + pl_total + passivo_nao_mapeado

    return {
        "competencia": competencia,
        "ativo_circulante": ac,
        "ativo_nao_circulante": anc,
        "ativo_permanente": perm,
        "ativo_nao_circulante_total": anc_total,
        "ativo_nao_mapeado": round(ativo_nao_mapeado, 2),
        "total_ativo": round(total_ativo, 2),
        "passivo_circulante": pc,
        "passivo_nao_circulante": pnc,
        "patrimonio_liquido": pl,
        "lucro_exercicio": round(lucro_exercicio, 2),
        "pl_total": round(pl_total, 2),
        "passivo_nao_mapeado": round(passivo_nao_mapeado, 2),
        "total_passivo": round(total_passivo, 2),
        "diferenca": round(total_ativo - total_passivo, 2),
    }


def competencias_com_balancete(conn, empresa_id: int) -> list:
    return [
        r["competencia"] for r in conn.execute(
            "SELECT DISTINCT competencia FROM balancete "
            "WHERE empresa_id = ? ORDER BY competencia",
            (empresa_id,),
        ).fetchall()
    ]


def contas_fora_do_de_para(conn) -> list[dict]:
    """Contas patrimoniais (1.x/2.x) do balancete mais recente de cada empresa
    que não casam com nenhum prefixo — o "Outras contas (fora do de-para)" do
    balanço, aberto conta a conta para a tela /de-para poder vincular."""
    try:
        tem = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='balancete'"
        ).fetchone()
        if not tem:
            return []
    except Exception:
        return []

    mapa, _ = montar_mapa(conn)
    classificar = _classificador(mapa)

    ultimas = conn.execute(
        "SELECT empresa_id, MAX(competencia) FROM balancete GROUP BY empresa_id"
    ).fetchall()

    out = []
    for empresa_id, competencia in ultimas:
        rows = conn.execute(
            "SELECT b.conta_cod, b.descricao, b.saldo_atual, e.sigla "
            "FROM balancete b JOIN empresas e ON e.id = b.empresa_id "
            "WHERE b.empresa_id = ? AND b.competencia = ?",
            (empresa_id, competencia),
        ).fetchall()
        folhas = _saldos_folha(rows)
        descr = {str(r["conta_cod"]).strip(): (r["descricao"] or "") for r in rows}
        sigla = rows[0]["sigla"] if rows else str(empresa_id)

        for cod, saldo in folhas.items():
            if not (cod.startswith("1") or cod.startswith("2")):
                continue
            if abs(saldo) <= 0.005 or classificar(cod):
                continue
            # Exibição na mesma convenção do balanço: ativo positivo, passivo +
            valor = -saldo if cod.startswith("1") else saldo
            out.append({
                "cod": cod,
                "descricao": descr.get(cod, ""),
                "valor": round(valor, 2),
                "empresa": sigla,
                "competencia": competencia,
                "lado": "Ativo" if cod.startswith("1") else "Passivo/PL",
            })

    out.sort(key=lambda x: -abs(x["valor"]))
    return out
