"""
prova_ia_config.py -- trava a configuração dos provedores de IA (Fase 2 do
"Pergunte à IA", 00_GENESIS/PLANO_FASEADO.md).

O que esta prova segura, sem rede (a chamada HTTP é trocada por dublê):
  1. a chave mora no diretório do banco; a variável de ambiente vence o arquivo;
  2. arquivo de chave e de config nasce com permissão 0o600;
  3. a URL de cada provedor é fixa (allowlist de duas) e a tela não tem campo de URL;
  4. /config/ia: sem sessão vai para o login, perfil leitura é barrado, admin vê;
  5. a chave nunca aparece inteira no HTML nem no JSON, só a máscara;
  6. salvar exige CSRF; campo vazio mantém a chave; chave e modelo inválidos são recusados;
  7. erro do provedor volta genérico, sem corpo nem chave;
  8. a rota antiga de aliases grava pelo ia_config e a sugestão de aliases
     continua funcionando com a chave salva por lá.

Rodar:  uv run --no-project --python 3.12 --with-requirements requirements.txt python provas/prova_ia_config.py
"""
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
DADOS = Path(tempfile.mkdtemp())
os.environ["DB_PATH"] = str(DADOS / "prova_ia.db")
for v in ("OPENAI_API_KEY", "NVIDIA_API_KEY"):
    os.environ.pop(v, None)

import ia_config                                                    # noqa: E402
POST_REAL = ia_config._post_json
import app as A                                                     # noqa: E402
from ingestion import get_conn                                      # noqa: E402

CHAVE_OA = "sk-provaOPENAIabcdefghij1234567890XYZ9"
CHAVE_NV = "nvapi-provaNVIDIAabcdefghij1234567890QRS7"
CHAVE_ENV = "sk-daVARIAVELdeAMBIENTEqwertyuiop0000"

ok = True


def check(nome, cond, extra=""):
    global ok
    print(f"  {'OK  ' if cond else 'FALHA'} {nome} {extra}")
    ok = ok and bool(cond)


class Duble:
    """Substitui ia_config._post_json: guarda o que seria enviado e devolve o combinado."""
    def __init__(self, status=200, corpo=None, erro=None):
        self.status, self.corpo, self.erro, self.chamadas = status, corpo, erro, []

    def __call__(self, url, corpo, cabecalhos, timeout):
        self.chamadas.append({"url": url, "corpo": corpo, "cab": cabecalhos, "timeout": timeout})
        if self.erro:
            raise self.erro
        return self.status, json.dumps(self.corpo or {}).encode()


def resposta_ok(texto="ok"):
    return {"choices": [{"message": {"content": texto}}]}


A.app.config["TESTING"] = True


def cliente(role=None):
    c = A.app.test_client()
    if role:
        with c.session_transaction() as s:
            s["usuario_logado"] = {"id": 1, "usuario": "t", "role": role, "nome": "T"}
            s["csrf_token"] = "tok-prova"
    return c


print("\n=== 1. onde a chave mora, e quem vence ===")
check("sem chave nenhuma, ler_chave é vazio", ia_config.ler_chave("openai") == "")
check("salvar chave válida não devolve erro", ia_config.salvar_chave("openai", CHAVE_OA) is None)
arq = DADOS / "openai_key.txt"
check("arquivo nasce no diretório do DB_PATH", arq.exists(), f"({arq})")
check("ler_chave lê o arquivo", ia_config.ler_chave("openai") == CHAVE_OA)
os.environ["OPENAI_API_KEY"] = CHAVE_ENV
check("variável de ambiente vence o arquivo", ia_config.ler_chave("openai") == CHAVE_ENV)
check("origem informada como ambiente", ia_config.origem_chave("openai") == "ambiente")
del os.environ["OPENAI_API_KEY"]
check("sem a variável, volta ao arquivo", ia_config.origem_chave("openai") == "arquivo")

print("\n=== 2. permissão dos arquivos ===")
ia_config.salvar_chave("nvidia", CHAVE_NV)
ia_config.salvar_config(ativo="nvidia")
for nome in ("openai_key.txt", "nvidia_key.txt", "ia_config.json"):
    modo = stat.S_IMODE((DADOS / nome).stat().st_mode)
    check(f"{nome} com 0o600", modo == 0o600, f"({oct(modo)})")
os.chmod(arq, 0o644)
ia_config.salvar_chave("openai", CHAVE_OA)
check("regravar reaperta para 0o600", stat.S_IMODE(arq.stat().st_mode) == 0o600)

print("\n=== 3. URL fixa ===")
urls = {p["url"] for p in ia_config.PROVEDORES.values()}
check("só as duas URLs da allowlist", urls == {
    "https://api.openai.com/v1/chat/completions",
    "https://integrate.api.nvidia.com/v1/chat/completions"})
