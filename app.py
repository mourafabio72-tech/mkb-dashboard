"""
app.py -- MKB-Dashboard  (porta 5001)
Dashboard gerencial do Grupo Markbuilding: DRE, IRPJ/CSLL, Comparativos.
"""

from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session

from config import SECRET_KEY, PORT, DEBUG, EMPRESAS
from auth import login_required, verificar_credenciais
from ingestion import get_conn, criar_schema, seed_empresas, importar
from razao_parser import importar_razao
from plano_contas_parser import importar_plano_contas
from dre_engine import (
    calcular_dre, calcular_consolidado, calcular_todas_empresas,
    calcular_dre_detalhada, calcular_dre_mensal, calcular_dre_mensal_detalhada,
    calcular_rob_por_segmento, calcular_top_custo, calcular_top_despesa, calcular_serie_mensal,
    calcular_todas_empresas_gerencial, calcular_dre_gerencial_mensal,
    calcular_dre_detalhada_gerencial, analisar_receita_clientes,
    analisar_despesas_fornecedores,
    fmt_brl, pct_rob, variacao_pct, DRE_META, DRE_META_GERENCIAL
)

app = Flask(__name__)
app.secret_key = SECRET_KEY


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
        rows = conn.execute(
            "SELECT DISTINCT competencia FROM lancamentos ORDER BY competencia"
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

app.jinja_env.globals["mes_label"] = _mes_label


# --- ROTA: HOME / DASHBOARD --------------------------------------------------

# --- LOGIN / LOGOUT ----------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        senha   = (request.form.get("senha")   or "").strip()
        next_url = request.form.get("next") or url_for("index")
        if verificar_credenciais(usuario, senha):
            session.permanent = True
            session["usuario_logado"] = usuario
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

    return render_template(
        "dashboard.html",
        todas_competencias=todas_competencias,
        competencias=competencias,
        ultima=ultima,
        kpis=kpis,
        kpis_ant=kpis_ant,
        ytd=ytd,
        dre_meta=DRE_META,
        fmt_brl=fmt_brl,
        pct_rob=pct_rob,
        variacao_pct=variacao_pct,
        # JSON para Chart.js
        grafico_serie=_json.dumps(grafico_serie),
        grafico_segmento=_json.dumps(grafico_segmento),
        grafico_custo=_json.dumps(grafico_custo),
        grafico_despesa=_json.dumps(grafico_despesa),
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

        _acc: dict = {}   # {grupo: {cod: {descricao, totais: {comp: v}}}}
        for comp in competencias:
            for grupo, contas in det_por_mes[comp].items():
                _acc.setdefault(grupo, {})
                for c in contas:
                    cod = c["cod"]
                    if cod not in _acc[grupo]:
                        _acc[grupo][cod] = {"cod": cod, "descricao": c["descricao"], "totais": {}}
                    _acc[grupo][cod]["totais"][comp] = c["total"]
        contas_meses = {g: sorted(d.values(), key=lambda x: x["cod"])
                        for g, d in _acc.items()}

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
def ingest():
    ano_atual = datetime.now().year
    mes_atual = datetime.now().month

    if request.method == "POST":
        formato = request.form.get("formato", "ct2")

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

        # ─── Plano de Contas: descrição oficial das contas ──────────────────
        if formato == "plano_contas":
            arquivo_pc = request.files.get("arquivo_plano_contas")
            empresa_pc = request.form.get("empresa_plano_contas", "mkb")

            if not arquivo_pc or not arquivo_pc.filename:
                flash("Selecione o arquivo CSV do Plano de Contas.", "warning")
                return redirect(url_for("ingest"))

            import tempfile, os
            ext = Path(arquivo_pc.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                arquivo_pc.save(tmp.name)
                tmp_path = Path(tmp.name)

            try:
                conn = get_conn()
                criar_schema(conn)
                seed_empresas(conn)
                res = importar_plano_contas(tmp_path, empresa_pc, conn)
                conn.close()
                if "erro" in res:
                    flash(f"Erro ao importar Plano de Contas: {res['erro']}", "danger")
                else:
                    flash(
                        f"Plano de Contas importado: {res.get('registros', 0)} contas "
                        f"({res.get('empresa','')}) — descrições gravadas/atualizadas em \"contas\".",
                        "success"
                    )
            except Exception as e:
                flash(f"Erro ao importar Plano de Contas: {e}", "danger")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
            return redirect(url_for("ingest"))

        # ─── CT2: Comparativo Conta x 12 Meses ──────────────────────────────
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
        conn.close()
    except Exception:
        stats_ct2 = []
        stats_razao = []

    return render_template(
        "ingest.html",
        ano_atual=ano_atual,
        mes_atual=mes_atual,
        competencias=competencias,
        stats_ct2=stats_ct2,
        stats_razao=stats_razao,
    )


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
    rows = conn.execute(
        "SELECT l.conta_cod, c.descricao, l.valor "
        "FROM lancamentos l "
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
    return render_template("em_breve.html", titulo="IRPJ/CSLL",
                           empresa=empresa, competencia=competencia,
                           mes_label=_mes_label(competencia))


@app.route("/comparativo/<empresa>")
@login_required
def comparativo(empresa):
    return render_template("em_breve.html", titulo="Comparativo Mensal",
                           empresa=empresa, competencia="", mes_label="")


# --- MAIN --------------------------------------------------------------------

if __name__ == "__main__":
    conn = get_conn()
    criar_schema(conn)
    seed_empresas(conn)
    conn.close()
    print(f"\n  MKB-Dashboard rodando em http://localhost:{PORT}")
    print(f"  Use Ctrl+C para encerrar\n")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG, use_reloader=False)
