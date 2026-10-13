"""
prova_ia_conversa.py -- trava a janela do mascote em texto livre (2026-10-14).

Banco temporário com razão de duas empresas; o provedor é um dublê que anota o
que SAIRIA e responde com um código. O que ela trava:
  - nome de cliente e fornecedor, histórico do razão e número de NF não saem;
  - cliente e fornecedor vão em campos separados, com código neutro (X01);
  - o nome citado vira código na pergunta e volta como nome na resposta;
  - quem só vê a MKB não manda nada da Gnileb;
  - modelo gpt-4.1-mini, temperatura 0, histórico de 4;
  - a rota exige login, CSRF e a chave configurada.

Rodar:  uv run --no-project --python 3.12 --with-requirements requirements.txt python provas/prova_ia_conversa.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
DADOS = Path(tempfile.mkdtemp())
os.environ["DB_PATH"] = str(DADOS / "prova_conversa.db")
for v in ("OPENAI_API_KEY", "NVIDIA_API_KEY", "OPENAI_MODEL"):
    os.environ.pop(v, None)

import ia_config                                                    # noqa: E402
import ia_conversa as C                                             # noqa: E402
import ia_perguntas as P                                            # noqa: E402
import app as A                                                     # noqa: E402
from ingestion import get_conn, criar_schema, seed_empresas         # noqa: E402

ok = True


def check(nome, cond, extra=""):
    global ok
    print(f"  {'OK  ' if cond else 'FALHA'} {nome} {extra}")
    ok = ok and bool(cond)


conn = get_conn()
criar_schema(conn)
seed_empresas(conn)
mapa = json.loads((RAIZ / "account_map.json").read_text())
CONTA_DESP = next(p for p, g in mapa.items() if isinstance(g, str) and g.startswith("DADM")
                  and g not in P.GRUPOS_FOLHA and p.startswith("4.")) + "999"
n = 0


def lanc(emp, comp, conta, valor, hist):
    global n
    n += 1
    conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, historico, valor, "
                 "debito, credito) VALUES (?,?,?,?,?,?,?,?,?)",
                 (emp, comp, comp + "-10", conta, f"D{n}", hist, valor,
                  -valor if valor < 0 else 0, valor if valor > 0 else 0))


lanc(1, "2026-08", "3.1.1.01.01.001", 12000.0, "VL. NF. 101 - SMART LUZ ENERGIA LTDA")
lanc(1, "2026-07", "3.1.1.01.01.001", 9000.0, "VL. NF. 90 - SMART LUZ ENERGIA LTDA")
lanc(1, "2026-08", "3.1.1.01.01.001", 3000.0, "VL. NF. 102 - PADARIA SAO JOSE ME")
lanc(1, "2026-08", CONTA_DESP, -700.0, "NF 555 DE PAPELARIA FORNECEDORA SA")
lanc(2, "2026-08", "3.1.1.01.01.001", 777.0, "VL. NF. 9 - CLIENTE SECRETO DA GNILEB LTDA")
conn.commit()
conn.close()
ia_config.salvar_chave("openai", "sk-provaCONVERSAabcdefghij123456")


class IA:
    def __init__(self):
        self.texto, self.payloads = "X01 faturou R$ 12.000,00 em agosto.", []

    def __call__(self, url, corpo, cab, timeout):
        import re
        self.payloads.append(corpo)
        # Responde com o código que a pergunta de fato carregou (o da SMARTLUZ).
        achado = re.search(r"X\d{2}", corpo["messages"][-1]["content"])
        texto = self.texto.replace("X01", achado.group(0)) if achado else self.texto
        return 200, json.dumps({"choices": [{"message": {"content": texto}}]}).encode()


ia = IA()
ia_config._post_json = ia
A.app.config["TESTING"] = True


def cli(sess):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s["usuario_logado"] = sess
        s["csrf_token"] = "tok"
    return c


ADMIN = {"id": 1, "usuario": "adm", "role": "admin", "nome": "A"}
SO_MKB = {"id": 7, "usuario": "cli", "role": "leitura", "nome": "C", "origem": "hub",
          "empresas": ["MKB"], "modulos": ["controladoria"]}


def conversar(c, pergunta, historico=None):
    P._baldes.clear()
    return c.post("/ia/conversar", json={"pergunta": pergunta, "historico": historico or []},
                  headers={"X-CSRF-Token": "tok"})


print("\n=== 1. nome citado vira código e volta como nome ===")
r = conversar(cli(ADMIN), "Quanto a SMARTLUZ faturou?",
              [{"papel": "assistente", "texto": "Padaria Sao Jose faturou R$ 3.000,00."}] * 6)
check("200", r.status_code == 200, r.get_data(as_text=True)[:200])
corpo = json.loads(ia.payloads[-1]) if isinstance(ia.payloads[-1], (str, bytes)) else ia.payloads[-1]
saiu = json.dumps(corpo, ensure_ascii=False).lower()
check("a pergunta saiu com o código", "smartluz" not in corpo["messages"][-1]["content"].lower()
      and "X0" in corpo["messages"][-1]["content"], corpo["messages"][-1]["content"])
check("a resposta voltou com o nome", "Smart Luz Energia" in (r.get_json() or {}).get("resposta", ""),
      (r.get_json() or {}).get("resposta"))

print("\n=== 2. o que NÃO sai ===")
for termo in ("smart luz", "padaria", "papelaria", "secreto", "nf. 101", "vl. nf", "nf 555"):
    check(f"nada de '{termo}' no que sairia", termo not in saiu)

print("\n=== 3. cliente e fornecedor separados, código neutro ===")
dados = json.loads(corpo["messages"][1]["content"].split("DADOS:\n", 1)[1])
check("clientes da MKB vêm com o campo 'cliente'", all("cliente" in x for x in dados["clientes"]["mkb"]))
check("fornecedores da MKB vêm com o campo 'fornecedor'", all("fornecedor" in x for x in dados["fornecedores"]["mkb"])
      and len(dados["fornecedores"]["mkb"]) >= 1)
check("código neutro X, nunca C", all(x["cliente"].startswith("X") for x in dados["clientes"]["mkb"]))
check("o citado vem com o papel", any(c["papel"] == "cliente" for c in dados["citados"]))
check("a DRE mensal vem por empresa e consolidado", set(dados["dre_mensal"]) >= {"mkb", "gnileb", "consolidado"})

print("\n=== 4. precisão ===")
check("modelo gpt-4.1-mini", corpo["model"] == "gpt-4.1-mini", corpo["model"])
check("temperatura 0", corpo["temperature"] == 0)
check("histórico de no máximo 4", len(corpo["messages"]) <= 2 + 4 + 1, str(len(corpo["messages"])))
check("as instruções separam cliente de fornecedor", "NUNCA se trocam" in C.INSTRUCOES)

print("\n=== 5. escopo da sessão ===")
r = conversar(cli(SO_MKB), "Quanto faturamos?")
corpo = ia.payloads[-1]
dados = json.loads(corpo["messages"][1]["content"].split("DADOS:\n", 1)[1])
check("quem só vê a MKB não manda a Gnileb", dados["empresas_visiveis"] == ["mkb"]
      and "gnileb" not in dados["dre_mensal"] and "consolidado" not in dados["dre_mensal"])

print("\n=== 6. as travas da rota ===")
anon = A.app.test_client()
check("sem login não conversa", anon.post("/ia/conversar", json={"pergunta": "x"}).status_code in (302, 400, 401))
check("sem CSRF, 400", cli(ADMIN).post("/ia/conversar", json={"pergunta": "x"}).status_code == 400)
check("pergunta vazia, 400", conversar(cli(ADMIN), "  ").status_code == 400)
(DADOS / "openai_key.txt").unlink()
check("sem chave, 409", conversar(cli(ADMIN), "x").status_code == 409)

print("\nPROVA VERDE" if ok else "\nPROVA VERMELHA")
sys.exit(0 if ok else 1)
