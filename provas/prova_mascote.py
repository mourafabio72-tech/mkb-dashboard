"""
prova_mascote.py -- trava o mascote do Pergunte à IA (2026-10-13).

O robô do canto aparece para quem está logado, em toda tela que estende o
base.html, menos na própria /ia (para onde ele leva). Sem login não aparece.
O logo é o arquivo da casa, e o desenho não puxa imagem de fora.

Rodar:  uv run --no-project --python 3.12 --with-requirements requirements.txt python provas/prova_mascote.py
"""
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "prova_mascote.db")

import app as A                                                     # noqa: E402
from ingestion import get_conn, criar_schema, seed_empresas         # noqa: E402

conn = get_conn()
criar_schema(conn)
seed_empresas(conn)
conn.commit()

ok = True


def check(nome, cond, extra=""):
    global ok
    print(f"  {'OK  ' if cond else 'FALHA'} {nome} {extra}")
    ok = ok and bool(cond)


def cli(sess):
    c = A.app.test_client()
    if sess:
        with c.session_transaction() as s:
            s["usuario_logado"] = sess
            s["csrf_token"] = "tok"
    return c


ADMIN = {"id": 1, "usuario": "adm", "role": "admin", "nome": "A"}
adm = cli(ADMIN)

print("\n1. Logado, o mascote está nas telas e leva à /ia")
html = adm.get("/").get_data(as_text=True)
check("o painel tem o mascote", "data-ia-mascote" in html)
check("com o corpo e o logo da casa no peito",
      "rb-peito" in html and "/static/bps4-logo.png" in html)
check("o clique leva à /ia", 'href="/ia" class="ia-mascote-botao"' in html)
check("o CSS e o JS dele entram com versão na URL",
      "mascote.css?v=" in html and "mascote.js?v=" in html)
canto = html.split("data-ia-mascote", 1)[1].split("</div>", 1)[0]
check("nenhuma imagem de fora no desenho", "http" not in canto and "<img" not in canto)

print("\n2. Onde ele não aparece")
r = adm.get("/ia")
check("na própria /ia, não (já está nela)", r.status_code == 200 and "data-ia-mascote" not in r.get_data(as_text=True))
r = cli(None).get("/login")
check("no login, sem sessão, não", "data-ia-mascote" not in r.get_data(as_text=True))

print("\nRESULTADO:", "OK" if ok else "FALHA")
sys.exit(0 if ok else 1)