tpl = (RAIZ / "templates" / "config_ia.html").read_text(encoding="utf-8")
check("tela sem campo de URL", not re.search(r'(name|id)="[^"]*url|type="url"|https?://', tpl, re.I))
d = Duble(corpo=resposta_ok())
ia_config._post_json = d
ia_config.chamar([{"role": "user", "content": "x"}], "nvidia")
check("chamada vai para a URL fixa da NVIDIA",
      d.chamadas[0]["url"] == "https://integrate.api.nvidia.com/v1/chat/completions")
check("modelo padrão da NVIDIA", d.chamadas[0]["corpo"]["model"] == "meta/llama-3.3-70b-instruct")
check("json_mode não vai para a NVIDIA", "response_format" not in d.chamadas[0]["corpo"])
ia_config.chamar([{"role": "user", "content": "x"}], "openai", json_mode=True)
check("json_mode vai para a OpenAI", d.chamadas[1]["corpo"].get("response_format") == {"type": "json_object"})
check("timeout padrão 30 s", d.chamadas[1]["timeout"] == 30)

print("\n=== 4. quem entra em /config/ia ===")
r = cliente().get("/config/ia")
check("sem sessão vai para o login", r.status_code == 302 and "/login" in r.headers["Location"],
      f"({r.status_code} {r.headers.get('Location')})")
r = cliente("leitura").get("/config/ia")
check("perfil leitura é barrado", r.status_code == 302 and "/config/ia" not in r.headers["Location"])
r = cliente("leitura").post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_openai": "sk-" + "x" * 30})
check("leitura não salva", r.status_code == 302 and ia_config.ler_chave("openai") == CHAVE_OA)
d_leit = Duble(corpo=resposta_ok())
ia_config._post_json = d_leit
r = cliente("leitura").post("/config/ia/testar", json={"provedor": "openai"}, headers={"X-CSRF-Token": "tok-prova"})
check("leitura não testa", r.status_code == 302 and d_leit.chamadas == [])
adm = cliente("admin")
r = adm.get("/config/ia")
check("admin abre", r.status_code == 200, f"({r.status_code})")
html = r.get_data(as_text=True)

print("\n=== 5. a chave não sai ===")
check("HTML sem a chave da OpenAI", CHAVE_OA not in html)
check("HTML sem a chave da NVIDIA", CHAVE_NV not in html)
check("HTML com a máscara", ia_config.mascarar(CHAVE_OA) in html, f"({ia_config.mascarar(CHAVE_OA)})")
check("máscara = 3 primeiros + ... + 4 últimos", ia_config.mascarar(CHAVE_OA) == "sk-...XYZ9")
check("estado_publico sem chave inteira", CHAVE_OA not in json.dumps(ia_config.estado_publico()))

print("\n=== 6. salvar ===")
r = adm.post("/config/ia/salvar", data={"chave_openai": ""})
check("POST sem token CSRF leva 400", r.status_code == 400, f"({r.status_code})")
r = adm.post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_openai": "", "chave_nvidia": "",
                                        "ativo": "openai", "modelo_openai": "gpt-4o", "modelo_nvidia": ""})
check("salvar com token redireciona", r.status_code == 302)
check("campo vazio mantém a chave", ia_config.ler_chave("openai") == CHAVE_OA and ia_config.ler_chave("nvidia") == CHAVE_NV)
cfg = ia_config.ler_config()
check("provedor ativo trocado", cfg["ativo"] == "openai")
check("modelo trocado; vazio mantém o outro", cfg["modelos"] == {"openai": "gpt-4o", "nvidia": "meta/llama-3.3-70b-instruct"})
adm.post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_nvidia": "sk-trocadoDeProvedor1234567890"})
check("chave com prefixo errado é recusada", ia_config.ler_chave("nvidia") == CHAVE_NV)
adm.post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_openai": "sk-com espaco 1234567890abcdef"})
check("chave com espaço é recusada", ia_config.ler_chave("openai") == CHAVE_OA)
check("modelo com caractere proibido é recusado", ia_config.validar_modelo("gpt;rm -rf") is not None)
check("modelo com mais de 80 caracteres é recusado", ia_config.validar_modelo("a" * 81) is not None)
check("provedor desconhecido é recusado", ia_config.salvar_config(ativo="anthropic") is not None)
NOVA = "nvapi-novaChaveNVIDIA0987654321zyxw"
adm.post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_nvidia": NOVA})
check("chave nova válida é gravada", ia_config.ler_chave("nvidia") == NOVA)

