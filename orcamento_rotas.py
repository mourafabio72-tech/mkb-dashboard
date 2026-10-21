"""
orcamento_rotas.py — telas do módulo de Orçamento (Orçado x Realizado).

Fase 2: importar o Rel_OrcRel. Dois passos, sem estado no servidor entre eles:
  POST /orcamento/importar/previa     lê o arquivo e devolve o resumo; não grava nada
  POST /orcamento/importar/confirmar  lê de novo o mesmo arquivo e substitui o ano
                                      daquela empresa numa transação só
O navegador manda o arquivo nas duas vezes. O servidor grava o upload num arquivo
temporário com nome sorteado, fora de static/, e apaga logo depois de ler.
"""

import json
import logging
import os
import re
import sys
import tempfile
import uuid
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, g, jsonify, render_template, request

from auth import admin_required, empresas_permitidas, login_required, usuario_logado
from config import EMPRESAS
from dre_engine import GRUPO_LABELS, classificar_conta
from ingestion import get_conn
import orcamento_parser as op

bp = Blueprint("orcamento", __name__)

MAX_UPLOAD = 30 * 1024 * 1024  # o Rel_OrcRel de 2026 tem ~13 MB
MESES_CURTOS = ["", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

_log = logging.getLogger("finhub.orcamento")
if not _log.handlers:
    _saida = logging.StreamHandler(sys.stdout)
    _saida.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_saida)
    _log.setLevel(logging.INFO)
    _log.propagate = False


def log_evento(evento: str, nivel: int = logging.INFO, **extra) -> None:
    """Uma linha JSON por evento (Padrao_Logging_Estruturado). Nunca conteúdo da planilha."""
    u = usuario_logado() or {}
    linha = {"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
             "level": logging.getLevelName(nivel), "event": evento, "user_id": u.get("id"),
             "ip": request.remote_addr, "path": request.path, "method": request.method,
             "request_id": getattr(g, "orc_request_id", None) or uuid.uuid4().hex[:16]}
    linha.update(extra)
    _log.log(nivel, json.dumps(linha, ensure_ascii=False, default=str))


class ErroPedido(Exception):
    def __init__(self, mensagem: str, status: int = 400, campo: str = ""):
        super().__init__(mensagem)
        self.status, self.campo = status, campo


@bp.before_request
def _limite_upload():
    g.orc_request_id = uuid.uuid4().hex[:16]
    if request.method != "POST":
        return None
    if request.content_length is None:  # sem tamanho declarado, o corpo seria lido inteiro antes do teto
        return jsonify(erro="Envie o arquivo pela tela de importação."), 411
    if request.content_length > MAX_UPLOAD:
        return jsonify(erro="O arquivo passa de 30 MB. Exporte um ano por arquivo."), 413
    request.max_content_length = MAX_UPLOAD + 1024 * 1024  # o Werkzeug também corta ao ler o multipart
    return None


def _empresa_do_pedido():
    """Whitelist: só as chaves de EMPRESAS que esta sessão enxerga. Fora disso, 404."""
    chave = (request.form.get("empresa") or "").strip()
    perm = empresas_permitidas()
    if chave not in EMPRESAS or (perm is not None and chave not in perm):
        log_evento("ACESSO_NEGADO_IDOR", logging.WARNING, recurso="orcamento", empresa=chave[:20])
        raise ErroPedido("Empresa não encontrada.", 404, "empresa")
    return chave, EMPRESAS[chave]["id"]


def _ano_do_pedido() -> int:
    texto = (request.form.get("ano") or "").strip()
    if not re.fullmatch(r"[0-9]{4}", texto) or not 2000 <= int(texto) <= 2100:
        raise ErroPedido("Informe o ano do orçamento com 4 dígitos.", 400, "ano")
    return int(texto)


def _ler_upload(ano: int):
    """(lido, nome original). O arquivo vive só durante a leitura."""
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        raise ErroPedido("Escolha o arquivo do Rel_OrcRel.", 400, "arquivo")
    raw = arquivo.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise ErroPedido("O arquivo passa de 30 MB. Exporte um ano por arquivo.", 413, "arquivo")
    try:
        op.conferir_xlsx(raw)
    except ValueError as erro:
        raise ErroPedido(str(erro), 400, "arquivo") from None
    descritor, caminho = tempfile.mkstemp(prefix="orc_", suffix=".xlsx")  # nome sorteado, permissão 0600
    try:
        with os.fdopen(descritor, "wb") as destino:
            destino.write(raw)
        lido = op.ler_orcamento(caminho, ano)
    except ValueError as erro:  # inclui ErroOrcamento, com aba e linha
        raise ErroPedido(str(erro), 400, "arquivo") from None
    finally:
        try:
            os.unlink(caminho)
        except OSError:
            pass
    nome = re.sub(r"[^\w .()-]", "", os.path.basename(arquivo.filename))[:120]
    return lido, nome


