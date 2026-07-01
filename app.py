"""
app.py -- MKB-Dashboard  (porta 5001)
Dashboard gerencial do Grupo Markbuilding: DRE, IRPJ/CSLL, Endividamento Tributário.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash

from config import SECRET_KEY, PORT, DEBUG, EMPRESAS
from auth import login_required, admin_required, verificar_credenciais
from ingestion import get_conn, criar_schema, seed_empresas, importar, ler_template_dre, salvar_lancamentos
from importar_mes import importar_mes_completo
from razao_parser import importar_razao
from emprestimo_bancario_parser import importar_cronograma
from irpj_csll_parser import importar_irpj_csll
from endividamento_parser import importar_vinculacao
from dre_engine import (
    calcular_dre, calcular_consolidado, calcular_todas_empresas,
    calcular_dre_detalhada, calcular_dre_mensal, calcular_dre_mensal_detalhada,
    calcular_rob_por_segmento, calcular_top_custo, calcular_top_despesa, calcular_serie_mensal,
    calcular_todas_empresas_gerencial, calcular_dre_gerencial_mensal,
    calcular_dre_detalhada_gerencial, analisar_receita_clientes,
    analisar_despesas_fornecedores,
    fmt_brl, pct_rob, variacao_pct, DRE_META, DRE_META_GERENCIAL,
    GRUPOS_AGREGADOS_GER, montar_bridge_ebitda, montar_bridge_resultado_final,
    _tabela_lancamentos,
    contas_nao_classificadas, grupos_disponiveis, invalidar_prefixos, GRUPO_LABELS,
    conciliar_balancete, criar_ajustes_saldo,
)
from balancete_parser import importar_balancete

app = Flask(__name__)
app.secret_key = SECRET_KEY


@app.after_request
def _no_cache_html(resp):
    """Impede cache de páginas HTML (navegador/proxy) para que dados dinâmicos
    -- ex.: validação após recalcular ajustes -- sempre venham frescos."""
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
    return resp


# --- FILTROS JINJA2 ----------------------------------------------------------

@app.template_filter("brl")
def filtro_brl(valor):
    try:
        return fmt_brl(float(valor))
    except Exception:
        return "—"


@app.template_filter("pct")
def filtro_pct(valor, rob=None):
    try:
        if rob is None:
            return "—"
        return pct_rob(float(valor), float(rob))
    except Exception:
        return "—"


# --- CONTEXT PROCESSOR -------------------------------------------------------

@app.context_processor
def inject_globals():
    return {
        "now": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "EMPRESAS": EMPRESAS,
    }


# --- HELPERS -----------------------------------------------------------------

def _competencias_disponiveis() -> list:
    try:
        conn = get_conn()
        # Usa a view v_lancamentos (Razão CT1 agregado + CT2) quando existir,
        # para que a DRE/dashboard gerem só com o Razão importado — sem precisar
        # subir o "Template DRE Protheus". O de-para conta→linha já é feito por
        # prefixo em account_map.json (ver dre_engine.classificar_conta).
        tbl = _tabela_lancamentos(conn)
        rows = conn.execute(
            f"SELECT DISTINCT competencia FROM {tbl} ORDER BY competencia"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def _mes_label(competencia: str) -> str:
    meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    try:
        ano, mes = competencia.split("-")
        return f"{meses[int(mes)-1]}/{ano}"
    except Exception:
        return competencia


def _ref_competencia_razao(conn, empresa_id: int) -> str:
    """
    Mês ANTERIOR ao último competência do Razão da empresa (o último mês do
    Razão pode ainda não estar fechado/conciliado) -- cai para "hoje" se a
    empresa não tiver Razão importado ainda. Mesmo critério usado em
    /endividamento-bancario e no resumo do dashboard.
    """
    r_max = conn.execute(
        "SELECT MAX(competencia) FROM razao WHERE empresa_id=?", (empresa_id,)
    ).fetchone()
    if r_max and r_max[0]:
        ano_ref, mes_ref = int(r_max[0][:4]), int(r_max[0][5:7])
        mes_ref -= 1
        if mes_ref < 1:
            mes_ref = 12
            ano_ref -= 1
        return f"{ano_ref}-{mes_ref:02d}"
    hoje = datetime.now()
    return f"{hoje.year}-{hoje.month:02d}"


def _resumo_endividamento_tributario(empresa_id: int) -> dict:
    """
    Saldo devedor atual + desembolso mensal do Endividamento Tributário de
    uma empresa (snapshot mais recente de `parcelamentos`, saldo via Razão
    em tempo real) -- versão resumida da rota /endividamento, usada no
    resumo do dashboard (sem a série mensal completa).
    """
    conn = get_conn()
    competencias_disp = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT competencia_ref FROM parcelamentos WHERE empresa_id=? ORDER BY competencia_ref",
            (empresa_id,)
        ).fetchall()
    ]
    if not competencias_disp:
        conn.close()
        return {"total_endividamento": 0.0, "desembolso_total": 0.0}

    comp_ref = competencias_disp[-1]
    parcelamentos = conn.execute(
        """
        SELECT tributo, conta_cp, conta_lp, desembolso_mensal, saldo_contabilidade_snapshot
        FROM parcelamentos WHERE empresa_id=? AND competencia_ref=?
        """,
        (empresa_id, comp_ref)
    ).fetchall()

    grupos_conta: dict[tuple, list] = {}
    for p in parcelamentos:
        chave = (p["conta_cp"], p["conta_lp"])
        grupos_conta.setdefault(chave, []).append(p["tributo"])

    peso_por_tributo: dict[str, float] = {}
    for p in parcelamentos:
        chave = (p["conta_cp"], p["conta_lp"])
        membros = grupos_conta[chave]
        if len(membros) == 1:
            peso_por_tributo[p["tributo"]] = 1.0
            continue
        soma_snapshot = sum(
            (pp["saldo_contabilidade_snapshot"] or 0.0)
            for pp in parcelamentos if pp["tributo"] in membros
        )
        snap = p["saldo_contabilidade_snapshot"] or 0.0
        peso_por_tributo[p["tributo"]] = (
            snap / soma_snapshot if soma_snapshot else 1.0 / len(membros)
        )

    def _saldo_atual_conta(conta):
        if not conta:
            return 0.0
        r = conn.execute(
            "SELECT saldo_atual FROM razao WHERE empresa_id=? AND conta_cod=? "
            "AND saldo_atual IS NOT NULL ORDER BY competencia DESC, data_lanc DESC, id DESC LIMIT 1",
            (empresa_id, conta)
        ).fetchone()
        return r["saldo_atual"] if r else 0.0

    total_endividamento = 0.0
    for p in parcelamentos:
        peso = peso_por_tributo[p["tributo"]]
        saldo = _saldo_atual_conta(p["conta_cp"]) + (_saldo_atual_conta(p["conta_lp"]) if p["conta_lp"] else 0.0)
        total_endividamento += saldo * peso

    desembolso_total = sum(p["desembolso_mensal"] or 0 for p in parcelamentos)
    conn.close()
    return {"total_endividamento": total_endividamento, "desembolso_total": desembolso_total}


def _resumo_endividamento_bancario(empresa_id: int) -> dict:
    """
    Saldo a pagar + valor da próxima parcela do Endividamento Bancário de
    uma empresa, somado entre todos os contratos -- versão resumida da rota
    /endividamento-bancario, usada no resumo do dashboard.
    """
    conn = get_conn()
    criar_schema(conn)
    emprestimos = conn.execute(
        "SELECT * FROM emprestimos_bancarios WHERE empresa_id=?", (empresa_id,)
    ).fetchall()
    if not emprestimos:
        conn.close()
        return {"saldo_a_pagar": 0.0, "valor_parcela_atual": 0.0}

    def _saldo_atual(conta):
        if not conta:
            return None
        r = conn.execute(
            "SELECT saldo_atual FROM razao WHERE empresa_id=? AND conta_cod=? "
            "AND saldo_atual IS NOT NULL ORDER BY competencia DESC, data_lanc DESC, id DESC LIMIT 1",
            (empresa_id, conta)
        ).fetchone()
        return r["saldo_atual"] if r else None

    ref_competencia = _ref_competencia_razao(conn, empresa_id)

    saldo_total = 0.0
    parcela_total = 0.0
    for e in emprestimos:
        parcelas = conn.execute(
            "SELECT * FROM emprestimos_parcelas WHERE emprestimo_id=? ORDER BY numero_parcela",
            (e["id"],)
        ).fetchall()

        s_cp_p = _saldo_atual(e["conta_cp_principal"])
        s_cp_j = _saldo_atual(e["conta_cp_juros"])
        s_lp_p = _saldo_atual(e["conta_lp_principal"])
        s_lp_j = _saldo_atual(e["conta_lp_juros"])
        tem_razao = any(v is not None for v in (s_cp_p, s_cp_j, s_lp_p, s_lp_j))

        if tem_razao:
            saldo = (s_cp_p or 0) + (s_cp_j or 0) + (s_lp_p or 0) + (s_lp_j or 0)
            futuras = [p for p in parcelas if p["competencia"] > ref_competencia]
            parcela = futuras[0]["valor_parcela"] if futuras else (parcelas[-1]["valor_parcela"] if parcelas else 0.0)
        elif parcelas:
            pagas = [p for p in parcelas if p["competencia"] <= ref_competencia]
            futuras = [p for p in parcelas if p["competencia"] > ref_competencia]
            saldo = pagas[-1]["saldo_devedor"] if pagas else e["valor_contratado"]
            parcela = futuras[0]["valor_parcela"] if futuras else (pagas[-1]["valor_parcela"] if pagas else 0.0)
        else:
            saldo, parcela = 0.0, 0.0

        saldo_total += saldo or 0.0
        parcela_total += parcela or 0.0

    conn.close()
    return {"saldo_a_pagar": saldo_total, "valor_parcela_atual": parcela_total}


def _pagamentos_mensais_tributario(empresa_id: int, competencias: list) -> dict:
    """
    Valor efetivamente PAGO (débito na conta CP, ponderado pelo peso de
    rateio) por mês, do Endividamento Tributário de uma empresa -- mesma
    lógica de `_pago`/`totais_pagos_por_mes` da rota /endividamento, só que
    para uma lista arbitrária de competências (usado na série do dashboard).
    """
    resultado = {c: 0.0 for c in competencias}
    conn = get_conn()
    comp_ref_rows = conn.execute(
        "SELECT DISTINCT competencia_ref FROM parcelamentos WHERE empresa_id=? ORDER BY competencia_ref",
        (empresa_id,)
    ).fetchall()
    if not comp_ref_rows:
        conn.close()
        return resultado

    comp_ref = comp_ref_rows[-1][0]
    parcelamentos = conn.execute(
        "SELECT tributo, conta_cp, conta_lp, saldo_contabilidade_snapshot "
        "FROM parcelamentos WHERE empresa_id=? AND competencia_ref=?",
        (empresa_id, comp_ref)
    ).fetchall()

    grupos_conta: dict[tuple, list] = {}
    for p in parcelamentos:
        chave = (p["conta_cp"], p["conta_lp"])
        grupos_conta.setdefault(chave, []).append(p["tributo"])

    peso_por_tributo: dict[str, float] = {}
    for p in parcelamentos:
        chave = (p["conta_cp"], p["conta_lp"])
        membros = grupos_conta[chave]
        if len(membros) == 1:
            peso_por_tributo[p["tributo"]] = 1.0
            continue
        soma_snapshot = sum(
            (pp["saldo_contabilidade_snapshot"] or 0.0)
            for pp in parcelamentos if pp["tributo"] in membros
        )
        snap = p["saldo_contabilidade_snapshot"] or 0.0
        peso_por_tributo[p["tributo"]] = (
            snap / soma_snapshot if soma_snapshot else 1.0 / len(membros)
        )

    contas_cp_unicas = {p["conta_cp"] for p in parcelamentos}
    pago_por_conta_comp: dict[tuple, float] = {}
    if contas_cp_unicas:
        placeholders = ",".join("?" * len(contas_cp_unicas))
        rows = conn.execute(
            f"SELECT conta_cod, competencia, SUM(debito) as total_debito FROM razao "
            f"WHERE empresa_id=? AND conta_cod IN ({placeholders}) GROUP BY conta_cod, competencia",
            (empresa_id, *contas_cp_unicas)
        ).fetchall()
        for r in rows:
            pago_por_conta_comp[(r["conta_cod"], r["competencia"])] = r["total_debito"] or 0.0
    conn.close()

    for p in parcelamentos:
        peso = peso_por_tributo[p["tributo"]]
        for c in competencias:
            resultado[c] += pago_por_conta_comp.get((p["conta_cp"], c), 0.0) * peso
    return resultado


def _pagamentos_mensais_bancario(empresa_id: int, competencias: list) -> dict:
    """Valor da parcela (cronograma) por mês, do Endividamento Bancário de uma empresa."""
    resultado = {c: 0.0 for c in competencias}
    conn = get_conn()
    criar_schema(conn)
    emprestimo_ids = [r[0] for r in conn.execute(
        "SELECT id FROM emprestimos_bancarios WHERE empresa_id=?", (empresa_id,)
    ).fetchall()]
    if not emprestimo_ids:
        conn.close()
        return resultado

    placeholders = ",".join("?" * len(emprestimo_ids))
    rows = conn.execute(
        f"SELECT competencia, SUM(valor_parcela) as total FROM emprestimos_parcelas "
        f"WHERE emprestimo_id IN ({placeholders}) GROUP BY competencia",
        emprestimo_ids
    ).fetchall()
    conn.close()

    for r in rows:
        if r["competencia"] in resultado:
            resultado[r["competencia"]] += r["total"] or 0.0
    return resultado


app.jinja_env.globals["mes_label"] = _mes_label


# --- ROTA: HOME / DASHBOARD --------------------------------------------------

# --- LOGIN / LOGOUT ----------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha   = (request.form.get("senha")   or "").strip()
        next_url = request.form.get("next") or url_for("index")

        conn = get_conn()
        criar_schema(conn)
        dados_usuario = verificar_credenciais(conn, usuario, senha)
        conn.close()

        if dados_usuario:
            session.permanent = True
            session["usuario_logado"] = dados_usuario
            return redirect(next_url)
        return render_template("login.html", erro="Usuário ou senha incorretos.",
                               ultimo_usuario=usuario, next_url=next_url)
    next_url = request.args.get("next", "")
    if session.get("usuario_logado"):
        return redirect(next_url or url_for("index"))
    return render_template("login.html", erro=None, ultimo_usuario=None, next_url=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- ROTAS: USUÁRIOS (admin) -------------------------------------------------

@app.route("/usuarios")
@login_required
@admin_required
def usuarios():
    conn = get_conn()
    criar_schema(conn)
    lista = conn.execute(
        "SELECT id, usuario, nome, email, role, ativo, criado_em FROM usuarios ORDER BY criado_em"
    ).fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=lista)


@app.route("/usuarios/novo", methods=["GET", "POST"])
@login_required
@admin_required
def usuarios_novo():
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        nome    = (request.form.get("nome") or "").strip()
        email   = (request.form.get("email") or "").strip() or None
        senha   = (request.form.get("senha") or "").strip()
        role    = request.form.get("role", "leitura")
        role    = role if role in ("admin", "leitura") else "leitura"

        if not (usuario and nome and senha):
            flash("Preencha usuário, nome e senha.", "warning")
            return redirect(url_for("usuarios_novo"))
        if len(senha) < 6:
            flash("A senha precisa ter pelo menos 6 caracteres.", "warning")
            return redirect(url_for("usuarios_novo"))

        conn = get_conn()
        criar_schema(conn)
        try:
            conn.execute(
                "INSERT INTO usuarios (usuario, nome, email, senha_hash, role, ativo) VALUES (?,?,?,?,?,1)",
                (usuario, nome, email, generate_password_hash(senha), role),
            )
            conn.commit()
            flash(f"Usuário \"{usuario}\" criado ({role}).", "success")
        except sqlite3.IntegrityError:
            flash(f"Já existe um usuário com o login \"{usuario}\".", "danger")
        finally:
            conn.close()
        return redirect(url_for("usuarios"))

    return render_template("usuarios_novo.html")


@app.route("/usuarios/<int:usuario_id>/alternar", methods=["POST"])
@login_required
@admin_required
def usuarios_alternar(usuario_id):
    conn = get_conn()
    criar_schema(conn)
    row = conn.execute("SELECT ativo, usuario FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    if not row:
        flash("Usuário não encontrado.", "danger")
    else:
        novo_status = 0 if row["ativo"] else 1
        conn.execute("UPDATE usuarios SET ativo=? WHERE id=?", (novo_status, usuario_id))
        conn.commit()
        flash(
            f"Usuário \"{row['usuario']}\" {'reativado' if novo_status else 'desativado'}.",
            "success"
        )
    conn.close()
    return redirect(url_for("usuarios"))


# --- ROTAS PROTEGIDAS --------------------------------------------------------

@app.route("/")
@login_required
def index():
    todas_competencias = _competencias_disponiveis()

    # Filtra pelos meses selecionados via checkbox (GET ?meses=)
    meses_sel = request.args.getlist("meses")
    if meses_sel:
        competencias = [m for m in meses_sel if m in todas_competencias]
    else:
        competencias = todas_competencias  # default: todos

    if not competencias:
        competencias = todas_competencias

    ultima = competencias[-1] if competencias else None

    # KPIs do último mês selecionado + variação vs. mês anterior no conjunto
    kpis     = {}
    kpis_ant = {}
    if ultima:
        kpis = calcular_consolidado(ultima)
        # Mês anterior dentro dos selecionados
        idx = competencias.index(ultima)
        if idx > 0:
            kpis_ant = calcular_consolidado(competencias[idx - 1])

    # Resumo dos meses selecionados
    mensal_todos = calcular_dre_mensal("consolidado", competencias)

    # Calcula variação mês a mês para todas as competências
    vars_periodo = {}          # {comp: {linha: (delta, pct_str, sinal)}}
    for i, comp in enumerate(competencias):
        if i == 0:
            vars_periodo[comp] = {}
            continue
        ant = competencias[i - 1]
        vars_periodo[comp] = {
            lid: variacao_pct(
                mensal_todos[comp].get(lid, 0),
                mensal_todos[ant].get(lid, 0)
            )
            for lid, _, _, _ in DRE_META
        }

    # YTD acumulado (linhas de fluxo)
    ytd = {}
    for lid in ["ROB","DED","CPV","DADM","ENC_FIN","OUTROS_OP","IRPJ_CSLL"]:
        ytd[lid] = sum(mensal_todos[c].get(lid, 0) for c in competencias)
    from dre_engine import _aplicar_calc
    _aplicar_calc(ytd)

    # Dados para gráficos
    import json as _json
    grafico_serie    = calcular_serie_mensal(competencias)
    grafico_segmento = calcular_rob_por_segmento(competencias)
    grafico_custo    = calcular_top_custo(competencias, n=10)
    grafico_despesa  = calcular_top_despesa(competencias, n=10)

    # Resumo de Endividamento (Tributário + Bancário), MKB + Gnileb somados,
    # comparado à Receita Bruta consolidada acumulada (YTD) do período acima.
    end_trib_mkb     = _resumo_endividamento_tributario(EMPRESAS["mkb"]["id"])
    end_trib_gnileb  = _resumo_endividamento_tributario(EMPRESAS["gnileb"]["id"])
    end_banc_mkb     = _resumo_endividamento_bancario(EMPRESAS["mkb"]["id"])
    end_banc_gnileb  = _resumo_endividamento_bancario(EMPRESAS["gnileb"]["id"])

    divida_tributaria = end_trib_mkb["total_endividamento"] + end_trib_gnileb["total_endividamento"]
    divida_bancaria    = end_banc_mkb["saldo_a_pagar"] + end_banc_gnileb["saldo_a_pagar"]
    divida_total       = divida_tributaria + divida_bancaria

    desembolso_tributario = end_trib_mkb["desembolso_total"] + end_trib_gnileb["desembolso_total"]
    desembolso_bancario    = end_banc_mkb["valor_parcela_atual"] + end_banc_gnileb["valor_parcela_atual"]
    desembolso_total_geral = desembolso_tributario + desembolso_bancario

    rob_consolidado_ytd = ytd.get("ROB", 0) or 0
    pct_divida_rob = (divida_total / rob_consolidado_ytd * 100) if rob_consolidado_ytd else None

    resumo_endividamento = {
        "divida_tributaria": divida_tributaria,
        "divida_bancaria": divida_bancaria,
        "divida_total": divida_total,
        "desembolso_total": desembolso_total_geral,
        "rob_consolidado_ytd": rob_consolidado_ytd,
        "pct_divida_rob": pct_divida_rob,
    }

    # Série mensal: parcelas pagas (Tributário + Bancário) × Receita Bruta
    # ACUMULADA até aquele mês (Jan -> mês), consolidado MKB + Gnileb.
    pagos_trib_mkb = _pagamentos_mensais_tributario(EMPRESAS["mkb"]["id"], competencias)
    pagos_trib_gni = _pagamentos_mensais_tributario(EMPRESAS["gnileb"]["id"], competencias)
    pagos_banc_mkb = _pagamentos_mensais_bancario(EMPRESAS["mkb"]["id"], competencias)
    pagos_banc_gni = _pagamentos_mensais_bancario(EMPRESAS["gnileb"]["id"], competencias)

    serie_endividamento_mensal = []
    rob_acum = 0.0
    divida_acum = 0.0
    for c in competencias:
        rob_mes = mensal_todos[c].get("ROB", 0) or 0
        rob_acum += rob_mes
        valor_pago = (
            pagos_trib_mkb.get(c, 0.0) + pagos_trib_gni.get(c, 0.0)
            + pagos_banc_mkb.get(c, 0.0) + pagos_banc_gni.get(c, 0.0)
        )
        divida_acum += valor_pago
        pct = (valor_pago / rob_acum * 100) if rob_acum else None
        serie_endividamento_mensal.append({
            "competencia": c, "valor_pago": valor_pago,
            "divida_acumulada": divida_acum, "rob_mes": rob_mes, "pct": pct,
        })

    grafico_endividamento_valor = [round(l["valor_pago"]) for l in serie_endividamento_mensal]
    grafico_endividamento_pct   = [round(l["pct"], 1) if l["pct"] is not None else 0 for l in serie_endividamento_mensal]

    return render_template(
        "dashboard.html",
        todas_competencias=todas_competencias,
        competencias=competencias,
        ultima=ultima,
        kpis=kpis,
        kpis_ant=kpis_ant,
        ytd=ytd,
        resumo_endividamento=resumo_endividamento,
        serie_endividamento_mensal=serie_endividamento_mensal,
        dre_meta=DRE_META,
        fmt_brl=fmt_brl,
        pct_rob=pct_rob,
        variacao_pct=variacao_pct,
        # JSON para Chart.js
        grafico_serie=_json.dumps(grafico_serie),
        grafico_segmento=_json.dumps(grafico_segmento),
        grafico_custo=_json.dumps(grafico_custo),
        grafico_despesa=_json.dumps(grafico_despesa),
        grafico_endividamento_valor=_json.dumps(grafico_endividamento_valor),
        grafico_endividamento_pct=_json.dumps(grafico_endividamento_pct),
    )


# --- ROTA: DRE (OFICIAL ou GERENCIAL) ----------------------------------------

@app.route("/dre/<competencia>")
@login_required
def dre_resumida(competencia):
    competencias = _competencias_disponiveis()
    if not competencias:
        flash("Nenhum dado disponivel. Importe os arquivos primeiro.", "warning")
        return redirect(url_for("ingest"))

    if competencia not in competencias:
        competencia = competencias[-1]

    tipo = request.args.get("tipo", "gerencial")   # 'gerencial' | 'oficial'
    modo = request.args.get("modo", "mes")          # 'mes' | 'mensal'
    idx  = competencias.index(competencia)
    comp_ant = competencias[idx - 1] if idx > 0 else None

    # ── DRE OFICIAL (12 linhas) ───────────────────────────────────────────────
    dados_oficial = calcular_todas_empresas(competencia)

    # ── DRE GERENCIAL (30 linhas expansíveis) ─────────────────────────────────
    dados = calcular_todas_empresas_gerencial(competencia)

    dados_ant = calcular_todas_empresas_gerencial(comp_ant) if comp_ant else None
    variacao: dict = {}
    if dados_ant:
        cons     = dados["consolidado"]
        cons_ant = dados_ant["consolidado"]
        for lid, _, _, _ in DRE_META_GERENCIAL:
            variacao[lid] = variacao_pct(cons.get(lid, 0.0), cons_ant.get(lid, 0.0))

    meses_ytd = competencias[: idx + 1]
    ytd_cons  = calcular_dre_gerencial_mensal(meses_ytd)
    ytd: dict[str, float] = {}
    for comp in meses_ytd:
        for lid, v in ytd_cons.get(comp, {}).items():
            ytd[lid] = ytd.get(lid, 0.0) + v
    n = len(meses_ytd) or 1
    media = {lid: v / n for lid, v in ytd.items()}

    det_mkb    = calcular_dre_detalhada_gerencial(EMPRESAS["mkb"]["id"],    competencia)
    det_gnileb = calcular_dre_detalhada_gerencial(EMPRESAS["gnileb"]["id"], competencia)
    det_merged = _merge_detalhe_gerencial(det_mkb, det_gnileb)

    # EBITDA: drill-down não é lista de contas, e sim a "ponte" a partir do
    # Resultado Líquido (ver montar_bridge_ebitda em dre_engine.py)
    det_merged["EBITDA"] = montar_bridge_ebitda(dados, det_mkb, det_gnileb)

    # LL (Resultado Final): drill-down é a "ponte" de subtotais ROL→...→LL
    # (ver montar_bridge_resultado_final em dre_engine.py)
    det_merged["LL"] = montar_bridge_resultado_final(dados)

    # ── MULTI-MÊS: dados de todos os meses + contas por grupo ───────────────
    dados_mensal: dict = {}
    contas_meses: dict = {}     # {grupo: [{cod, descricao, totais: {comp: v}}]}
    if modo == "mensal":
        for comp in competencias:
            dados_mensal[comp] = calcular_todas_empresas_gerencial(comp)

        # Contas detalhadas por grupo × mês (para expansão das linhas)
        det_por_mes: dict = {}
        for comp in competencias:
            dm  = calcular_dre_detalhada_gerencial(EMPRESAS["mkb"]["id"],    comp)
            dg  = calcular_dre_detalhada_gerencial(EMPRESAS["gnileb"]["id"], comp)
            det_por_mes[comp] = _merge_detalhe_gerencial(dm, dg)
            det_por_mes[comp]["EBITDA"] = montar_bridge_ebitda(dados_mensal[comp], dm, dg)
            det_por_mes[comp]["LL"] = montar_bridge_resultado_final(dados_mensal[comp])

        _acc: dict = {}   # {grupo: {cod: {descricao, totais: {comp: v}}}}
        for comp in competencias:
            for grupo, contas in det_por_mes[comp].items():
                _acc.setdefault(grupo, {})
                for c in contas:
                    cod = c["cod"]
                    if cod not in _acc[grupo]:
                        _acc[grupo][cod] = {"cod": cod, "descricao": c["descricao"], "totais": {}}
                    _acc[grupo][cod]["totais"][comp] = c["total"]
        # EBITDA e LL: preservam a ordem da "ponte" (bridge de subtotais),
        # não reordenam por código de conta como os demais grupos.
        contas_meses = {
            g: (list(d.values()) if g in ("EBITDA", "LL")
                else sorted(d.values(), key=lambda x: x["cod"]))
            for g, d in _acc.items()
        }

        # YTD e média sobre TODOS os meses
        ytd_all: dict[str, float] = {}
        for comp in competencias:
            for lid, v in dados_mensal[comp]["consolidado"].items():
                ytd_all[lid] = ytd_all.get(lid, 0.0) + v
        n_all = len(competencias) or 1
        media_all = {lid: v / n_all for lid, v in ytd_all.items()}
    else:
        ytd_all   = ytd
        media_all = media
        n_all     = n

    return render_template(
        "dre_resumida.html",
        tipo=tipo,
        modo=modo,
        competencia=competencia,
        competencias=competencias,
        comp_ant=comp_ant,
        # dados gerencial (mês único)
        dados=dados,
        variacao=variacao,
        det_merged=det_merged,
        dre_meta=DRE_META_GERENCIAL,
        # dados oficial
        dados_oficial=dados_oficial,
        dre_meta_oficial=DRE_META,
        # dados multi-mês
        dados_mensal=dados_mensal,
        contas_meses=contas_meses,
        ytd=ytd_all,
        media=media_all,
        n_meses=n_all,
        # helpers
        fmt_brl=fmt_brl,
        pct_rob=pct_rob,
    )


# --- API: Lançamentos CT1/CT2 por conta (drill-down) -------------------------

@app.route("/api/lancamentos-razao")
@login_required
def api_lancamentos_razao():
    """
    Retorna os lançamentos de uma conta específica para drill-down.
    Prefere CT1 (razão) se disponível; cai para CT2 (saldo agregado).
    """
    empresa = request.args.get("empresa", "mkb")
    comp    = request.args.get("competencia", "")
    conta   = request.args.get("conta", "")

    emp_id = EMPRESAS.get(empresa, {}).get("id", 1)
    conn   = get_conn()

    # Verifica se a tabela razao existe
    razao_ok = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='razao'"
    ).fetchone()

    ct1_rows = []
    if razao_ok:
        ct1_rows = conn.execute(
            """
            SELECT data_lanc, documento, historico, conta_partida,
                   filial, centro_custo, debito, credito, valor
            FROM razao
            WHERE empresa_id=? AND competencia=? AND conta_cod=?
            ORDER BY data_lanc, id
            """,
            (emp_id, comp, conta)
        ).fetchall()

    if ct1_rows:
        rows = [{
            "tipo":          "CT1",
            "data":          r[0] or comp,
            "documento":     r[1] or "—",
            "historico":     (r[2] or "—")[:120],
            "conta_partida": r[3] or "—",
            "filial":        r[4] or "—",
            "centro_custo":  r[5] or "—",
            "debito":        round(r[6] or 0, 2),
            "credito":       round(r[7] or 0, 2),
            "valor":         round(r[8] or 0, 2),
        } for r in ct1_rows]
    else:
        # Fallback CT2 — saldo único agregado
        ct2 = conn.execute(
            "SELECT valor FROM lancamentos "
            "WHERE empresa_id=? AND competencia=? AND conta_cod=?",
            (emp_id, comp, conta)
        ).fetchone()

        if ct2:
            v = round(ct2[0], 2)
            rows = [{
                "tipo":          "CT2",
                "data":          comp,
                "documento":     "—",
                "historico":     "Saldo agregado — CT2 (Comparativo de Contas × 12 Meses)",
                "conta_partida": "—",
                "filial":        "—",
                "centro_custo":  "—",
                "debito":        round(-v, 2) if v < 0 else 0.0,
                "credito":       round(v,  2) if v > 0 else 0.0,
                "valor":         v,
            }]
        else:
            rows = []

    conn.close()

    return jsonify({
        "conta":       conta,
        "empresa":     empresa,
        "competencia": comp,
        "tipo_fonte":  "CT1" if ct1_rows else ("CT2" if rows else "—"),
        "total":       round(sum(r["valor"] for r in rows), 2),
        "rows":        rows,
    })


def _merge_detalhe_gerencial(det_mkb: list, det_gnileb: list) -> dict:
    """
    Funde as listas de contas de MKB e Gnileb por grupo.
    Retorna dict {grupo: [{cod, descricao, mkb, gnileb, total}]}.

    Também cria chaves agregadas para linhas da DRE Gerencial que somam
    mais de um grupo do account_map (ver GRUPOS_AGREGADOS_GER em
    dre_engine.py): DED, ROL e EBITDA.
    """
    merged: dict[str, dict] = {}

    for det, empresa in ((det_mkb, "mkb"), (det_gnileb, "gnileb")):
        for g in det:
            grupo = g["grupo"]
            merged.setdefault(grupo, {})
            for c in g["contas"]:
                cod = c["cod"]
                merged[grupo].setdefault(cod, {
                    "cod": cod,
                    "descricao": c["descricao"],
                    "mkb": 0.0,
                    "gnileb": 0.0,
                })
                merged[grupo][cod][empresa] = c["valor"]

    resultado: dict[str, list] = {}
    for grupo, contas_dict in merged.items():
        lista = sorted(contas_dict.values(), key=lambda x: x["cod"])
        for c in lista:
            c["total"] = c["mkb"] + c["gnileb"]
        resultado[grupo] = lista

    # ── Agregações de linhas que somam múltiplos grupos (DED, ROL, EBITDA) ───
    for linha, grupos in GRUPOS_AGREGADOS_GER.items():
        combinado = []
        for g in grupos:
            combinado.extend(resultado.get(g, []))
        resultado[linha] = sorted(combinado, key=lambda x: x["cod"])

    return resultado


# --- ROTA: DRE DETALHADA -----------------------------------------------------

@app.route("/dre/<competencia>/detalhada/<empresa>")
@login_required
def dre_detalhada(competencia, empresa):
    competencias = _competencias_disponiveis()
    emp_info = EMPRESAS.get(empresa)
    if not emp_info:
        return redirect(url_for("index"))

    detalhes = calcular_dre_detalhada(emp_info["id"], competencia)
    dre_res  = calcular_dre(emp_info["id"], competencia)

    return render_template(
        "dre_detalhada.html",
        competencia=competencia,
        competencias=competencias,
        empresa=empresa,
        emp_info=emp_info,
        detalhes=detalhes,
        dre_res=dre_res,
        fmt_brl=fmt_brl,
        pct_rob=pct_rob,
    )


# --- ROTA: RECEITA POR CLIENTE (CT1) ------------------------------------------

@app.route("/receita/clientes")
@app.route("/receita/clientes/<empresa>")
@login_required
def receita_clientes(empresa="mkb"):
    """
    Análise de Receita Bruta (3.1.1.x) por Cliente × Mês — pivot expansível.
    Disponível apenas para meses com CT1 (Razão) importado — por isso o
    período de navegação é construído a partir da própria tabela `razao`,
    e não de `_competencias_disponiveis()` (que reflete o CT2/lancamentos).
    """
    empresa_valida = empresa if empresa in EMPRESAS else "mkb"
    emp_id = EMPRESAS[empresa_valida]["id"]

    conn = get_conn()
    competencias = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT competencia FROM razao WHERE empresa_id = ? ORDER BY competencia",
            (emp_id,)
        ).fetchall()
    ]
    conn.close()

    if not competencias:
        flash(
            f"Nenhum Razão (CT1) importado para {EMPRESAS[empresa_valida]['sigla']}. "
            f"Importe o relatório 12-00 — Emissão do Razão Conta primeiro.",
            "warning"
        )
        return redirect(url_for("ingest"))

    # Filtro de período opcional via querystring (?de=YYYY-MM&ate=YYYY-MM)
    comp_ini = request.args.get("de",  competencias[0])
    comp_fim = request.args.get("ate", competencias[-1])
    periodo = [c for c in competencias if comp_ini <= c <= comp_fim]
    if not periodo:
        periodo = competencias
        comp_ini, comp_fim = competencias[0], competencias[-1]

    analise = analisar_receita_clientes(emp_id, periodo)

    return render_template(
        "receita_clientes.html",
        empresa=empresa_valida,
        competencias=competencias,
        comp_ini=comp_ini,
        comp_fim=comp_fim,
        analise=analise,
        fmt_brl=fmt_brl,
    )


# --- ROTA: DESPESAS POR FORNECEDOR (CT1) --------------------------------------

@app.route("/despesas/fornecedores")
@app.route("/despesas/fornecedores/<empresa>")
@login_required
def despesas_fornecedores(empresa="mkb"):
    """
    Análise de Despesas e Custos (4.x, exceto folha/encargos/pró-labore) por
    Grupo de Despesa × Fornecedor × Mês — pivot expansível com toggle de
    visão (?visao=grupo|fornecedor). Disponível apenas para meses com CT1
    (Razão) importado — mesmo padrão de receita_clientes.
    """
    empresa_valida = empresa if empresa in EMPRESAS else "mkb"
    emp_id = EMPRESAS[empresa_valida]["id"]

    # Mesmo padrão de `receita_clientes`: a navegação por período é construída
    # a partir de QUALQUER competência com CT1 (Razão) importado -- não apenas
    # as que têm lançamentos 4.x. Isso evita redirecionar empresas que têm CT1
    # mas (ainda) não têm detalhe de despesas importado (ex.: Gnileb, cujo
    # CT2-detalhe de despesas só foi recebido para a MKB) -- nesse caso a
    # própria tela exibe o estado "nenhum lançamento encontrado", de forma
    # graciosa, em vez de mandar o usuário para a tela de importação.
    conn = get_conn()
    competencias = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT competencia FROM razao WHERE empresa_id = ? ORDER BY competencia",
            (emp_id,)
        ).fetchall()
    ]
    conn.close()

    if not competencias:
        flash(
            f"Nenhum Razão (CT1) importado para {EMPRESAS[empresa_valida]['sigla']}. "
            f"Importe o relatório 12-00 — Emissão do Razão Conta primeiro.",
            "warning"
        )
        return redirect(url_for("ingest"))

    # Filtro de período opcional via querystring (?de=YYYY-MM&ate=YYYY-MM)
    comp_ini = request.args.get("de",  competencias[0])
    comp_fim = request.args.get("ate", competencias[-1])
    periodo = [c for c in competencias if comp_ini <= c <= comp_fim]
    if not periodo:
        periodo = competencias
        comp_ini, comp_fim = competencias[0], competencias[-1]

    # Toggle de visão: "grupo" (padrão) ou "fornecedor"
    visao = request.args.get("visao", "grupo")
    if visao not in ("grupo", "fornecedor"):
        visao = "grupo"

    # Filtro Custo × Despesa: "todos" (padrão) | "custo" | "despesa"
    # ("custo" = linha CPV da DRE, 4.1.x; "despesa" = restante não-excluído --
    # DADM/ENC_FIN/OUTROS_OP/IRPJ_CSLL, 4.4.x/4.5.x -- ver GRUPOS_CUSTO)
    tipo = request.args.get("tipo", "todos")
    if tipo not in ("todos", "custo", "despesa"):
        tipo = "todos"

    analise = analisar_despesas_fornecedores(emp_id, periodo, tipo=tipo)

    return render_template(
        "despesas_fornecedores.html",
        empresa=empresa_valida,
        competencias=competencias,
        comp_ini=comp_ini,
        comp_fim=comp_fim,
        visao=visao,
        tipo=tipo,
        analise=analise,
        fmt_brl=fmt_brl,
    )


# --- ROTA: INGESTAO ----------------------------------------------------------

@app.route("/ingest", methods=["GET", "POST"])
@login_required
@admin_required
def ingest():
    ano_atual = datetime.now().year
    mes_atual = datetime.now().month

    if request.method == "POST":
        formato = request.form.get("formato", "ct2")

        # ─── MÊS COMPLETO: localização automática (DRE + Razão + IRPJ/CSLL) ─
        if formato == "mes_completo":
            ano          = int(request.form.get("ano",  ano_atual))
            mes          = int(request.form.get("mes",  mes_atual))
            empresas_sel = request.form.getlist("empresa_mes") or ["mkb", "gnileb"]

            relatorio = importar_mes_completo(ano, mes, empresas=empresas_sel)

            for msg in relatorio["importados"]:
                flash(f"✔ {msg}", "success")
            for msg in relatorio["nao_encontrados"]:
                flash(f"⚠ Não encontrado automaticamente (faça upload manual abaixo): {msg}", "warning")
            for msg in relatorio["erros"]:
                flash(f"✖ {msg}", "danger")

            return redirect(url_for("ingest"))

        # ─── CT1: Razão Contábil ────────────────────────────────────────────
        if formato == "ct1":
            arquivo_ct1 = request.files.get("arquivo_ct1")
            empresa_ct1 = request.form.get("empresa_ct1", "mkb")

            if not arquivo_ct1 or not arquivo_ct1.filename:
                flash("Selecione um arquivo Excel do Razão Contábil.", "warning")
                return redirect(url_for("ingest"))

            # Salva temporariamente
            import tempfile, os
            ext = Path(arquivo_ct1.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                arquivo_ct1.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                conn = get_conn()
                criar_schema(conn)
                seed_empresas(conn)
                res = importar_razao(tmp_path, empresa_ct1, conn)
                conn.close()
                flash(
                    f"Razão CT1 importado: {res.get('registros', 0)} lançamentos "
                    f"({res.get('empresa','')}) — "
                    f"competências: {', '.join(res.get('competencias', []))}",
                    "success"
                )
            except Exception as e:
                flash(f"Erro ao importar Razão: {e}", "danger")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return redirect(url_for("ingest"))

        # ─── DRE: planilha "Template DRE Protheus" (gera o dashboard) ───────
        # Um arquivo cobre o ano inteiro (12 colunas de período). Usado quando
        # o "Mês Completo" automático não acha os arquivos (ex.: deploy remoto
        # sem acesso às pastas do OneDrive).
        if formato == "dre":
            arquivo_dre = request.files.get("arquivo_dre")
            empresa_dre = request.form.get("empresa_dre", "mkb")
            ano_dre     = int(request.form.get("ano_dre", ano_atual))

            if not arquivo_dre or not arquivo_dre.filename:
                flash("Selecione o arquivo Excel da DRE (Template DRE Protheus).", "warning")
                return redirect(url_for("ingest"))

            import tempfile, os
            ext = Path(arquivo_dre.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                arquivo_dre.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                regs = ler_template_dre(tmp_path, empresa_dre, ano_dre)
                if not regs:
                    flash(
                        "Nenhum registro lido — confira se o arquivo tem a aba "
                        "'Template DRE Protheus' e se o ano selecionado bate com o do arquivo.",
                        "warning"
                    )
                else:
                    conn = get_conn()
                    criar_schema(conn)
                    seed_empresas(conn)
                    n = salvar_lancamentos(conn, regs, tmp_path)
                    conn.close()
                    comps = sorted({r["competencia"] for r in regs})
                    flash(
                        f"DRE importada: {n} lançamentos ({empresa_dre.upper()}) — "
                        f"competências: {', '.join(comps)}",
                        "success"
                    )
            except Exception as e:
                flash(f"Erro ao importar DRE: {e}", "danger")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return redirect(url_for("ingest"))

        # ─── BALANCETE: saldo acumulado por conta (validação da DRE) ────────
        if formato == "balancete":
            arquivo_bal = request.files.get("arquivo_balancete")
            empresa_bal = request.form.get("empresa_balancete", "mkb")
            ano_bal     = int(request.form.get("ano_balancete", ano_atual))
            mes_bal     = int(request.form.get("mes_balancete", mes_atual))
            competencia = f"{ano_bal}-{mes_bal:02d}"

            if not arquivo_bal or not arquivo_bal.filename:
                flash("Selecione o arquivo Excel do Balancete.", "warning")
                return redirect(url_for("ingest"))

            import tempfile, os
            ext = Path(arquivo_bal.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                arquivo_bal.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                conn = get_conn()
                criar_schema(conn)
                seed_empresas(conn)
                res = importar_balancete(tmp_path, empresa_bal, competencia, conn)
                conn.close()
                if "erro" in res:
                    flash(f"Erro ao importar Balancete: {res['erro']}", "danger")
                else:
                    # Gera os ajustes de saldo na própria conta divergente, para
                    # a DRE bater com o balancete.
                    emp_id = EMPRESAS.get(empresa_bal, {}).get("id", 1)
                    aj = criar_ajustes_saldo(emp_id, competencia)
                    flash(
                        f"Balancete importado: {res['registros']} contas "
                        f"({res['empresa']}) — competência {_mes_label(competencia)}. "
                        f"{aj['ajustes']} ajuste(s) de saldo lançado(s) na conta divergente. "
                        f"Confira em Validação DRE × Balancete.",
                        "success"
                    )
            except Exception as e:
                flash(f"Erro ao importar Balancete: {e}", "danger")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return redirect(url_for("ingest"))

        # ─── IRPJ/CSLL: planilha ANUAL (apuração de Lucro Real) ─────────────
        if formato == "irpj_csll":
            arquivo_irpj = request.files.get("arquivo_irpj_csll")
            empresa_irpj = request.form.get("empresa_irpj_csll", "mkb")

            if not arquivo_irpj or not arquivo_irpj.filename:
                flash("Selecione a planilha ANUAL de IRPJ/CSLL (.xlsx).", "warning")
                return redirect(url_for("ingest"))

            import tempfile, os
            ext = Path(arquivo_irpj.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                arquivo_irpj.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                conn = get_conn()
                criar_schema(conn)
                seed_empresas(conn)
                res = importar_irpj_csll(tmp_path, empresa_irpj, conn)
                conn.close()
                if "erro" in res:
                    flash(f"Erro ao importar IRPJ/CSLL: {res['erro']}", "danger")
                else:
                    flash(
                        f"IRPJ/CSLL importado: {res.get('registros', 0)} linhas "
                        f"({res.get('empresa','')}) — "
                        f"competências: {', '.join(res.get('competencias', []))}",
                        "success"
                    )
            except Exception as e:
                flash(f"Erro ao importar IRPJ/CSLL: {e}", "danger")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return redirect(url_for("ingest"))

        # ─── ENDIVIDAMENTO: planilha de vinculação parcelamento x conta ─────
        if formato == "endividamento":
            arquivo_end = request.files.get("arquivo_endividamento")
            empresa_end = request.form.get("empresa_endividamento", "mkb")

            if not arquivo_end or not arquivo_end.filename:
                flash("Selecione a planilha de vinculação (.csv).", "warning")
                return redirect(url_for("ingest"))

            import tempfile, os
            ext = Path(arquivo_end.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                arquivo_end.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                conn = get_conn()
                criar_schema(conn)
                seed_empresas(conn)
                res = importar_vinculacao(tmp_path, empresa_end, conn)
                conn.close()
                if "erro" in res:
                    flash(f"Erro ao importar Endividamento: {res['erro']}", "danger")
                else:
                    flash(
                        f"Endividamento importado: {res.get('registros', 0)} parcelamentos "
                        f"({res.get('empresa','')}) — "
                        f"competência de referência: {res.get('competencia_ref','')}",
                        "success"
                    )
            except Exception as e:
                flash(f"Erro ao importar Endividamento: {e}", "danger")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return redirect(url_for("ingest"))

        # ─── CT2: Comparativo Conta x 12 Meses ──────────────────────────────
        # Sem card manual na tela (a Razão já cobre a maior parte das contas
        # via v_lancamentos; o CT2 continua sendo importado automaticamente
        # pelo "Importar Mês Completo" -- ver importar_mes.py). Esta rota
        # continua disponível só pra reimportação em lote de vários meses de
        # uma vez, se algum dia for necessário (ex.: POST manual/CLI).
        if formato == "ct2":
            ano          = int(request.form.get("ano",  ano_atual))
            mes          = int(request.form.get("mes",  mes_atual))
            modo         = request.form.get("modo", "mes")
            empresas_sel = request.form.getlist("empresa_ct2") or ["mkb", "gnileb"]

            meses = list(range(1, mes_atual + 1)) if modo == "ano" else [mes]

            erros_total  = []
            total_mkb    = 0
            total_gnileb = 0

            for m in meses:
                res = importar(ano, m, empresas=empresas_sel)
                total_mkb    += res["mkb"]
                total_gnileb += res["gnileb"]
                erros_total  += res["erros"]

            for e in erros_total:
                flash(f"Aviso: {e}", "warning")

            nomes = " | ".join(e.upper() for e in empresas_sel)
            flash(
                f"CT2 importado [{nomes}]: MKB={total_mkb} | GNILEB={total_gnileb} lançamentos",
                "success"
            )
        return redirect(url_for("ingest"))

    _conn = get_conn()
    criar_schema(_conn)
    seed_empresas(_conn)
    _conn.close()

    competencias = _competencias_disponiveis()

    try:
        conn = get_conn()
        stats_ct2 = conn.execute(
            """
            SELECT e.sigla, l.competencia, COUNT(*) as qtd
            FROM lancamentos l JOIN empresas e ON l.empresa_id = e.id
            GROUP BY e.sigla, l.competencia ORDER BY l.competencia, e.sigla
            """
        ).fetchall()
        stats_razao = conn.execute(
            """
            SELECT e.sigla, r.competencia, COUNT(*) as qtd
            FROM razao r JOIN empresas e ON r.empresa_id = e.id
            GROUP BY e.sigla, r.competencia ORDER BY r.competencia, e.sigla
            """
        ).fetchall() if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='razao'"
        ).fetchone() else []
        stats_irpj = conn.execute(
            """
            SELECT e.sigla, i.competencia, COUNT(DISTINCT i.secao || '-' || i.ordem) as qtd
            FROM irpj_csll i JOIN empresas e ON i.empresa_id = e.id
            GROUP BY e.sigla, i.competencia ORDER BY i.competencia, e.sigla
            """
        ).fetchall() if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='irpj_csll'"
        ).fetchone() else []
        stats_endividamento = conn.execute(
            """
            SELECT e.sigla, p.competencia_ref, COUNT(*) as qtd
            FROM parcelamentos p JOIN empresas e ON p.empresa_id = e.id
            GROUP BY e.sigla, p.competencia_ref ORDER BY p.competencia_ref, e.sigla
            """
        ).fetchall() if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='parcelamentos'"
        ).fetchone() else []
        conn.close()
    except Exception:
        stats_ct2 = []
        stats_razao = []
        stats_irpj = []
        stats_endividamento = []

    return render_template(
        "ingest.html",
        ano_atual=ano_atual,
        mes_atual=mes_atual,
        competencias=competencias,
        stats_ct2=stats_ct2,
        stats_irpj=stats_irpj,
        stats_endividamento=stats_endividamento,
        stats_razao=stats_razao,
    )


@app.route("/razao/excluir", methods=["POST"])
@login_required
@admin_required
def razao_excluir():
    """Exclui o Razão (CT1) de uma empresa+competência, para permitir
    reimportar o mês limpo (sem lançamentos fantasma de um upload anterior)."""
    empresa_sigla = request.form.get("empresa", "")
    competencia   = request.form.get("competencia", "")

    emp = next((e for e in EMPRESAS.values() if e["sigla"] == empresa_sigla), None)
    if not emp or not competencia:
        flash("Empresa ou competência inválida.", "danger")
        return redirect(url_for("ingest"))

    conn = get_conn()
    cur = conn.execute(
        "DELETE FROM razao WHERE empresa_id=? AND competencia=?",
        (emp["id"], competencia)
    )
    n = cur.rowcount
    conn.commit()
    conn.close()

    flash(
        f"Razão excluído: {n} lançamentos de {emp['sigla']} — {_mes_label(competencia)}. "
        f"Pode reimportar o mês agora.",
        "success"
    )
    return redirect(url_for("ingest"))


# --- ROTA: CADASTRO (agrupa Importar + De-Para) ------------------------------

@app.route("/cadastro")
@login_required
@admin_required
def cadastro():
    return render_template("cadastro.html")


# --- ROTA: VALIDAÇÃO DRE × BALANCETE -----------------------------------------

@app.route("/validacao")
@login_required
@admin_required
def validacao():
    competencias = _competencias_disponiveis()
    empresa = request.args.get("empresa", "mkb")
    if empresa not in EMPRESAS:
        empresa = "mkb"

    # competências que têm balancete importado (para o seletor)
    conn = get_conn()
    criar_schema(conn)
    tem_bal = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='balancete'"
    ).fetchone()
    comps_bal = [r[0] for r in conn.execute(
        "SELECT DISTINCT competencia FROM balancete WHERE empresa_id=? ORDER BY competencia",
        (EMPRESAS[empresa]["id"],)
    ).fetchall()] if tem_bal else []
    conn.close()

    # Usa a competência pedida só se ela tiver balancete (senão cai numa válida).
    # Evita ficar "preso" numa competência excluída (ex.: junho fantasma) com o
    # seletor mostrando outro mês.
    comp_param = request.args.get("competencia")
    if comp_param and comp_param in comps_bal:
        competencia = comp_param
    else:
        competencia = comps_bal[-1] if comps_bal else (competencias[-1] if competencias else "")

    resultado = conciliar_balancete(EMPRESAS[empresa]["id"], competencia) if competencia else None

    return render_template(
        "validacao.html",
        empresa=empresa,
        competencia=competencia,
        comps_bal=comps_bal,
        resultado=resultado,
        fmt_brl=fmt_brl,
    )


@app.route("/ajustes/recalcular", methods=["POST"])
@login_required
@admin_required
def ajustes_recalcular():
    """Recalcula os lançamentos AJUSTE-SALDO de uma empresa+competência sem
    precisar reimportar o balancete (aplica a lógica de ajuste mais recente)."""
    empresa_chave = request.form.get("empresa", "")
    competencia   = request.form.get("competencia", "")
    emp = EMPRESAS.get(empresa_chave)
    if not emp or not competencia:
        flash("Empresa ou competência inválida.", "danger")
        return redirect(url_for("validacao"))
    aj = criar_ajustes_saldo(emp["id"], competencia)
    flash(
        f"Ajustes recalculados para {emp['sigla']} — {_mes_label(competencia)}: "
        f"{aj['ajustes']} lançamento(s) AJUSTE-SALDO.",
        "success"
    )
    return redirect(url_for("validacao", empresa=empresa_chave, competencia=competencia))


@app.route("/balancete/excluir", methods=["POST"])
@login_required
@admin_required
def balancete_excluir():
    """Exclui o balancete de uma empresa+competência e os ajustes de saldo
    (AJUSTE-SALDO) gerados por ele -- ex.: balancete importado sob a competência
    errada (mês padrão)."""
    empresa_chave = request.form.get("empresa", "")
    competencia   = request.form.get("competencia", "")
    emp = EMPRESAS.get(empresa_chave)
    if not emp or not competencia:
        flash("Empresa ou competência inválida.", "danger")
        return redirect(url_for("validacao"))

    conn = get_conn()
    n1 = conn.execute(
        "DELETE FROM balancete WHERE empresa_id=? AND competencia=?",
        (emp["id"], competencia)
    ).rowcount
    n2 = conn.execute(
        "DELETE FROM razao WHERE empresa_id=? AND competencia=? AND documento='AJUSTE-SALDO'",
        (emp["id"], competencia)
    ).rowcount
    conn.commit()
    conn.close()
    flash(
        f"Balancete de {emp['sigla']} — {_mes_label(competencia)} excluído "
        f"({n1} contas, {n2} ajustes de saldo removidos).",
        "success"
    )
    return redirect(url_for("validacao", empresa=empresa_chave))


# --- ROTA: DE-PARA (mapeamento conta → linha da DRE) -------------------------

@app.route("/de-para")
@login_required
@admin_required
def de_para():
    conn = get_conn()
    criar_schema(conn)
    custom = conn.execute(
        "SELECT prefixo, grupo, criado_em FROM account_map_custom ORDER BY prefixo"
    ).fetchall()
    conn.close()
    return render_template(
        "de_para.html",
        custom=custom,
        nao_classificadas=contas_nao_classificadas(),
        grupos=grupos_disponiveis(),
        grupo_labels=GRUPO_LABELS,
        fmt_brl=fmt_brl,
    )


@app.route("/de-para/add", methods=["POST"])
@login_required
@admin_required
def de_para_add():
    prefixo = (request.form.get("prefixo") or "").strip()
    grupo   = (request.form.get("grupo") or "").strip()
    if not prefixo or not grupo:
        flash("Informe a conta/prefixo e o grupo da DRE.", "warning")
        return redirect(url_for("de_para"))

    conn = get_conn()
    criar_schema(conn)
    conn.execute(
        """
        INSERT INTO account_map_custom (prefixo, grupo) VALUES (?, ?)
        ON CONFLICT (prefixo) DO UPDATE SET grupo = excluded.grupo
        """,
        (prefixo, grupo)
    )
    conn.commit()
    conn.close()
    invalidar_prefixos()
    flash(f"Mapeamento salvo: {prefixo} → {GRUPO_LABELS.get(grupo, grupo)}.", "success")
    return redirect(url_for("de_para"))


@app.route("/de-para/excluir", methods=["POST"])
@login_required
@admin_required
def de_para_excluir():
    prefixo = (request.form.get("prefixo") or "").strip()
    conn = get_conn()
    conn.execute("DELETE FROM account_map_custom WHERE prefixo = ?", (prefixo,))
    conn.commit()
    conn.close()
    invalidar_prefixos()
    flash(f"Mapeamento removido: {prefixo}.", "success")
    return redirect(url_for("de_para"))


# --- ROTA: API ---------------------------------------------------------------

@app.route("/api/dre/<competencia>")
@login_required
def api_dre(competencia):
    return jsonify(calcular_todas_empresas(competencia))


@app.route("/api/lancamentos")
@login_required
def api_lancamentos():
    empresa = request.args.get("empresa", "mkb")
    comp    = request.args.get("competencia", "")
    emp_id  = EMPRESAS.get(empresa, {}).get("id", 1)
    conn = get_conn()
    tbl = _tabela_lancamentos(conn)
    rows = conn.execute(
        f"SELECT l.conta_cod, c.descricao, l.valor "
        f"FROM {tbl} l "
        "LEFT JOIN contas c ON l.conta_cod=c.cod AND l.empresa_id=c.empresa_id "
        "WHERE l.empresa_id=? AND l.competencia=? ORDER BY l.conta_cod",
        (emp_id, comp)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# --- ROTA: DRE MENSAL (meses lado a lado) ------------------------------------

@app.route("/dre/mensal/<empresa>")
@login_required
def dre_mensal(empresa):
    competencias = _competencias_disponiveis()
    if not competencias:
        flash("Nenhum dado disponivel. Importe os arquivos primeiro.", "warning")
        return redirect(url_for("ingest"))

    # Garante empresa válida
    empresa_valida = empresa if empresa in (list(EMPRESAS.keys()) + ["consolidado"]) else "consolidado"

    mensal = calcular_dre_mensal(empresa_valida, competencias)

    # Variação do último vs. penúltimo mês
    vars_mes = {}
    if len(competencias) >= 2:
        ult = competencias[-1]
        ant = competencias[-2]
        for lid, _, _, _ in DRE_META:
            v_a = mensal[ult].get(lid, 0)
            v_ant = mensal[ant].get(lid, 0)
            vars_mes[lid] = variacao_pct(v_a, v_ant)

    # YTD: soma de todos os meses disponíveis (para linhas de fluxo)
    ytd = {}
    linhas_ytd = ["ROB","DED","CPV","DADM","ENC_FIN","OUTROS_OP","IRPJ_CSLL"]
    for lid in linhas_ytd:
        ytd[lid] = sum(mensal[c].get(lid, 0) for c in competencias)
    from dre_engine import _aplicar_calc
    _aplicar_calc(ytd)

    return render_template(
        "dre_mensal.html",
        empresa=empresa_valida,
        competencias=competencias,
        mensal=mensal,
        vars_mes=vars_mes,
        ytd=ytd,
        dre_meta=DRE_META,
        fmt_brl=fmt_brl,
        pct_rob=pct_rob,
        variacao_pct=variacao_pct,
        modo="fechada",
        EMPRESAS=EMPRESAS,
    )


@app.route("/dre/mensal/<empresa>/detalhada")
@login_required
def dre_mensal_detalhada(empresa):
    competencias = _competencias_disponiveis()
    empresa_valida = empresa if empresa in EMPRESAS else list(EMPRESAS.keys())[0]
    emp_id = EMPRESAS[empresa_valida]["id"]

    det_mensal = calcular_dre_mensal_detalhada(emp_id, competencias)

    # Monta lista de grupos únicos na ordem correta
    from dre_engine import _ORDEM_GRUPOS, GRUPO_LABELS
    grupos_ordem = _ORDEM_GRUPOS

    return render_template(
        "dre_mensal.html",
        empresa=empresa_valida,
        competencias=competencias,
        det_mensal=det_mensal,
        grupos_ordem=grupos_ordem,
        grupo_labels=GRUPO_LABELS,
        dre_meta=DRE_META,
        fmt_brl=fmt_brl,
        pct_rob=pct_rob,
        variacao_pct=variacao_pct,
        modo="detalhada",
        EMPRESAS=EMPRESAS,
    )


# --- PLACEHOLDERS FUTUROS ----------------------------------------------------

@app.route("/irpj/<empresa>/<competencia>")
@login_required
def irpj(empresa, competencia):
    if empresa not in EMPRESAS:
        return render_template("em_breve.html", titulo="IRPJ/CSLL",
                               empresa=empresa, competencia=competencia,
                               mes_label=_mes_label(competencia))

    empresa_id = EMPRESAS[empresa]["id"]
    secao = request.args.get("secao", "CSLL").upper()
    if secao not in ("CSLL", "IRPJ"):
        secao = "CSLL"
    meses_param = request.args.get("meses", "ano")

    conn = get_conn()
    # Só considera "disponível" a competência que teve apuração de fato.
    # Meses sem apuração (planilha ainda zerada, ex.: meses futuros) carregam
    # só 1-2 saldos "arrastados" (ex.: antecipações acumuladas) idênticos em
    # todos os meses vazios -- por isso o corte exige ALGUMAS linhas com
    # valor diferente de zero (não apenas 1), para não confundir esse arrasto
    # com apuração real.
    MIN_LINHAS_COM_VALOR = 3
    competencias_disp = [
        r[0] for r in conn.execute(
            """
            SELECT competencia FROM irpj_csll
            WHERE empresa_id=?
            GROUP BY competencia
            HAVING SUM(CASE WHEN valor IS NOT NULL AND valor != 0 THEN 1 ELSE 0 END) >= ?
            ORDER BY competencia
            """,
            (empresa_id, MIN_LINHAS_COM_VALOR)
        ).fetchall()
    ]

    if not competencias_disp:
        conn.close()
        return render_template("em_breve.html", titulo="IRPJ/CSLL",
                               empresa=empresa, competencia=competencia,
                               mes_label=_mes_label(competencia))

    # Se a competência da URL não tem dados, cai na mais recente disponível
    if competencia not in competencias_disp:
        competencia = competencias_disp[-1]

    # Janela de meses a exibir na tabela comparativa: sempre começa em Janeiro
    # do ano da competência de referência e vai até ela (estilo YTD, igual à
    # planilha original) — não "retrocede N meses" a partir do mês atual.
    # "todas" mostra a história completa (todos os anos já importados, sem
    # limitar pelo mês de referência).
    if meses_param == "todas":
        janela = competencias_disp
    else:
        meses_param = "ano"
        idx = competencias_disp.index(competencia)
        ano_ref = competencia[:4]
        janela = [c for c in competencias_disp[:idx + 1] if c.startswith(ano_ref + "-")]

    placeholders = ",".join("?" * len(janela))
    linhas = conn.execute(
        f"""
        SELECT competencia, ordem, conta_cod, descricao, valor, is_destaque, is_subtotal
        FROM irpj_csll
        WHERE empresa_id=? AND secao=? AND competencia IN ({placeholders})
        ORDER BY ordem, competencia
        """,
        (empresa_id, secao, *janela)
    ).fetchall()

    # Cards de resumo: valor final de CADA seção na competência atual (não na
    # janela) — usa a ÚLTIMA linha "destaque" (pode haver mais de uma, ex.:
    # "IRPJ Devido" e, mais abaixo, "IRPJ Valor Final Devido" após dedução de
    # retenções — a de baixo é o valor realmente a pagar).
    linhas_atual = conn.execute(
        """
        SELECT secao, ordem, valor FROM irpj_csll
        WHERE empresa_id=? AND competencia=? AND is_destaque=1
        ORDER BY secao ASC, ordem
        """,
        (empresa_id, competencia)
    ).fetchall()
    conn.close()

    csll_final = next((l["valor"] for l in reversed(linhas_atual) if l["secao"] == "CSLL"), None)
    irpj_final = next((l["valor"] for l in reversed(linhas_atual) if l["secao"] == "IRPJ"), None)

    # Pivot: agrupa por ordem (linha original da planilha) -> {competencia: valor}
    pivot: dict[int, dict] = {}
    for l in linhas:
        item = pivot.setdefault(l["ordem"], {
            "conta_cod": l["conta_cod"], "descricao": l["descricao"],
            "valores": {}, "destaque": False, "subtotal": False,
        })
        item["valores"][l["competencia"]] = l["valor"]
        if l["is_destaque"]:
            item["destaque"] = True
        if l["is_subtotal"]:
            item["subtotal"] = True

    # Oculta linhas totalmente zeradas/vazias dentro da janela exibida -- mas
    # NUNCA a linha "destaque" (CSLL/IRPJ A Recolher): zero ali é informação
    # real (imposto integralmente coberto por antecipações), não ausência de
    # dado, e é a linha mais importante da tabela.
    linhas_pivot = [
        pivot[k] for k in sorted(pivot.keys())
        if pivot[k]["destaque"] or any((v or 0) != 0 for v in pivot[k]["valores"].values())
    ]

    return render_template(
        "irpj_csll.html",
        empresa=empresa, competencia=competencia,
        mes_label_atual=_mes_label(competencia),
        competencias=competencias_disp,
        janela=janela, secao=secao, meses_param=meses_param,
        linhas=linhas_pivot,
        csll_final=csll_final, irpj_final=irpj_final,
    )


# Prefixos das contas de parcelamento tributário no Razão:
#   CP (curto prazo)  -> 2.1.3.05.x
#   LP (longo prazo)  -> 2.2.4.02.x
_PARCEL_PREFIXOS = ("2.1.3.05.", "2.2.4.02.")


def _endividamento_do_razao(empresa_id: int, competencia: str | None = None) -> dict:
    """Endividamento tributário: saldo devedor (dívida a pagar) vem do BALANCETE
    (tem todas as contas de parcelamento, mesmo as sem movimento no período);
    total pago e última parcela vêm do Razão (débitos = amortizações)."""
    conn = get_conn()
    cond  = " OR ".join("conta_cod LIKE ?" for _ in _PARCEL_PREFIXOS)
    likes = [p + "%" for p in _PARCEL_PREFIXOS]

    # ── Saldo devedor: balancete (competência com balancete mais recente ≤ alvo)
    saldos_bal: dict[str, dict] = {}
    comp_bal = None
    tem_bal = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='balancete'"
    ).fetchone()
    if tem_bal:
        comps = [r[0] for r in conn.execute(
            "SELECT DISTINCT competencia FROM balancete WHERE empresa_id=? ORDER BY competencia",
            (empresa_id,)
        ).fetchall()]
        if comps:
            if competencia:
                antes = [c for c in comps if c <= competencia]
                comp_bal = antes[-1] if antes else comps[-1]
            else:
                comp_bal = comps[-1]
            all_codes = {r[0] for r in conn.execute(
                "SELECT conta_cod FROM balancete WHERE empresa_id=? AND competencia=?",
                (empresa_id, comp_bal)
            ).fetchall()}
            def _leaf(c):
                return not any(o != c and o.startswith(c + ".") for o in all_codes)
            rows = conn.execute(
                f"""SELECT conta_cod, saldo_atual, descricao FROM balancete
                    WHERE empresa_id=? AND competencia=? AND ({cond})""",
                [empresa_id, comp_bal, *likes]
            ).fetchall()
            saldos_bal = {
                r[0]: {"saldo": abs(r[1] or 0.0), "desc": r[2] or ""}
                for r in rows if _leaf(r[0])
            }

    # ── Pago e última parcela: Razão (débitos com lote 008850 = pagamento real)
    _LOTE_PAGAMENTO = "008850"
    rz = conn.execute(
        f"""SELECT conta_cod, competencia, id, debito, historico, documento FROM razao
            WHERE empresa_id=? AND ({cond}) ORDER BY conta_cod, competencia, id""",
        [empresa_id, *likes]
    ).fetchall()
    conn.close()

    pago: dict[str, dict] = {}
    for r in rz:
        c = r["conta_cod"]
        info = pago.setdefault(c, {"pago": 0.0, "ultima": 0.0, "ultima_comp": "",
                                    "hist": "", "parcelas_pagas": 0})
        doc = r["documento"] or ""
        hist = (r["historico"] or "").upper()
        deb = r["debito"] or 0.0
        # ignorar transferências (reclassificação CP↔LP)
        if "TRANSFERENCIA" in hist or "TRANSFERÊNCIA" in hist:
            continue
        # só contar como pagamento se lote começa com 008850
        if doc.startswith(_LOTE_PAGAMENTO) and deb > 0.005:
            info["pago"] += deb
            info["ultima"] = deb
            info["ultima_comp"] = r["competencia"]
            info["parcelas_pagas"] += 1
        if r["historico"]:
            info["hist"] = r["historico"]

    contas = []
    for c in (set(saldos_bal) | set(pago)):
        b = saldos_bal.get(c, {"saldo": 0.0, "desc": ""})
        p = pago.get(c, {"pago": 0.0, "ultima": 0.0, "ultima_comp": "",
                          "hist": "", "parcelas_pagas": 0})
        saldo = round(b["saldo"], 2)
        ultima = round(p["ultima"], 2)
        pagas = p["parcelas_pagas"]
        faltam = round(saldo / ultima) if ultima >= 0.01 and saldo >= 0.01 else None
        qtd_total = (pagas + faltam) if faltam is not None else None
        item = {
            "cod": c,
            "saldo_abs": saldo,
            "pago": round(p["pago"], 2),
            "ultima": ultima,
            "ultima_comp": p["ultima_comp"],
            "hist": b["desc"] or p["hist"],
            "cp": c.startswith("2.1.3.05."),
            "parcelas_pagas": pagas,
            "faltam": faltam,
            "qtd_total": qtd_total,
        }
        if item["saldo_abs"] >= 0.01 or item["pago"] >= 0.01:
            contas.append(item)
    contas.sort(key=lambda x: -x["saldo_abs"])

    def _tot(lst, campo):
        return round(sum(x[campo] for x in lst), 2)

    # ── Agrupar por TIPO DE PARCELAMENTO (descrição), não por conta contábil ──
    import re
    from collections import OrderedDict

    _TYPOS = {"DEMIAS": "DEMAIS"}

    def _normalizar(hist: str) -> str:
        if not hist:
            return "OUTROS PARCELAMENTOS"
        h = hist.strip().upper()
        h = re.sub(r"\s*-?\s*PARC\.\s*\d+/\d+.*", "", h)
        h = re.sub(r"\s*-\s*$", "", h)
        h = re.sub(r"\s+", " ", h).strip()
        # corrigir typos conhecidos
        for errado, certo in _TYPOS.items():
            h = h.replace(errado, certo)
        # normalizar separadores: "PERT DEBITOS" → "PERT - DEBITOS"
        h = re.sub(r"^(PERT|REFIS|PARC\.?)\s+(?!-)", r"\1 - ", h)
        return h or "OUTROS PARCELAMENTOS"

    tipos: dict[str, list] = OrderedDict()
    for c in contas:
        nome = _normalizar(c["hist"])
        tipos.setdefault(nome, []).append(c)

    grupos = []
    for idx, (nome, items) in enumerate(tipos.items()):
        items.sort(key=lambda x: (-x["saldo_abs"], x["cod"]))
        pagas = sum(x["parcelas_pagas"] for x in items)
        faltam_vals = [x["faltam"] for x in items if x["faltam"] is not None]
        faltam = round(sum(faltam_vals)) if faltam_vals else None
        qtd_total = (pagas + faltam) if faltam is not None else None
        grupos.append({
            "nome": nome, "id": f"tipo{idx}",
            "qtd": len(items),
            "saldo": _tot(items, "saldo_abs"),
            "pago": _tot(items, "pago"),
            "ultima": _tot(items, "ultima"),
            "qtd_total": qtd_total,
            "pagas": pagas,
            "faltam": faltam,
            "contas": items,
        })

    cp_all = [x for x in contas if x["cp"]]
    lp_all = [x for x in contas if not x["cp"]]

    return {
        "contas":       contas,
        "comp_bal":     comp_bal,
        "grupos":       grupos,
        "total_pagar":  _tot(contas, "saldo_abs"),
        "total_pago":   _tot(contas, "pago"),
        "total_ultima": _tot(contas, "ultima"),
        "total_cp":     _tot(cp_all, "saldo_abs"),
        "total_lp":     _tot(lp_all, "saldo_abs"),
    }


@app.route("/debug/endiv/<empresa>")
@login_required
def debug_endiv(empresa):
    if empresa not in EMPRESAS:
        return "empresa não encontrada", 404
    eid = EMPRESAS[empresa]["id"]
    conn = get_conn()
    cond = " OR ".join("conta_cod LIKE ?" for _ in _PARCEL_PREFIXOS)
    likes = [p + "%" for p in _PARCEL_PREFIXOS]
    rows_bal = conn.execute(
        f"SELECT conta_cod, descricao, saldo_atual FROM balancete WHERE empresa_id=? AND ({cond}) ORDER BY conta_cod",
        [eid, *likes]).fetchall()
    rows_rz = conn.execute(
        f"""SELECT conta_cod, documento, debito, credito, historico, competencia
            FROM razao WHERE empresa_id=? AND ({cond})
            ORDER BY conta_cod, competencia, documento""",
        [eid, *likes]).fetchall()
    conn.close()
    lines = ["<pre style='font-size:12px'>"]
    lines.append("=== BALANCETE (conta | descricao | saldo) ===")
    for r in rows_bal:
        lines.append(f"  {r[0]:25s} | {r[1]:50s} | {r[2]:>12.2f}")
    lines.append("\n=== RAZÃO (conta | doc | D | C | hist | comp) ===")
    for r in rows_rz:
        lines.append(f"  {r[0]:25s} | {r[1]:15s} | D={r[2]:>10.2f} C={r[3]:>10.2f} | {r[4]:40s} | {r[5]}")
    lines.append("</pre>")
    return "\n".join(lines)


@app.route("/endividamento/<empresa>/<competencia>")
@login_required
def endividamento(empresa, competencia):
    if empresa not in EMPRESAS:
        return render_template("em_breve.html", titulo="Endividamento Tributário",
                               empresa=empresa, competencia=competencia,
                               mes_label=_mes_label(competencia))

    empresa_id = EMPRESAS[empresa]["id"]
    meses_param = request.args.get("meses", "ano")

    conn = get_conn()

    # Competências com snapshot de vinculação já enviado
    competencias_disp = [
        r[0] for r in conn.execute(
            "SELECT DISTINCT competencia_ref FROM parcelamentos WHERE empresa_id=? ORDER BY competencia_ref",
            (empresa_id,)
        ).fetchall()
    ]

    if not competencias_disp:
        conn.close()
        # Sem CSV de vinculação → visão direto do Razão (contas 2.1.3.05 / 2.2.4.02)
        dados = _endividamento_do_razao(empresa_id, competencia)
        return render_template(
            "endividamento_razao.html",
            empresa=empresa,
            competencia=competencia,
            dados=dados,
            fmt_brl=fmt_brl,
        )

    # Se a competência da URL não tem snapshot, usa o mais recente <= ela
    # (ou o mais antigo disponível, se a URL pedir algo anterior a todos)
    competencia_original = competencia
    comp_snapshot = competencia
    if competencia not in competencias_disp:
        anteriores = [c for c in competencias_disp if c <= competencia]
        comp_snapshot = anteriores[-1] if anteriores else competencias_disp[0]

    # Offset de meses entre o snapshot base e a competência solicitada
    # (para auto-ajustar parcela_paga e faltam em meses futuros)
    def _diff_meses(comp_a, comp_b):
        ya, ma = int(comp_a[:4]), int(comp_a[5:7])
        yb, mb = int(comp_b[:4]), int(comp_b[5:7])
        return (ya - yb) * 12 + (ma - mb)

    offset_meses = _diff_meses(competencia_original, comp_snapshot)
    competencia = comp_snapshot

    parcelamentos_raw = conn.execute(
        """
        SELECT tributo, processo, conta_cp, conta_lp, qtd_parcelas, parcela_paga,
               faltam, dt_inicio, dt_termino, desembolso_mensal, valor_principal,
               observacao, saldo_fiscal, saldo_contabilidade_snapshot
        FROM parcelamentos WHERE empresa_id=? AND competencia_ref=?
        ORDER BY tributo
        """,
        (empresa_id, competencia)
    ).fetchall()

    # Auto-ajustar parcelas: se a competência solicitada é posterior ao
    # snapshot, incrementa parcela_paga e decrementa faltam por cada mês
    parcelamentos = []
    for p in parcelamentos_raw:
        row = dict(p)
        if offset_meses > 0 and row["parcela_paga"] is not None and row["faltam"] is not None:
            ajuste = min(offset_meses, row["faltam"])
            row["parcela_paga"] = row["parcela_paga"] + ajuste
            row["faltam"] = row["faltam"] - ajuste
        parcelamentos.append(row)

    # Peso de rateio: 2+ parcelamentos podem compartilhar a mesma conta_cp/lp
    # (ex.: "TRANSAÇÃO - DEMAIS DÉBITOS" e "TRANSAÇÃO - DÉBITOS
    # PREVIDENCIÁRIOS" usam a mesma conta) -- o saldo REAL da conta (vindo do
    # razão) precisa ser dividido entre eles, não duplicado em cada um. Usa o
    # "Saldo contabilidade" do snapshot como peso (confirmado: a soma dos
    # snapshots de quem compartilha a conta bate com o saldo combinado real).
    grupos_conta: dict[tuple, list] = {}
    for p in parcelamentos:
        chave = (p["conta_cp"], p["conta_lp"])
        grupos_conta.setdefault(chave, []).append(p["tributo"])

    peso_por_tributo: dict[str, float] = {}
    for p in parcelamentos:
        chave = (p["conta_cp"], p["conta_lp"])
        membros = grupos_conta[chave]
        if len(membros) == 1:
            peso_por_tributo[p["tributo"]] = 1.0
            continue
        soma_snapshot = sum(
            (pp["saldo_contabilidade_snapshot"] or 0.0)
            for pp in parcelamentos if pp["tributo"] in membros
        )
        snap = p["saldo_contabilidade_snapshot"] or 0.0
        peso_por_tributo[p["tributo"]] = (
            snap / soma_snapshot if soma_snapshot else 1.0 / len(membros)
        )

    contas_envolvidas = set()
    for p in parcelamentos:
        contas_envolvidas.add(p["conta_cp"])
        if p["conta_lp"]:
            contas_envolvidas.add(p["conta_lp"])

    comps_razao = []
    if contas_envolvidas:
        placeholders = ",".join("?" * len(contas_envolvidas))
        comps_razao = [
            r[0] for r in conn.execute(
                f"SELECT DISTINCT competencia FROM razao WHERE empresa_id=? "
                f"AND conta_cod IN ({placeholders}) ORDER BY competencia",
                (empresa_id, *contas_envolvidas)
            ).fetchall()
        ]

    # Janela de meses (calendário contínuo): "ano" = Jan do ano da referência
    # até a referência; "todas" = desde a 1ª competência com razão disponível.
    if meses_param == "todas":
        inicio = min(comps_razao) if comps_razao else competencia
    else:
        meses_param = "ano"
        inicio = f"{competencia[:4]}-01"

    def _add_mes(ano, mes):
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
        return ano, mes

    def _mes_anterior(comp):
        ano, mes = int(comp[:4]), int(comp[5:7])
        mes -= 1
        if mes < 1:
            mes = 12
            ano -= 1
        return f"{ano}-{mes:02d}"

    mes_referencia_anterior = _mes_anterior(competencia)

    janela = []
    ano_i, mes_i = int(inicio[:4]), int(inicio[5:7])
    ano_f, mes_f = int(competencia[:4]), int(competencia[5:7])
    while (ano_i, mes_i) <= (ano_f, mes_f):
        janela.append(f"{ano_i}-{mes_i:02d}")
        ano_i, mes_i = _add_mes(ano_i, mes_i)

    # Busca todos os saldo_atual relevantes de uma vez e monta, por conta, o
    # saldo "como estava" em cada competência da janela (carrega o último
    # valor conhecido para meses sem lançamento -- a dívida não desaparece).
    saldo_por_conta_comp: dict[tuple, float] = {}
    if contas_envolvidas:
        placeholders = ",".join("?" * len(contas_envolvidas))
        rows = conn.execute(
            f"""
            SELECT conta_cod, competencia, saldo_atual
            FROM razao WHERE empresa_id=? AND conta_cod IN ({placeholders})
              AND saldo_atual IS NOT NULL
            ORDER BY conta_cod, competencia, data_lanc, id
            """,
            (empresa_id, *contas_envolvidas)
        ).fetchall()
        por_conta: dict[str, dict] = {}
        for r in rows:
            por_conta.setdefault(r["conta_cod"], {})[r["competencia"]] = r["saldo_atual"]
        for conta, comps_vals in por_conta.items():
            comps_ordenadas = sorted(comps_vals.keys())
            idx, ultimo = 0, None
            for comp in janela:
                while idx < len(comps_ordenadas) and comps_ordenadas[idx] <= comp:
                    ultimo = comps_vals[comps_ordenadas[idx]]
                    idx += 1
                saldo_por_conta_comp[(conta, comp)] = ultimo

    # Valor PAGO em cada mês: soma do DÉBITO lançado na conta CP naquele mês
    # (um pagamento reduz o passivo = débito; transferências LP->CP e juros
    # acrescidos aparecem como CRÉDITO na conta CP, então não entram aqui --
    # só a conta CP é somada, a LP só recebe/cede saldo internamente, nunca
    # representa desembolso de caixa real).
    contas_cp_unicas = {p["conta_cp"] for p in parcelamentos}
    pago_por_conta_comp: dict[tuple, float] = {}
    if contas_cp_unicas:
        placeholders_cp = ",".join("?" * len(contas_cp_unicas))
        rows_pg = conn.execute(
            f"""
            SELECT conta_cod, competencia, SUM(debito) as total_debito
            FROM razao WHERE empresa_id=? AND conta_cod IN ({placeholders_cp})
            GROUP BY conta_cod, competencia
            """,
            (empresa_id, *contas_cp_unicas)
        ).fetchall()
        for r in rows_pg:
            pago_por_conta_comp[(r["conta_cod"], r["competencia"])] = r["total_debito"] or 0.0

    conn.close()

    def _saldo(conta, comp):
        return saldo_por_conta_comp.get((conta, comp)) or 0.0

    def _pago(conta, comp):
        return pago_por_conta_comp.get((conta, comp)) or 0.0

    linhas = []
    totais_por_mes = {c: 0.0 for c in janela}
    totais_pagos_por_mes = {c: 0.0 for c in janela}
    for p in parcelamentos:
        peso = peso_por_tributo[p["tributo"]]
        valores, pagos = {}, {}
        for c in janela:
            saldo_conta = _saldo(p["conta_cp"], c) + (_saldo(p["conta_lp"], c) if p["conta_lp"] else 0.0)
            total = saldo_conta * peso
            valores[c] = total
            totais_por_mes[c] += total

            pago_mes = _pago(p["conta_cp"], c) * peso
            pagos[c] = pago_mes
            totais_pagos_por_mes[c] += pago_mes

        # Saldo ANTERIOR = saldo devedor (dívida) no mês imediatamente antes
        # da referência -- não é soma de pagamentos, é o mesmo saldo da
        # tabela 1, só "puxado" para o mês anterior (pode não estar na
        # janela exibida, ex.: referência = janeiro).
        saldo_conta_ant = (
            _saldo(p["conta_cp"], mes_referencia_anterior)
            + (_saldo(p["conta_lp"], mes_referencia_anterior) if p["conta_lp"] else 0.0)
        )
        saldo_anterior = saldo_conta_ant * peso
        total_a_pagar = valores.get(competencia, 0.0)  # saldo devedor na referência

        linhas.append({
            "tributo": p["tributo"], "processo": p["processo"],
            "qtd_parcelas": p["qtd_parcelas"], "parcela_paga": p["parcela_paga"],
            "faltam": p["faltam"], "dt_inicio": p["dt_inicio"], "dt_termino": p["dt_termino"],
            "desembolso_mensal": p["desembolso_mensal"], "valor_principal": p["valor_principal"],
            "saldo_fiscal": p["saldo_fiscal"], "valores": valores, "pagos": pagos,
            "saldo_anterior": saldo_anterior, "total_a_pagar": total_a_pagar,
        })

    total_endividamento = totais_por_mes.get(competencia, 0.0)
    desembolso_total = sum(p["desembolso_mensal"] or 0 for p in parcelamentos)
    total_saldo_anterior = sum(l["saldo_anterior"] for l in linhas)
    total_a_pagar_geral = sum(l["total_a_pagar"] for l in linhas)

    # ROB acumulada (Jan -> competência de referência), mesmo padrão YTD já
    # usado no Dashboard/DRE
    meses_ano_ref = [f"{competencia[:4]}-{m:02d}" for m in range(1, int(competencia[5:7]) + 1)]
    rob_acumulada = 0.0
    for c in meses_ano_ref:
        try:
            rob_acumulada += calcular_dre(empresa_id, c).get("ROB", 0) or 0
        except Exception:
            pass

    pct_endividamento_rob = (total_endividamento / rob_acumulada * 100) if rob_acumulada else None

    return render_template(
        "endividamento.html",
        empresa=empresa, competencia=competencia,
        mes_label_atual=_mes_label(competencia),
        competencias=competencias_disp,
        janela=janela, meses_param=meses_param,
        linhas=linhas, totais_por_mes=totais_por_mes,
        totais_pagos_por_mes=totais_pagos_por_mes,
        total_endividamento=total_endividamento,
        rob_acumulada=rob_acumulada,
        desembolso_total=desembolso_total,
        pct_endividamento_rob=pct_endividamento_rob,
        mes_label_anterior=_mes_label(mes_referencia_anterior),
        total_saldo_anterior=total_saldo_anterior,
        total_a_pagar_geral=total_a_pagar_geral,
    )


# --- ROTAS: ENDIVIDAMENTO BANCÁRIO -------------------------------------------
# Diferente do Endividamento Tributário (upload de CSV mensal/snapshot), aqui
# o cadastro é manual e raro -- layout de planilha de banco pra banco é
# inconsistente demais pra valer um parser automático (ver decisão tomada com
# o usuário). Saldo devedor e total pago são calculados em tempo real a
# partir do Razão, mesmo padrão do Endividamento Tributário.

@app.route("/endividamento-bancario/cadastro", methods=["GET", "POST"])
@login_required
@admin_required
def endividamento_bancario_cadastro():
    if request.method == "POST":
        empresa_chave = request.form.get("empresa", "gnileb")
        emp = EMPRESAS.get(empresa_chave)
        if not emp:
            flash("Empresa inválida.", "danger")
            return redirect(url_for("endividamento_bancario_cadastro"))

        def _num(campo):
            txt = request.form.get(campo, "").strip()
            if not txt:
                return None
            return float(txt.replace(".", "").replace(",", "."))

        try:
            banco       = request.form.get("banco", "").strip()
            descricao   = request.form.get("descricao", "").strip() or None
            conta_cp_p  = request.form.get("conta_cp_principal", "").strip()
            conta_cp_j  = request.form.get("conta_cp_juros", "").strip() or None
            conta_lp_p  = request.form.get("conta_lp_principal", "").strip() or None
            conta_lp_j  = request.form.get("conta_lp_juros", "").strip() or None
            valor_contratado       = _num("valor_contratado")
            valor_total_com_juros  = _num("valor_total_com_juros")
            qtd_parcelas_txt       = request.form.get("qtd_parcelas", "").strip()
            qtd_parcelas           = int(qtd_parcelas_txt) if qtd_parcelas_txt else None
            data_primeira_parcela  = request.form.get("data_primeira_parcela", "").strip()
        except ValueError as e:
            flash(f"Valor numérico inválido: {e}", "danger")
            return redirect(url_for("endividamento_bancario_cadastro"))

        if not (banco and conta_cp_p and valor_contratado and qtd_parcelas and data_primeira_parcela):
            flash(
                "Preencha banco, conta CP principal, valor contratado, "
                "qtd. parcelas e data da 1ª parcela.", "warning"
            )
            return redirect(url_for("endividamento_bancario_cadastro"))

        conn = get_conn()
        criar_schema(conn)
        conn.execute(
            """
            INSERT INTO emprestimos_bancarios
                (empresa_id, banco, descricao, conta_cp_principal, conta_cp_juros,
                 conta_lp_principal, conta_lp_juros, valor_contratado,
                 valor_total_com_juros, qtd_parcelas, data_primeira_parcela)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (emp["id"], banco, descricao, conta_cp_p, conta_cp_j,
             conta_lp_p, conta_lp_j, valor_contratado, valor_total_com_juros,
             qtd_parcelas, data_primeira_parcela),
        )
        conn.commit()
        conn.close()
        flash(f"Empréstimo \"{banco}\" cadastrado para {emp['sigla']}.", "success")
        return redirect(url_for("endividamento_bancario", empresa=empresa_chave))

    conn = get_conn()
    criar_schema(conn)
    cadastrados = conn.execute(
        """
        SELECT eb.id, e.sigla, eb.banco, eb.descricao, eb.valor_contratado, eb.qtd_parcelas,
               (SELECT COUNT(*) FROM emprestimos_parcelas ep WHERE ep.emprestimo_id = eb.id) AS qtd_cronograma
        FROM emprestimos_bancarios eb JOIN empresas e ON e.id = eb.empresa_id
        ORDER BY eb.criado_em DESC
        """
    ).fetchall()
    conn.close()
    return render_template(
        "endividamento_bancario_cadastro.html",
        cadastrados=cadastrados, EMPRESAS=EMPRESAS,
    )