print("\n=== 7. erro do provedor é genérico ===")
ia_config._post_json = Duble(status=401, corpo={"error": {"message": "Invalid key " + NOVA}})
r = adm.post("/config/ia/testar", json={"provedor": "nvidia"}, headers={"X-CSRF-Token": "tok-prova"})
j = r.get_json()
check("401 vira mensagem curta", j == {"ok": False, "mensagem": "A NVIDIA respondeu HTTP 401."}, f"({j})")
check("JSON sem a chave", NOVA not in r.get_data(as_text=True))
ia_config._post_json = Duble(erro=OSError("conexão recusada por 10.0.0.5 " + NOVA))
j = adm.post("/config/ia/testar", json={"provedor": "nvidia"}, headers={"X-CSRF-Token": "tok-prova"}).get_json()
check("falha de rede vira mensagem curta", j["mensagem"] == "Não consegui falar com a NVIDIA agora.", f"({j})")
ia_config._post_json = Duble(status=200, corpo={"inesperado": True})
j = adm.post("/config/ia/testar", json={"provedor": "openai"}, headers={"X-CSRF-Token": "tok-prova"}).get_json()
check("resposta torta vira mensagem curta", j["mensagem"] == "A OpenAI devolveu uma resposta que não entendi.", f"({j})")
d = Duble(corpo=resposta_ok())
ia_config._post_json = d
j = adm.post("/config/ia/testar", json={"provedor": "openai"}, headers={"X-CSRF-Token": "tok-prova"}).get_json()
check("teste com sucesso", j["ok"] is True, f"({j})")
check("Authorization com Bearer da chave salva", d.chamadas[0]["cab"]["Authorization"] == f"Bearer {CHAVE_OA}")
r = adm.post("/config/ia/testar", json={"provedor": "http://169.254.169.254"}, headers={"X-CSRF-Token": "tok-prova"})
check("provedor fora da lista leva 400", r.status_code == 400)
r = adm.post("/config/ia/testar", json={"provedor": "openai"})
check("testar sem token CSRF leva 400", r.status_code == 400)

print("\n=== 7b. a chamada HTTP real (servidor local, sem internet) ===")
import http.server, threading                                       # noqa: E402
recebidos = {"alvo": 0}


class Provedor(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/401":
            corpo = ('{"error":"chave ' + CHAVE_OA + ' invalida"}').encode()
            self.send_response(401); self.send_header("Content-Length", str(len(corpo))); self.end_headers()
            self.wfile.write(corpo)
        elif self.path == "/redir":
            self.send_response(302); self.send_header("Location", f"http://127.0.0.1:{porta_alvo}/roubo")
            self.send_header("Content-Length", "0"); self.end_headers()
        else:
            recebidos["alvo"] += 1
            recebidos["auth"] = self.headers.get("Authorization")
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")

    do_GET = do_POST   # o urllib segue 302 como GET: o alvo conta do mesmo jeito


srv = http.server.HTTPServer(("127.0.0.1", 0), Provedor)
alvo = http.server.HTTPServer(("127.0.0.1", 0), Provedor)
porta, porta_alvo = srv.server_address[1], alvo.server_address[1]
for x in (srv, alvo):
    threading.Thread(target=x.serve_forever, daemon=True).start()
cab = {"Authorization": "Bearer " + CHAVE_OA, "Content-Type": "application/json"}
st, corpo = POST_REAL(f"http://127.0.0.1:{porta}/401", {}, cab, 5)
check("401 real volta só o código, corpo vazio", st == 401 and corpo == b"", f"({st} {corpo!r})")
st, corpo = POST_REAL(f"http://127.0.0.1:{porta}/redir", {}, cab, 5)
check("redirect não é seguido", st == 302 and recebidos["alvo"] == 0, f"({st}, alvo recebeu {recebidos['alvo']})")
srv.shutdown(); alvo.shutdown()

print("\n=== 7c. entrada torta não vira 500 ===")
ia_config._post_json = Duble(corpo=resposta_ok())
for corpo in ([1], "x", {"provedor": {"a": 1}}, {"provedor": [1]}):
    r = adm.post("/config/ia/testar", json=corpo, headers={"X-CSRF-Token": "tok-prova"})
    check(f"testar com {corpo!r} leva 400", r.status_code == 400, f"({r.status_code})")
r = adm.post("/config/ia/salvar", data={"csrf_token": "é"})
check("token CSRF com acento leva 400, não 500", r.status_code == 400, f"({r.status_code})")
(DADOS / "ia_config.json").write_text("[]")
check("config.json torto cai no padrão", ia_config.ler_config()["ativo"] == "openai")
check("e a tela abre", adm.get("/config/ia").status_code == 200)
(DADOS / "ia_config.json").write_text('{"modelos": [1]}')
check("modelos torto cai no padrão", ia_config.ler_config()["modelos"]["openai"] == "gpt-4o-mini")

print("\n=== 7d. ou salva tudo, ou nada; e deixa rastro sem a chave ===")
import io, contextlib                                               # noqa: E402
antes = (ia_config.ler_chave("openai"), ia_config.ler_chave("nvidia"), ia_config.ler_config())
OUTRA = "sk-outraChaveValida1234567890abcdEFGH"
adm.post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_openai": OUTRA,
                                    "chave_nvidia": "nvapi-x", "ativo": "nvidia"})
