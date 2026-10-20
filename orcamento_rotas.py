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