def _pedido():
    chave, empresa_id = _empresa_do_pedido()
    ano = _ano_do_pedido()
    lido, nome = _ler_upload(ano)
    return chave, empresa_id, ano, lido, nome


def _resposta_erro(erro: ErroPedido):
    return jsonify(erro=str(erro), campo=erro.campo), erro.status


def _resumo(conn, empresa_id: int, ano: int, lido: dict) -> dict:
    por_mes = defaultdict(float)
    sem_linha = defaultdict(float)
    for (competencia, conta, _), valor in lido["orcado"].items():
        por_mes[competencia] += valor
        if classificar_conta(conta) == "NAO_CLASSIFICADO":
            sem_linha[conta] += valor
    existentes = {r[0] for r in conn.execute("SELECT codigo FROM centros_custo WHERE empresa_id = ?", (empresa_id,))}
    gravadas = conn.execute("SELECT COUNT(*) FROM orcamento WHERE empresa_id = ? AND substr(competencia, 1, 4) = ?",
                            (empresa_id, str(ano))).fetchone()[0]
    usados = {centro for (_, _, centro) in lido["orcado"]}
    return dict(
        ano=ano, linhas=lido["resumo"]["linhas_orcado"], chaves=lido["resumo"]["chaves_orcado"],
        total=round(sum(lido["orcado"].values()), 2), centros=len(usados),
        centros_novos=sorted(c for c in usados if c not in existentes)[:50],
        qtd_centros_novos=len([c for c in usados if c not in existentes]),
        meses=[dict(mes=MESES_CURTOS[int(c[5:7])], total=round(v, 2)) for c, v in sorted(por_mes.items())],
        contas_sem_linha=[dict(conta=c, total=round(v, 2)) for c, v in sorted(sem_linha.items())][:50],
        qtd_contas_sem_linha=len(sem_linha), linhas_substituidas=gravadas,
        grupo_sem_linha=GRUPO_LABELS.get("NAO_CLASSIFICADO", "Não classificado"))


@bp.route("/orcamento/importar")
@login_required
@admin_required
def importar():
    return render_template("orcamento_importar.html", ano_padrao=datetime.now().year)


@bp.route("/orcamento/importar/previa", methods=["POST"])
@login_required
@admin_required
def previa():
    try:
        chave, empresa_id, ano, lido, _ = _pedido()
    except ErroPedido as erro:
        return _resposta_erro(erro)
    conn = get_conn()
    try:
        resumo = _resumo(conn, empresa_id, ano, lido)
    finally:
        conn.close()
    resumo["empresa"] = EMPRESAS[chave]["sigla"]
    return jsonify(ok=True, previa=resumo)