depois = (ia_config.ler_chave("openai"), ia_config.ler_chave("nvidia"), ia_config.ler_config())
check("chave inválida numa ponta não grava a outra", antes == depois)
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    adm.post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_openai": OUTRA})
log = buf.getvalue()
check("troca de chave vira evento IA_CONFIG_ALTERADA", '"event": "IA_CONFIG_ALTERADA"' in log and '"openai"' in log)
check("o log não carrega a chave", OUTRA not in log and "sk-" not in log)
check("gravação sem temporário sobrando", not list(DADOS.glob(".ia-*")))
adm.post("/config/ia/salvar", data={"csrf_token": "tok-prova", "chave_openai": CHAVE_OA})

print("\n=== 7e. arquivos de chave fora do git e da imagem ===")
import subprocess                                                   # noqa: E402
ign = subprocess.run(["git", "check-ignore", "openai_key.txt", "nvidia_key.txt", "ia_config.json"],
                     cwd=RAIZ, capture_output=True, text=True).stdout.split()
check("os três no .gitignore", sorted(ign) == ["ia_config.json", "nvidia_key.txt", "openai_key.txt"], f"({ign})")
di = (RAIZ / ".dockerignore").read_text().split()
check("os três no .dockerignore", all(n in di for n in ("openai_key.txt", "nvidia_key.txt", "ia_config.json")))

print("\n=== 8. aliases continuam funcionando ===")
(DADOS / "openai_key.txt").unlink()
r = adm.post("/cadastro/aliases/sugerir-ia", data={"csrf_token": "tok-prova"})
check("sem chave, sugestão avisa", r.status_code == 400 and "não configurada" in r.get_json()["erro"])
r = adm.post("/cadastro/aliases/config-ia", data={"csrf_token": "tok-prova", "api_key": "chave-sem-prefixo-123456789"})
check("rota antiga recusa chave sem sk-", ia_config.ler_chave("openai") == "")
adm.post("/cadastro/aliases/config-ia", data={"csrf_token": "tok-prova", "api_key": CHAVE_OA})
check("rota antiga grava pelo ia_config", ia_config.ler_chave("openai") == CHAVE_OA
      and stat.S_IMODE((DADOS / "openai_key.txt").stat().st_mode) == 0o600)
r = adm.get("/cadastro/aliases")
check("tela de aliases enxerga a chave", r.status_code == 200 and CHAVE_OA not in r.get_data(as_text=True))

conn = get_conn()
conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, historico) "
             "VALUES (1, '2026-08', '2026-08-10', '4.1.1.01.01.001', 'D1', 'NF 123 DE ACME SERVICOS LTD')")
conn.commit()
conn.close()


class FakeOpenAI:
    recebido = {}

    def __init__(self, api_key):
        FakeOpenAI.recebido["api_key"] = api_key
        msg = type("M", (), {"content": '[{"canonical": "ACME SERVICOS LTDA", "nomes": ["ACME SERVICOS LTD"]}]'})
        resp = type("R", (), {"choices": [type("C", (), {"message": msg})]})
        self.chat = type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(lambda **kw: resp)})})


import openai                                                       # noqa: E402
openai.OpenAI = FakeOpenAI
r = adm.post("/cadastro/aliases/sugerir-ia", data={"csrf_token": "tok-prova"})
j = r.get_json()
check("sugestão de aliases responde", r.status_code == 200 and j["sugestoes"][0]["canonical"] == "ACME SERVICOS LTDA", f"({r.status_code} {j})")
check("SDK recebeu a chave salva pelo ia_config", FakeOpenAI.recebido.get("api_key") == CHAVE_OA)


def explode(**kw):
    raise RuntimeError("Error code: 401 - {'error': 'Incorrect API key provided: " + CHAVE_OA + "'}")


FakeOpenAI.__init__ = lambda self, api_key: setattr(self, "chat", type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(explode)})}))
r = adm.post("/cadastro/aliases/sugerir-ia", data={"csrf_token": "tok-prova"})
check("erro do SDK não vaza a chave nem o corpo", r.status_code == 502 and CHAVE_OA not in r.get_data(as_text=True),
      f"({r.status_code})")

print("\n" + ("PROVA VERDE" if ok else "PROVA VERMELHA"))
sys.exit(0 if ok else 1)
