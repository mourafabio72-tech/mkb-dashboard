"""
balanco_engine.py — MKB-Dashboard

Balanço Patrimonial a partir do balancete mensal (tabela `balancete`,
saldo_atual assinado: C = +, D = -). Regras validadas contra o
"MKB - BALANCETE 05.2026.xlsx":

- Soma apenas contas-FOLHA (analíticas) sob cada prefixo — o balancete
  também guarda as sintéticas, que duplicariam a soma.
- Linhas do ATIVO exibem -saldo (devedoras viram positivas; a depreciação,
  credora, sai negativa sozinha).
- Linhas do PASSIVO/PL exibem +saldo.
- "Lucro (Prejuízo) do Exercício" é apurado por diferença patrimonial:
  Ativo − (Passivo + PL mapeado) = -(Σ classe 1 + Σ classe 2). O balancete
  do Protheus não zera as contas de resultado, então a figura de fechamento
  é a apuração correta do resultado ainda não transferido ao PL.
- Contas 1.x/2.x fora do de-para aparecem em "Outras contas (não mapeadas)"
  para nunca fecharem o balanço com furo silencioso.
"""

from __future__ import annotations

# ─── DE-PARA (prefixo de conta → linha do balanço) ───────────────────────────

ATIVO_CIRCULANTE = [
    ("Caixa e Equivalentes de Caixa",        ["1.1.1"]),
    ("Contas a Receber",                     ["1.1.2"]),
    ("Créditos sobre Folha",                 ["1.1.3.02"]),
    ("Administração de Bens de Terceiros",   ["1.1.3.03"]),
    ("Tributos a Recuperar",                 ["1.1.3.04"]),
    ("Valores e Créditos Diversos",          ["1.1.3.05", "1.1.6"]),
    ("Despesas do Exercício Seguinte",       ["1.1.4", "1.1.5"]),
]

ATIVO_NAO_CIRCULANTE = [
    ("Parcelamentos RFB",                    ["1.2.1.01.01"]),
    ("Adiantamentos a Pessoas Ligadas",      ["1.2.1.01.02", "1.2.1.01.03"]),
    ("Despesas Diversas a Apropriar",        ["1.2.1.01.04"]),
]

ATIVO_PERMANENTE = [
    ("Imobilizado",                          ["1.2.3.01", "1.2.4"]),
    ("(-) Depreciação Acumulada",            ["1.2.5.01.99"]),
]

PASSIVO_CIRCULANTE = [
    ("Empréstimos e Financiamentos",         ["2.1.1.01.08.001"]),
    ("Contas a Pagar",                       ["2.1.2", "2.1.5"]),
    ("Impostos sobre o Faturamento",         ["2.1.3.01", "2.1.3.03", "2.1.3.04"]),
    ("Impostos e Contribuições Retidos",     ["2.1.3.02"]),
    ("Obrigações e Provisões Trabalhistas",  ["2.1.4"]),
    ("Parcelamentos Fiscais",                ["2.1.3.05"]),
]

PASSIVO_NAO_CIRCULANTE = [
    ("Empréstimos e Financiamentos",         ["2.2.3"]),
    ("Adiantamentos a Pessoas Ligadas",      ["2.2.1"]),
    ("Parcelamentos Tributários",            ["2.2.4"]),
    ("Obrigações Fiscais",                   ["2.2.6"]),
]

PATRIMONIO_LIQUIDO = [
    ("Capital Social",                       ["2.3.1"]),
    ("Lucro (Prejuízo) de Períodos Anteriores", ["2.3.4", "2.3.5", "2.9"]),
]


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


def _soma(folhas: dict, prefixos: list) -> float:
    return sum(
        v for c, v in folhas.items()
        if any(c == p or c.startswith(p + ".") for p in prefixos)
    )


def _grupo(folhas: dict, estrutura: list, sinal: int) -> dict:
    linhas = [(nome, sinal * _soma(folhas, prefs)) for nome, prefs in estrutura]
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

    # Ativo (display = -saldo) / Passivo e PL (display = +saldo)
    ac   = _grupo(folhas, ATIVO_CIRCULANTE, -1)
    anc  = _grupo(folhas, ATIVO_NAO_CIRCULANTE, -1)
    perm = _grupo(folhas, ATIVO_PERMANENTE, -1)
    pc   = _grupo(folhas, PASSIVO_CIRCULANTE, +1)
    pnc  = _grupo(folhas, PASSIVO_NAO_CIRCULANTE, +1)
    pl   = _grupo(folhas, PATRIMONIO_LIQUIDO, +1)

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
