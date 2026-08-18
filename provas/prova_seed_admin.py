"""Prova do seed do 1º admin (DASHBOARD_USERS), em banco temporário.

O env var DASHBOARD_USERS não é login: é SEMENTE, e ela só germina com a tabela
`usuarios` vazia. Até 2026-08-18 o `config.py` trazia "admin:admin123" como
valor padrão, o que significava que banco novo mais variável esquecida nascia
com senha conhecida -- e o formulário de `?local=1` é público na frente dela.

Esta prova trava o comportamento corrigido:
  1. positiva: com a variável definida, a tabela vazia recebe o admin e a senha
     semeada realmente autentica pelo `verificar_credenciais` real;
  2. com a variável AUSENTE (não vazia -- é assim que ela falta de verdade),
     nada é semeado e o app avisa no boot: é o fail-closed;
  3. nesse estado o par antigo `admin:admin123` não autentica;
  4. o seed é idempotente: com usuário já cadastrado, não mexe em nada;
  5. o `config.py` não carrega literal de senha, que é a regressão a evitar.

O item 1 não é enfeite: sem ele, um seed que nunca criasse nada passaria nos
outros quatro parecendo correto. E o item 2 só vale porque remove a variável do
ambiente em vez de defini-la vazia -- `os.environ.get(nome, padrão)` devolve o
padrão apenas quando ela está AUSENTE, e foi por aí que a primeira versão desta
prova deixou passar um fallback reintroduzido.

Uso:  python3 provas/prova_seed_admin.py
"""
import importlib
import io
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

PAR_ANTIGO = "admin:admin" + "123"   # partido para o item 5 não achar a si mesmo
LOGIN_ANTIGO, SENHA_ANTIGA = PAR_ANTIGO.split(":", 1)

# Onde mora o schema: o DRE monta pelo `ingestion`, a Conciliação por um `db`.
# Detectado em vez de fixado para o mesmo arquivo servir nos dois repositórios.
MODULO_BOOT = "db" if (RAIZ / "db.py").exists() else "ingestion"


def cenario(dashboard_users):
    """Monta um boot inteiro do app com a variável no valor pedido.

    Ambiente PRIMEIRO, banco DEPOIS, e isso não é estilo: no DRE o
    `criar_schema` já chama o `bootstrap_usuarios` por dentro, então um banco
    criado antes de acertar a variável nasceria semeado pelo cenário anterior e
    a prova mentiria. Aqui o caminho é o mesmo que produção percorre no boot.

    `dashboard_users=None` REMOVE a variável do ambiente. Recarga de módulo em
    vez de subprocesso porque `DASHBOARD_USERS_RAW` é lido uma vez, no import do
    config: sem o reload, o segundo cenário rodaria com o valor do primeiro.
    """
    if dashboard_users is None:
        os.environ.pop("DASHBOARD_USERS", None)
    else:
        os.environ["DASHBOARD_USERS"] = dashboard_users
    os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "seed_prova.db")

    import config
    importlib.reload(config)
    boot = importlib.reload(importlib.import_module(MODULO_BOOT))
    import auth
    importlib.reload(auth)

    saida = io.StringIO()
    with redirect_stdout(saida):          # o schema pode semear por dentro
        conn = boot.get_conn()
        boot.criar_schema(conn)
    return auth, conn, saida


def quantos(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"]


falhas = []


def exigir(condicao, descricao):
    print(f"  {'ok  ' if condicao else 'FALHA'}  {descricao}")
    if not condicao:
        falhas.append(descricao)


print(f"(schema montado por `{MODULO_BOOT}.py`)")

# ── 1. POSITIVA ──────────────────────────────────────────────────────────────
print("1. com a variável definida, o seed cria o admin e a senha entra")
auth, conn, saida = cenario("chefe:s3nha-que-so-existe-na-prova")
with redirect_stdout(saida):
    auth.bootstrap_usuarios(conn)
exigir(quantos(conn) == 1, "semeou exatamente 1 usuário")
u = auth.verificar_credenciais(conn, "chefe", "s3nha-que-so-existe-na-prova")
exigir(u is not None, "a senha semeada autentica de verdade")
exigir(bool(u) and u.get("role") == "admin", "e o usuário nasce como admin")

# ── 2. variável AUSENTE: nada nasce, e o app fala ────────────────────────────
print("2. com a variável ausente, nenhum admin é semeado, e o app avisa")
auth, conn, saida = cenario(None)
with redirect_stdout(saida):
    auth.bootstrap_usuarios(conn)
exigir(quantos(conn) == 0, "tabela continua vazia")
exigir("DASHBOARD_USERS" in saida.getvalue(), "avisa no boot em vez de morrer calado")

# ── 3. e o par antigo não entra por caminho nenhum ───────────────────────────
print("3. nesse estado, o par antigo não autentica")
exigir(auth.verificar_credenciais(conn, LOGIN_ANTIGO, SENHA_ANTIGA) is None,
       f"'{LOGIN_ANTIGO}' com a senha antiga é recusado")

# ── 4. idempotência ──────────────────────────────────────────────────────────
print("4. com usuário já cadastrado, o seed não mexe em nada")
auth, conn, saida = cenario("chefe:s3nha-que-so-existe-na-prova")
with redirect_stdout(saida):
    auth.bootstrap_usuarios(conn)
antes = quantos(conn)
os.environ["DASHBOARD_USERS"] = "outro:outra-senha-qualquer"
import config as _config
importlib.reload(_config)
importlib.reload(auth)
with redirect_stdout(saida):
    auth.bootstrap_usuarios(conn)
exigir(quantos(conn) == antes, f"continua com {antes} usuário(s), sem semear o segundo")

# ── 5. a regressão a evitar ──────────────────────────────────────────────────
print("5. o config.py não carrega literal de senha")
fonte = io.open(RAIZ / "config.py", encoding="utf-8").read()
exigir(PAR_ANTIGO not in fonte, "nenhum literal do par antigo no config.py")
exigir('os.environ.get("DASHBOARD_USERS", "")' in fonte.replace("'", '"'),
       "DASHBOARD_USERS é lida sem valor padrão")

print()
if falhas:
    print(f"FALHOU ({len(falhas)}):")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("PROVA OK: a semente germina quando existe, não inventa senha quando "
      "falta, avisa no boot, é idempotente, e o literal antigo não voltou.")