@app.route("/endividamento-bancario/cronograma/<int:emprestimo_id>", methods=["POST"])
@login_required
@admin_required
def endividamento_bancario_cronograma(emprestimo_id):
    arquivo = request.files.get("arquivo_cronograma")
    if not arquivo or not arquivo.filename:
        flash("Selecione a planilha de simulação/cronograma do banco (.xlsx).", "warning")
        return redirect(url_for("endividamento_bancario_cadastro"))

    import tempfile, os
    ext = Path(arquivo.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        arquivo.save(tmp.name)
        tmp_path = Path(tmp.name)

    try:
        conn = get_conn()
        criar_schema(conn)
        res = importar_cronograma(tmp_path, emprestimo_id, conn)
        conn.close()
        if "erro" in res:
            flash(f"Erro ao importar cronograma: {res['erro']}", "danger")
        else:
            flash(
                f"Cronograma importado: {res['registros']} parcelas "
                f"({res['competencia_ini']} a {res['competencia_fim']}).", "success"
            )
    except Exception as e:
        flash(f"Erro ao importar cronograma: {e}", "danger")
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    return redirect(url_for("endividamento_bancario_cadastro"))


@app.route("/endividamento-bancario/<empresa>")
@login_required
def endividamento_bancario(empresa):
    empresa_valida = empresa if empresa in EMPRESAS else "gnileb"
    emp_id = EMPRESAS[empresa_valida]["id"]

    conn = get_conn()
    criar_schema(conn)
    emprestimos = conn.execute(
        "SELECT * FROM emprestimos_bancarios WHERE empresa_id=? ORDER BY criado_em",
        (emp_id,)
    ).fetchall()

    def _saldo_atual(conta):
        if not conta:
            return None
        r = conn.execute(
            "SELECT saldo_atual FROM razao WHERE empresa_id=? AND conta_cod=? "
            "AND saldo_atual IS NOT NULL ORDER BY competencia DESC, data_lanc DESC, id DESC LIMIT 1",
            (emp_id, conta)
        ).fetchone()
        return r["saldo_atual"] if r else None

    ref_competencia = _ref_competencia_razao(conn, emp_id)

    linhas = []
    for e in emprestimos:
        parcelas = conn.execute(
            "SELECT * FROM emprestimos_parcelas WHERE emprestimo_id=? ORDER BY numero_parcela",
            (e["id"],)
        ).fetchall()

        s_cp_p = _saldo_atual(e["conta_cp_principal"])
        s_cp_j = _saldo_atual(e["conta_cp_juros"])
        s_lp_p = _saldo_atual(e["conta_lp_principal"])
        s_lp_j = _saldo_atual(e["conta_lp_juros"])

        # Saldo a pagar (líquido) = soma das contas de principal (saldo
        # positivo = passivo em aberto) + contas de juros a apropriar (saldo
        # já negativo, contra-conta -- soma reduz o bruto ao líquido).
        tem_razao = any(v is not None for v in (s_cp_p, s_cp_j, s_lp_p, s_lp_j))

        detalhe = []
        if tem_razao:
            # Razão disponível -- fonte oficial (ver Endividamento Tributário)
            saldo_a_pagar = (s_cp_p or 0) + (s_cp_j or 0) + (s_lp_p or 0) + (s_lp_j or 0)
            total_pago    = e["valor_contratado"] - saldo_a_pagar
            parcelas_pagas    = sum(1 for p in parcelas if p["competencia"] <= ref_competencia)
            parcelas_a_pagar  = e["qtd_parcelas"] - parcelas_pagas
            valor_parcela_atual = next(
                (p["valor_parcela"] for p in parcelas if p["competencia"] > ref_competencia),
                parcelas[-1]["valor_parcela"] if parcelas else None,
            )
        elif parcelas:
            # Sem Razão ainda -- usa o cronograma de amortização do contrato
            # (planilha do banco) como fonte do detalhamento mês a mês.
            pagas = [p for p in parcelas if p["competencia"] <= ref_competencia]
            futuras = [p for p in parcelas if p["competencia"] > ref_competencia]
            parcelas_pagas   = len(pagas)
            parcelas_a_pagar = len(futuras)
            saldo_a_pagar = pagas[-1]["saldo_devedor"] if pagas else e["valor_contratado"]
            total_pago    = e["valor_contratado"] - saldo_a_pagar
            valor_parcela_atual = (futuras[0]["valor_parcela"] if futuras
                                    else (pagas[-1]["valor_parcela"] if pagas else None))
        else:
            parcelas_pagas = parcelas_a_pagar = saldo_a_pagar = total_pago = valor_parcela_atual = None

        for p in parcelas:
            detalhe.append({
                "numero_parcela": p["numero_parcela"], "competencia": p["competencia"],
                "amortizacao": p["amortizacao"], "juros": p["juros"],
                "saldo_devedor": p["saldo_devedor"], "valor_parcela": p["valor_parcela"],
                "paga": p["competencia"] <= ref_competencia,
            })

        linhas.append({
            "id": e["id"], "banco": e["banco"], "descricao": e["descricao"],
            "valor_contratado": e["valor_contratado"],
            "valor_total_com_juros": e["valor_total_com_juros"],
            "qtd_parcelas": e["qtd_parcelas"],
            "parcelas_pagas": parcelas_pagas,
            "parcelas_a_pagar": parcelas_a_pagar,
            "saldo_a_pagar": saldo_a_pagar,
            "total_pago": total_pago,
            "valor_parcela_atual": valor_parcela_atual,
            "tem_dados": tem_razao or bool(parcelas),
            "fonte": "Razão" if tem_razao else ("Cronograma do contrato" if parcelas else None),
            "detalhe": detalhe,
        })

    conn.close()

    total_contratado      = sum(l["valor_contratado"] for l in linhas)
    total_pago_geral       = sum(l["total_pago"] or 0 for l in linhas if l["tem_dados"])
    total_saldo_geral      = sum(l["saldo_a_pagar"] or 0 for l in linhas if l["tem_dados"])
    parcelas_a_pagar_total = sum(l["parcelas_a_pagar"] or 0 for l in linhas if l["tem_dados"])

    return render_template(
        "endividamento_bancario.html",
        empresa=empresa_valida, linhas=linhas,
        ref_competencia=ref_competencia,
        total_contratado=total_contratado,
        total_pago_geral=total_pago_geral,
        total_saldo_geral=total_saldo_geral,
        parcelas_a_pagar_total=parcelas_a_pagar_total,
        algum_sem_dados=any(not l["tem_dados"] for l in linhas),
    )


# --- MAIN --------------------------------------------------------------------

if __name__ == "__main__":
    conn = get_conn()
    criar_schema(conn)
    seed_empresas(conn)
    conn.close()
    print(f"\n  MKB-Dashboard rodando em http://localhost:{PORT}")
    print(f"  Use Ctrl+C para encerrar\n")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG, use_reloader=False)
