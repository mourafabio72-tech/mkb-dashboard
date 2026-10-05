"""
ia_config.py -- provedores de IA do FinHub (OpenAI e NVIDIA).

Um lugar só para: onde a chave mora, qual provedor está ativo, qual modelo
cada um usa, e a chamada HTTP de chat. O resto do app (Pergunte à IA, sugestão
de aliases) pergunta para cá e nunca lê arquivo de chave por conta própria.

Regras (decisões 8 e 9 do 00_GENESIS/LASTRO.md):
  - variável de ambiente vence o arquivo; o arquivo mora no diretório do banco
    (prod `/data`, mesmo volume do `DB_PATH`), fora do git e da imagem;
  - a chave nunca sai daqui inteira para tela, JSON ou log: só `mascarar()`;
  - a URL de cada provedor é FIXA no código (allowlist). Não há campo de URL na
    tela, e é isso que fecha SSRF;
  - erro do provedor volta genérico, sem corpo da resposta nem cabeçalho.

HTTP pela `urllib` da biblioteca padrão: o pacote `openai` 3.x não traz mais o
`httpx`, e um POST de JSON não justifica dependência nova.
"""

import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import config

PROVEDORES = {
    "openai": {
        "nome": "OpenAI",
        "url": "https://api.openai.com/v1/chat/completions",
        "env": "OPENAI_API_KEY",
        "arquivo": "openai_key.txt",
        "prefixo": "sk-",
        "modelo_padrao": "gpt-4o-mini",
    },
    "nvidia": {
        "nome": "NVIDIA",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "env": "NVIDIA_API_KEY",
        "arquivo": "nvidia_key.txt",
        "prefixo": "nvapi-",
        "modelo_padrao": "meta/llama-3.3-70b-instruct",
    },
}
PROVEDOR_PADRAO = "openai"
ARQUIVO_CONFIG = "ia_config.json"

_RE_CHAVE = re.compile(r"^[A-Za-z0-9_.-]{20,200}$")
_RE_MODELO = re.compile(r"^[A-Za-z0-9._/:-]{1,80}$")


class ErroIA(Exception):
    """Falha ao falar com o provedor. A mensagem já é segura para a tela."""


def _dir_dados() -> Path:
    # lido a cada chamada: as provas trocam DB_PATH antes do import, e o
    # diretório tem de seguir o banco (prod /data, Mac a pasta do projeto)
    return Path(config.DB_PATH).parent