@bp.route("/orcamento/importar/confirmar", methods=["POST"])
@login_required
@admin_required
def confirmar():
    try:
        chave, empresa_id, ano, lido, nome = _pedido()
    except ErroPedido as erro:
        return _resposta_erro(erro)
    usuario = (usuario_logado() or {}).get("usuario") or (usuario_logado() or {}).get("nome") or "?"
    total = round(sum(lido["orcado"].values()), 2)
    conn = get_conn()
    try:
        conn.execute("PRAGMA busy_timeout = 30000")  # outra importação gravando: espera, não falha em 5 s
        conn.execute("BEGIN IMMEDIATE")
        removidas = conn.execute("DELETE FROM orcamento WHERE empresa_id = ? AND substr(competencia, 1, 4) = ?",
                                 (empresa_id, str(ano))).rowcount
        lote = conn.execute(
            "INSERT INTO orcamento_lotes (empresa_id, ano, usuario, arquivo, linhas, total) VALUES (?, ?, ?, ?, ?, ?)",
            (empresa_id, ano, str(usuario)[:80], nome, len(lido["orcado"]), total)).lastrowid
        conn.executemany(
            "INSERT INTO orcamento (empresa_id, competencia, conta_cod, centro_custo, valor, lote_id) VALUES (?, ?, ?, ?, ?, ?)",
            [(empresa_id, comp, conta, centro, round(valor, 2), lote)
             for (comp, conta, centro), valor in sorted(lido["orcado"].items())])
        conn.executemany(
            """INSERT INTO centros_custo (empresa_id, codigo, descricao, servico, coordenador, filial, tipo)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (empresa_id, codigo) DO UPDATE SET descricao = excluded.descricao,
                 servico = excluded.servico, coordenador = excluded.coordenador,
                 filial = excluded.filial, tipo = excluded.tipo""",
            [(empresa_id, codigo, c["descricao"], c["servico"], c["coordenador"], c["filial"], c["tipo"])
             for codigo, c in sorted(lido["centros"].items())])
        conn.commit()
    except Exception as erro:
        conn.rollback()
        log_evento("ORCAMENTO_IMPORTACAO_FALHOU", logging.ERROR, empresa=chave, ano=ano, erro=type(erro).__name__)
        return jsonify(erro="Não foi possível gravar o orçamento. Nada foi alterado."), 500
    finally:
        conn.close()
    log_evento("ORCAMENTO_IMPORTADO", empresa=chave, ano=ano, lote=lote, linhas=len(lido["orcado"]),
               substituidas=removidas, centros=len(lido["centros"]), total=total)
    return jsonify(ok=True, linhas=len(lido["orcado"]), substituidas=removidas, ano=ano,
                   empresa=EMPRESAS[chave]["sigla"], total=total)


# ─── Fase 4: tela Orçado x Realizado ─────────────────────────────────────────

import io as _io  # noqa: E402

import orcamento_engine as oe  # noqa: E402

MESES_LONGOS = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
                "Setembro", "Outubro", "Novembro", "Dezembro"]
MAX_EXPORT_LINHAS, MAX_EXPORT_COLUNAS, MAX_EXPORT_TEXTO = 5000, 60, 200  # árvore com 12 meses: 45 colunas


def _visoes_permitidas() -> list:
    """[(chave, rótulo)] que esta sessão enxerga. Consolidado só para quem vê as duas empresas."""
    perm = empresas_permitidas()
    chaves = [k for k in EMPRESAS if perm is None or k in perm]
    visoes = [(k, EMPRESAS[k]["sigla"]) for k in chaves]
    if len(chaves) == len(EMPRESAS):
        visoes.append(("consolidado", "Consolidado"))
    return visoes


def _visao_do_pedido(chave: str) -> str:
    if chave not in dict(_visoes_permitidas()):
        log_evento("ACESSO_NEGADO_IDOR", logging.WARNING, recurso="orcamento_tela", empresa=(chave or "")[:20])
        raise ErroPedido("Empresa não encontrada.", 404, "empresa")
    return chave


def _inteiro(nome: str, minimo: int, maximo: int) -> int:
    texto = (request.args.get(nome) or "").strip()
    if not re.fullmatch(r"[0-9]{1,4}", texto) or not minimo <= int(texto) <= maximo:
        raise ErroPedido("Parâmetro inválido.", 400, nome)
    return int(texto)


@bp.route("/orcamento")
@login_required
def tela():
    visoes = _visoes_permitidas()
    conn = get_conn()
    try:
        ids = [EMPRESAS[k]["id"] for k, _ in visoes if k in EMPRESAS] or [0]
        marcas = ",".join("?" * len(ids))  # só a empresa que a sessão enxerga entra no padrão e na lista de anos
        competencia = (request.args.get("competencia") or "").strip()
        if not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", competencia):
            linha = conn.execute(f"SELECT MAX(competencia) FROM razao WHERE empresa_id IN ({marcas})", ids).fetchone()
            competencia = (linha[0] if linha and linha[0] else datetime.now().strftime("%Y-%m"))
        brutas = oe.opcoes_filtro(conn, "consolidado" if len(visoes) > 2 else visoes[0][0]) if visoes else {}
        cad = oe._centros(conn, [EMPRESAS[k]["id"] for k, _ in visoes if k in EMPRESAS])
        opcoes = {k: [(v, v) for v in vs] for k, vs in brutas.items() if k != "centro"}
        opcoes["centro"] = [(c, f"{c} · {cad[c]['descricao']}" if cad[c]["descricao"] != c else c) for c in brutas.get("centro", [])]
        for k in ("servico", "coordenador", "filial"):
            opcoes[k].append((oe.SEM_CENTRO, oe.SEM_CENTRO))
        anos = sorted({int(r[0]) for r in conn.execute(
            f"SELECT DISTINCT substr(competencia, 1, 4) FROM orcamento WHERE empresa_id IN ({marcas}) "
            f"UNION SELECT DISTINCT substr(competencia, 1, 4) FROM razao WHERE empresa_id IN ({marcas})", ids + ids)
            if r[0] and r[0].isdigit()} | {int(competencia[:4])})
    finally:
        conn.close()
    return render_template("orcamento.html", visoes=visoes, ano=int(competencia[:4]), mes=int(competencia[5:7]),
                           anos=anos, meses=list(enumerate(MESES_LONGOS))[1:], opcoes=opcoes,
                           dimensoes=list(oe.DIMENSOES.items()))


