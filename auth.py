"""
auth.py — MKB-Dashboard
Autenticação baseada em sessão Flask, com usuários individuais na tabela
`usuarios` (login + senha com hash + role 'admin'/'leitura').

Substitui o esquema anterior (senha única via DASHBOARD_USERS). Esse env var
continua existindo só como SEED do 1º admin: se a tabela `usuarios` estiver
vazia na primeira execução, cada entrada de DASHBOARD_USERS vira um usuário
admin (ver `bootstrap_usuarios`, chamado por `ingestion.criar_schema`) --
evita ficar trancado fora no primeiro deploy. Depois disso, a gestão de
usuários é só pela tabela (tela /usuarios ou `criar_usuario.py`).

Uso:
    from auth import login_required, admin_required
    @app.route("/pagina")
    @login_required
    def pagina(): ...

    @app.route("/admin-only")
    @login_required
    @admin_required
    def admin_only(): ...
"""

import time
from functools import wraps
from urllib.parse import quote

from flask import session, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash

from config import DASHBOARD_USERS_RAW, HUB_URL, MODULO_HUB

_MAX_ATTEMPTS = 5
_BLOCK_SECONDS = 300
_login_attempts: dict[str, list] = {}  # ip -> [timestamps of failures]


# ─── RATE LIMITING ──────────────────────────────────────────────────────────

def rate_limit_login(ip: str, *, check_only: bool = False, reset: bool = False) -> tuple[bool, int]:
    """Bloqueia IP após _MAX_ATTEMPTS falhas em _BLOCK_SECONDS.
    Retorna (bloqueado, segundos_restantes)."""
    now = time.time()
    if reset:
        _login_attempts.pop(ip, None)
        return False, 0
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t < _BLOCK_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        wait = int(_BLOCK_SECONDS - (now - attempts[0]))
        return True, max(wait, 1)
    if not check_only:
        attempts.append(now)
        _login_attempts[ip] = attempts
    return False, 0


# ─── BOOTSTRAP (seed do 1º admin a partir do DASHBOARD_USERS antigo) ────────

def bootstrap_usuarios(conn) -> None:
    """
    Se a tabela `usuarios` estiver vazia e DASHBOARD_USERS estiver definida,
    cria 1 usuário admin por entrada ("usuario1:senha1,usuario2:senha2").
    Idempotente -- não faz nada se já existir qualquer usuário cadastrado.
    """
    existe = conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone()
    if existe or not DASHBOARD_USERS_RAW:
        return

    for par in DASHBOARD_USERS_RAW.split(","):
        par = par.strip()
        if not par:
            continue
        partes = par.split(":", 1)
        if len(partes) != 2 or not partes[0] or not partes[1]:
            continue
        usuario, senha = partes[0].strip(), partes[1].strip()
        conn.execute(
            """
            INSERT OR IGNORE INTO usuarios (usuario, nome, senha_hash, role, ativo)
            VALUES (?, ?, ?, 'admin', 1)
            """,
            (usuario, usuario, generate_password_hash(senha)),
        )
    conn.commit()


# ─── VERIFICAÇÃO ─────────────────────────────────────────────────────────────

def verificar_credenciais(conn, login: str, senha: str) -> dict | None:
    """
    Retorna o dict do usuário ({id, usuario, nome, role}) se as credenciais
    forem válidas e o usuário estiver ativo; None caso contrário.
    Aceita tanto o campo 'usuario' quanto 'email' como identificador de login.
    """
    row = conn.execute(
        "SELECT id, usuario, nome, role, senha_hash FROM usuarios "
        "WHERE (usuario = ? OR email = ?) AND ativo = 1",
        (login, login),
    ).fetchone()
    if row is None:
        return None
    if not check_password_hash(row["senha_hash"], senha):
        return None
    return {"id": row["id"], "usuario": row["usuario"], "nome": row["nome"], "role": row["role"]}


def usuario_logado() -> dict | None:
    """Retorna {id, usuario, nome, role} do usuário logado na sessão, ou None."""
    return session.get("usuario_logado")


def is_admin() -> bool:
    u = usuario_logado()
    return bool(u and u.get("role") == "admin")


# ─── DECORATORS ──────────────────────────────────────────────────────────────

def login_required(f):
    """Redireciona para o login (hub, se configurado) se ninguém estiver logado.
    Sessões vindas do hub também passam pela checagem de módulo."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        u = usuario_logado()
        if not u:
            if HUB_URL:
                return redirect(f"{HUB_URL}/login?next={quote(request.url, safe='')}")
            return redirect(url_for("login", next=request.path))
        if u.get("origem") == "hub" and MODULO_HUB not in (u.get("modulos") or []):
            return ("Seu usuário não tem acesso ao módulo deste aplicativo. "
                    "Solicite a liberação a um administrador no hub zoaria.com.br.", 403)
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """
    Bloqueia o acesso de quem não é admin (perfil 'leitura').
    Usar SEMPRE depois de @login_required (assume que já há sessão).
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_admin():
            flash("Acesso restrito a administradores.", "warning")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return wrapper
