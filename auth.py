"""
auth.py — MKB-Dashboard
Autenticação simples baseada em sessão Flask.

Usuários são definidos via variável de ambiente DASHBOARD_USERS no formato:
    "usuario1:senha1,usuario2:senha2"

Em produção, configure DASHBOARD_USERS no painel do Render (aba Environment).
Localmente, o fallback em config.py serve para desenvolvimento.

Uso:
    from auth import login_required
    @app.route("/pagina")
    @login_required
    def pagina(): ...
"""

from functools import wraps
from flask import session, redirect, url_for, request, flash
from config import DASHBOARD_USERS_RAW


# ─── CARREGA USUÁRIOS ────────────────────────────────────────────────────────

def _carregar_usuarios(raw: str) -> dict[str, str]:
    """
    Parseia DASHBOARD_USERS_RAW ("user1:pass1,user2:pass2") → {user: pass}.
    Entradas malformadas são ignoradas com aviso no log.
    """
    usuarios: dict[str, str] = {}
    for par in raw.split(","):
        par = par.strip()
        if not par:
            continue
        partes = par.split(":", 1)
        if len(partes) != 2 or not partes[0] or not partes[1]:
            print(f"[auth] AVISO: entrada inválida em DASHBOARD_USERS ignorada: {par!r}")
            continue
        usuarios[partes[0].strip()] = partes[1].strip()
    return usuarios


USUARIOS: dict[str, str] = _carregar_usuarios(DASHBOARD_USERS_RAW)


# ─── VERIFICAÇÃO ─────────────────────────────────────────────────────────────

def verificar_credenciais(usuario: str, senha: str) -> bool:
    """Retorna True se o par usuário/senha for válido."""
    senha_certa = USUARIOS.get(usuario)
    if senha_certa is None:
        return False
    # Comparação segura (evita timing attacks)
    from hmac import compare_digest
    return compare_digest(senha, senha_certa)


def usuario_logado() -> str | None:
    """Retorna o nome do usuário logado na sessão atual, ou None."""
    return session.get("usuario_logado")


# ─── DECORATOR ───────────────────────────────────────────────────────────────

def login_required(f):
    """
    Decorator para rotas protegidas.
    Redireciona para /login preservando a URL de destino (next).
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not usuario_logado():
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper
