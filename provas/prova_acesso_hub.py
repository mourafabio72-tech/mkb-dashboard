"""
prova_acesso_hub.py -- trava a entrada pelo Hub (2026-11-17).

Quem vem do Hub entra se tem o CARD deste app (`apps` do cookie), seja qual
for o grupo do menu em que o card está. O módulo `controladoria` continua
abrindo a porta, para não tirar quem já entrava. Sem os dois, 403.

Caso que originou: o card foi para o módulo "Cliente" e o Marcelo, com o card
marcado, recebia "Seu usuário não tem acesso ao módulo deste aplicativo".

Rodar:  uv run --no-project --python 3.12 --with-requirements requirements.txt python provas/prova_acesso_hub.py
"""
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prova_acesso_hub.db")
os.environ.pop("APPS_HUB", None)

import app as A                                                     # noqa: E402
from ingestion import get_conn, criar_schema, seed_empresas         # noqa: E402

conn = get_conn()
criar_schema(conn)
seed_empresas(conn)
conn.commit()

ok = True
BLOQUEIO = "não tem acesso ao módulo"


def check(nome, cond, extra=""):
    global ok
    print(f"  {'OK  ' if cond else 'FALHA'} {nome} {extra}")
    ok = ok and bool(cond)


def entra(modulos, apps):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s["usuario_logado"] = {"id": 9, "usuario": "marcelo", "nome": "M", "role": "consulta",
                               # as duas empresas: com uma só, a guarda de empresa
                               # redireciona antes do login_required e a prova não o vê
                               "origem": "hub", "empresas": ["MKB", "GNILEB"],
                               "modulos": modulos, "apps": apps}
        s["csrf_token"] = "tok"
    r = c.get("/")
    return r.status_code, BLOQUEIO in r.get_data(as_text=True)


print("\n1. Card do FinHub no grupo Cliente (o caso do Marcelo)")
st, barrado = entra(["cliente"], ["dashboard-dre-mkb-gnileb"])
check("entra", not barrado and st != 403, f"(status {st})")

print("\n2. Card com o slug de banco novo")
st, barrado = entra(["cliente"], ["finhub"])
check("entra", not barrado and st != 403, f"(status {st})")

print("\n3. Só o módulo, como era antes (cookie sem `apps`)")
st, barrado = entra(["controladoria"], None)
check("continua entrando", not barrado and st != 403, f"(status {st})")

print("\n4. Sem o card e sem o módulo")
st, barrado = entra(["cliente"], ["outro-app"])
check("barrado com 403", barrado and st == 403, f"(status {st})")
st, barrado = entra([], [])
check("vazio também barra", barrado and st == 403, f"(status {st})")

print("\n5. APPS_HUB troca a lista")
import auth as AU                                                    # noqa: E402
check("lista padrão", AU.APPS_HUB == frozenset({"dashboard-dre-mkb-gnileb", "finhub"}))

print("\nRESULTADO:", "TUDO OK" if ok else "FALHOU")
sys.exit(0 if ok else 1)