@bp.route("/orcamento/dados")
@login_required
def dados():
    try:
        empresa = _visao_do_pedido((request.args.get("empresa") or "").strip())
        ano = _inteiro("ano", 2000, 2100)
        mes = _inteiro("mes", 1, 12)
        de = _inteiro("de", 1, 12) if request.args.get("de") else None
        filtros = _filtros_do_pedido()
        linha = (request.args.get("linha") or "").strip() or None
        conn = get_conn()
        try:
            resultado = oe.calcular(conn, empresa, ano, mes, (request.args.get("modo") or "mes").strip(),
                                    (request.args.get("abrir_por") or "linha").strip(), filtros, linha, mes_ini=de)
        finally:
            conn.close()
    except ErroPedido as erro:
        return _resposta_erro(erro)
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400
    resultado["rotulo_empresa"] = dict(_visoes_permitidas())[empresa]
    resultado["rotulo_mes"] = (f"{MESES_LONGOS[de]} a {MESES_LONGOS[mes]} de {ano}" if de and de != mes
                               else f"{MESES_LONGOS[mes]} de {ano}")
    return jsonify(ok=True, dados=resultado)


def _filtros_do_pedido() -> dict:
    filtros = {}
    for chave in oe.FILTROS:
        valor = (request.args.get(chave) or "").strip()
        if valor:
            if len(valor) > 120:
                raise ErroPedido("Filtro inválido.", 400, chave)
            filtros[chave] = [valor]
    conta = (request.args.get("conta") or "").strip()
    if conta:
        if not re.fullmatch(r"[0-9][0-9.]{0,39}", conta):
            raise ErroPedido("Conta contábil: use só números e pontos, como 3.1.1.", 400, "conta")
        filtros["conta"] = [conta]
    descricao = " ".join((request.args.get("descricao") or "").split())
    if descricao:
        if len(descricao) > 80 or not re.fullmatch(r"[\w .,/()&-]+", descricao) or not oe._sem_acento(descricao).strip():
            raise ErroPedido("Descrição da conta: use letras ou números, como aluguel.", 400, "descricao")
        filtros["descricao"] = [descricao]
    return filtros


def _periodo_do_pedido():
    empresa = _visao_do_pedido((request.args.get("empresa") or "").strip())
    return empresa, _inteiro("ano", 2000, 2100), _inteiro("de", 1, 12), _inteiro("ate", 1, 12)


@bp.route("/orcamento/dimensao")
@login_required
def dimensao():
    """Abertura por serviço, coordenador, filial ou centro com Receita, Custo e Despesa e MC (Fase 7)."""
    try:
        empresa, ano, de, ate = _periodo_do_pedido()
        conn = get_conn()
        try:
            resultado = oe.por_dimensao(conn, empresa, ano, de, ate, (request.args.get("abrir_por") or "").strip(),
                                        _filtros_do_pedido())
        finally:
            conn.close()
    except ErroPedido as erro:
        return _resposta_erro(erro)
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400
    resultado["rotulo_empresa"] = dict(_visoes_permitidas())[empresa]
    resultado["rotulo_periodo"] = (f"{MESES_LONGOS[de]} de {ano}" if de == ate
                                   else f"{MESES_LONGOS[de]} a {MESES_LONGOS[ate]} de {ano}")
    return jsonify(ok=True, dados=resultado)