def _gravar_privado(caminho: Path, texto: str) -> None:
    """Grava num temporário 0o600 do mesmo diretório e troca de uma vez
    (os.replace): nunca há janela com a chave legível nem arquivo pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=caminho.parent, prefix=".ia-")   # mkstemp já cria 0o600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(tmp, caminho)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def registrar(evento: str, **campos) -> None:
    """Log estruturado (uma linha JSON no stdout, que o EasyPanel guarda).
    Nunca recebe chave, pergunta nem resposta: só quem, o quê e quanto tempo."""
    linha = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "level": "INFO", "event": evento}
    try:
        from flask import g, has_request_context, request
        if has_request_context():
            if "request_id" not in g:
                g.request_id = os.urandom(8).hex()
            linha.update(request_id=g.request_id, path=request.path, method=request.method)
    except ImportError:
        pass
    linha.update(campos)
    print(json.dumps(linha, ensure_ascii=False), file=sys.stdout, flush=True)


# ─── CHAVES ──────────────────────────────────────────────────────────────────

def ler_chave(provedor: str) -> str:
    p = PROVEDORES[provedor]
    chave = os.environ.get(p["env"], "").strip()
    if chave:
        return chave
    try:
        arq = _dir_dados() / p["arquivo"]
        if arq.exists():
            return arq.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    return ""


def origem_chave(provedor: str) -> str | None:
    """'ambiente', 'arquivo' ou None. A tela avisa quando a variável manda."""
    if os.environ.get(PROVEDORES[provedor]["env"], "").strip():
        return "ambiente"
    return "arquivo" if ler_chave(provedor) else None


def mascarar(chave: str) -> str:
    if not chave:
        return ""
    if len(chave) < 12:
        return "***"
    return f"{chave[:3]}...{chave[-4:]}"


def validar_chave(provedor: str, chave: str) -> str | None:
    """Mensagem de erro para a tela, ou None se a chave tem formato válido."""
    p = PROVEDORES[provedor]
    if not chave.startswith(p["prefixo"]):
        return f"A chave da {p['nome']} começa com {p['prefixo']}."
    if not _RE_CHAVE.match(chave):
        return f"A chave da {p['nome']} tem de 20 a 200 caracteres, sem espaço."
    return None


def validar_modelo(modelo: str) -> str | None:
    if not _RE_MODELO.match(modelo):
        return "O nome do modelo aceita até 80 caracteres: letras, números e . _ / : -"
    return None


def validar_envio(chaves: dict, ativo: str | None, modelos: dict) -> list[str]:
    """Valida tudo ANTES de gravar qualquer coisa: ou salva tudo, ou nada."""
    erros = []
    for k, c in chaves.items():
        c = (c or "").strip()
        if c:
            e = validar_chave(k, c)
            if e:
                erros.append(e)
    if ativo is not None and ativo not in PROVEDORES:
        erros.append("Provedor desconhecido.")
    for m in modelos.values():
        m = (m or "").strip()
        if m:
            e = validar_modelo(m)
            if e:
                erros.append(e)
    return erros


def salvar_chave(provedor: str, chave: str) -> str | None:
    """Grava a chave no diretório de dados. Vazio mantém a atual (devolve None)."""
    chave = (chave or "").strip()
    if not chave:
        return None
    erro = validar_chave(provedor, chave)
    if erro:
        return erro
    _gravar_privado(_dir_dados() / PROVEDORES[provedor]["arquivo"], chave)
    return None


# ─── PROVEDOR ATIVO E MODELO ─────────────────────────────────────────────────

def ler_config() -> dict:
    cfg = {"ativo": PROVEDOR_PADRAO,
           "modelos": {k: p["modelo_padrao"] for k, p in PROVEDORES.items()}}
    try:
        dados = json.loads((_dir_dados() / ARQUIVO_CONFIG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    if not isinstance(dados, dict):
        return cfg
    if dados.get("ativo") in PROVEDORES:
        cfg["ativo"] = dados["ativo"]
    modelos = dados.get("modelos")
    for k, m in (modelos.items() if isinstance(modelos, dict) else ()):
        if k in PROVEDORES and isinstance(m, str) and not validar_modelo(m):
            cfg["modelos"][k] = m
    return cfg


def salvar_config(ativo: str | None = None, modelos: dict | None = None) -> str | None:
    cfg = ler_config()
    if ativo is not None:
        if ativo not in PROVEDORES:
            return "Provedor desconhecido."
        cfg["ativo"] = ativo
    for k, m in (modelos or {}).items():
        if k not in PROVEDORES:
            continue
        m = (m or "").strip()
        if not m:
            continue
        erro = validar_modelo(m)
        if erro:
            return erro
        cfg["modelos"][k] = m
    _gravar_privado(_dir_dados() / ARQUIVO_CONFIG, json.dumps(cfg, ensure_ascii=False, indent=2))
    return None


def estado_publico() -> dict:
    """O que a tela de configuração pode mostrar. Nunca a chave inteira."""
    cfg = ler_config()
    provs = []
    for k, p in PROVEDORES.items():
        chave = ler_chave(k)
        provs.append({
            "id": k,
            "nome": p["nome"],
            "prefixo": p["prefixo"],
            "tem_chave": bool(chave),
            "mascara": mascarar(chave),
            "origem": origem_chave(k),
            "modelo": cfg["modelos"][k],
            "modelo_padrao": p["modelo_padrao"],
        })
    return {"ativo": cfg["ativo"], "provedores": provs}


# ─── CHAMADA ─────────────────────────────────────────────────────────────────

class _SemRedirect(urllib.request.HTTPRedirectHandler):
    """Redirect não é seguido: o urllib reenviaria o Authorization para o
    destino novo, e a allowlist de URL valeria só para o primeiro pedido."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_abridor = urllib.request.build_opener(_SemRedirect)


def _post_json(url: str, corpo: dict, cabecalhos: dict, timeout: float) -> tuple[int, bytes]:
    """POST de JSON. Separado para a prova trocar por dublê sem rede.
    Status diferente de 2xx (inclusive 3xx) volta com corpo vazio: quem chama
    só enxerga o código, nunca o texto do provedor."""
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                 headers=cabecalhos, method="POST")
    try:
        with _abridor.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def chamar(mensagens: list[dict], provedor: str | None = None, *,
           max_tokens: int = 300, temperature: float = 0,
           json_mode: bool = False, timeout: float = 30) -> str:
    """Chat completion no provedor (o ativo, se nenhum for dado). Devolve o texto.

    Levanta ErroIA com mensagem pronta para a tela; nunca carrega corpo da
    resposta, chave ou cabeçalho."""
    provedor = provedor or ler_config()["ativo"]
    p = PROVEDORES[provedor]
    chave = ler_chave(provedor)
    if not chave:
        raise ErroIA(f"Nenhuma chave da {p['nome']} configurada.")
    corpo = {
        "model": ler_config()["modelos"][provedor],
        "messages": mensagens,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode and provedor == "openai":
        corpo["response_format"] = {"type": "json_object"}
    cabecalhos = {
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        status, bruto = _post_json(p["url"], corpo, cabecalhos, timeout)
    except Exception:
        raise ErroIA(f"Não consegui falar com a {p['nome']} agora.") from None
    if status != 200:
        raise ErroIA(f"A {p['nome']} respondeu HTTP {status}.")
    try:
        texto = json.loads(bruto)["choices"][0]["message"]["content"]
        if texto is None:
            return ""
        if not isinstance(texto, str):   # lista de partes, dict: formato que não usamos
            raise TypeError
        return texto
    except (ValueError, KeyError, IndexError, TypeError):
        raise ErroIA(f"A {p['nome']} devolveu uma resposta que não entendi.") from None


def testar(provedor: str) -> tuple[bool, str]:
    nome = PROVEDORES[provedor]["nome"]
    if not ler_chave(provedor):
        return False, f"Nenhuma chave da {nome} configurada."
    try:
        chamar([{"role": "user", "content": "Responda só: ok"}], provedor,
               max_tokens=5, timeout=20)
    except ErroIA as e:
        return False, str(e)
    return True, f"A {nome} respondeu. Chave e modelo funcionando."