@bp.route("/orcamento/lancamentos")
@login_required
def lancamentos():
    """Drilldown: os lançamentos do razão de uma conta analítica no período e nos filtros."""
    try:
        empresa, ano, de, ate = _periodo_do_pedido()
        conta = (request.args.get("conta_lanc") or "").strip()
        if not re.fullmatch(r"[34][0-9.]{0,39}", conta):  # só conta de resultado, como o resto do módulo
            raise ErroPedido("Conta inválida.", 400, "conta_lanc")
        conn = get_conn()
        try:
            resultado = oe.lancamentos(conn, empresa, ano, de, ate, conta, _filtros_do_pedido())
        finally:
            conn.close()
    except ErroPedido as erro:
        return _resposta_erro(erro)
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400
    return jsonify(ok=True, dados=resultado)


@bp.route("/orcamento/painel")
@login_required
def painel():
    """Dashboard do Orçamento (Fase 8): indicadores, Resultado e MC por mês e maiores desvios."""
    try:
        empresa, ano, de, ate = _periodo_do_pedido()
        conn = get_conn()
        try:
            resultado = oe.painel(conn, empresa, ano, de, ate, _filtros_do_pedido())
        finally:
            conn.close()
    except ErroPedido as erro:
        return _resposta_erro(erro)
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400
    resultado["rotulo_empresa"] = dict(_visoes_permitidas())[empresa]
    resultado["rotulo_periodo"] = (f"{MESES_LONGOS[de]} de {ano}" if de == ate
                                   else f"{MESES_LONGOS[de]} a {MESES_LONGOS[ate]} de {ano}")
    return jsonify(ok=True, dados=resultado)


@bp.route("/orcamento/arvore")
@login_required
def arvore():
    """DRE em árvore (Fase 6): Resultado, bloco da DRE gerencial, grupo do 5º nível e analítica, por mês."""
    try:
        empresa = _visao_do_pedido((request.args.get("empresa") or "").strip())
        ano = _inteiro("ano", 2000, 2100)
        de, ate = _inteiro("de", 1, 12), _inteiro("ate", 1, 12)
        conn = get_conn()
        try:
            resultado = oe.arvore(conn, empresa, ano, de, ate, _filtros_do_pedido())
        finally:
            conn.close()
    except ErroPedido as erro:
        return _resposta_erro(erro)
    except ValueError as erro:
        return jsonify(erro=str(erro)), 400
    resultado["rotulo_empresa"] = dict(_visoes_permitidas())[empresa]
    resultado["rotulo_periodo"] = (f"{MESES_LONGOS[de]} de {ano}" if de == ate
                                   else f"{MESES_LONGOS[de]} a {MESES_LONGOS[ate]} de {ano}")
    return jsonify(ok=True, dados=resultado)


def _celula(valor):
    if isinstance(valor, bool) or valor is None:
        return ""
    if isinstance(valor, (int, float)):
        return valor if abs(valor) < 1e15 else ""
    texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(valor))[:MAX_EXPORT_TEXTO]  # o xlsx recusa controle
    return "'" + texto if texto and texto[0] in "=+-@\t\r" else texto  # célula que começa com fórmula vira texto


@bp.route("/orcamento/exportar", methods=["POST"])
@login_required
def exportar():
    """Excel das linhas VISÍVEIS (Padrao_Tabela): a tela manda o que sobrou depois dos filtros."""
    corpo = request.get_json(silent=True)
    try:
        if not isinstance(corpo, dict):
            raise ErroPedido("Pedido inválido.")
        cab, linhas, nome = corpo.get("cabecalho"), corpo.get("linhas"), str(corpo.get("nome") or "")
        if (not isinstance(cab, list) or not isinstance(linhas, list) or not 0 < len(cab) <= MAX_EXPORT_COLUNAS
                or len(linhas) > MAX_EXPORT_LINHAS or any(not isinstance(l, list) or len(l) != len(cab) for l in linhas)):
            raise ErroPedido("Pedido inválido.")
        if not re.fullmatch(r"orcamento_[a-z]+_[0-9]{4}-[0-9]{2}-[0-9]{2}", nome):
            raise ErroPedido("Nome de arquivo inválido.")
    except ErroPedido as erro:
        return _resposta_erro(erro)
    from openpyxl import Workbook
    livro = Workbook()
    folha = livro.active
    folha.title = "Orçado x Realizado"
    folha.append([_celula(c) for c in cab])
    for linha in linhas:
        folha.append([_celula(c) for c in linha])
    saida = _io.BytesIO()
    livro.save(saida)
    log_evento("EXPORT_DADOS", recurso="orcamento", linhas=len(linhas), formato="xlsx")
    from flask import send_file
    saida.seek(0)
    return send_file(saida, as_attachment=True, download_name=nome + ".xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
