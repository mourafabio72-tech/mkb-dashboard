"""
prova_ia_analisar.py -- trava o modo Analisar do "Pergunte à IA" (Fase 4).

O servidor recalcula (não aceita número do navegador) e manda à IA só totais:
rótulo, mês e valor. Nunca histórico, documento, NF, linha de razão nem nome
de cliente ou fornecedor (pode ser pessoa física). IA trocada por dublê.

Rodar:  uv run --no-project --python 3.12 --with-requirements requirements.txt python provas/prova_ia_analisar.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
DADOS = Path(tempfile.mkdtemp())
os.environ["DB_PATH"] = str(DADOS / "prova_anal.db")
for v in ("OPENAI_API_KEY", "NVIDIA_API_KEY"):
    os.environ.pop(v, None)

import ia_config                                                    # noqa: E402
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
NOMES = ["JOAO DA SILVA", "MARIA PEREIRA", "ACME SERVICOS LTDA"]
for i, nome in enumerate(NOMES):
    conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, historico, valor, credito, debito) "
                 "VALUES (1, '2026-08', '2026-08-10', '3.1.1.01.01.001', ?, ?, ?, ?, 0)",
                 (f"DOC{i}", f"VL. NF. 77{i} - {nome}", 1000.0 * (i + 1), 1000.0 * (i + 1)))
conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, historico, valor, credito, debito) "
             "VALUES (2, '2026-08', '2026-08-10', '3.1.1.01.01.001', 'G1', 'VL. NF. 1 - CLIENTE GNI', 500, 500, 0)")
conn.commit()
conn.close()
ia_config.salvar_chave("openai", "sk-provaANALISARabcdefghij1234567")


class IA:
    """1ª chamada devolve o filtro; 2ª devolve o texto da análise. Guarda os payloads."""
    def __init__(self):
        self.filtro, self.analise, self.payloads = {}, "", []

    def __call__(self, url, corpo, cab, timeout):
        self.payloads.append(corpo)
        primeira = corpo["messages"][0]["content"] == P.PROMPT_SISTEMA
        txt = json.dumps(self.filtro) if primeira else self.analise
        return 200, json.dumps({"choices": [{"message": {"content": txt}}]}).encode()


ia = IA()
ia_config._post_json = ia
A.app.config["TESTING"] = True


def cli(sess):
    c = A.app.test_client()
    with c.session_transaction() as s:
        if sess:
            s["usuario_logado"] = sess
        s["csrf_token"] = "tok"
    return c


adm = cli({"id": 1, "usuario": "adm", "role": "admin", "nome": "A"})
FILTRO = {"intencao": "receita_cliente", "empresa": "mkb", "cliente": "silva", "inicio": "2026-08", "fim": "2026-08"}


def analisar(c, filtro, corpo=None, texto="analise a receita por cliente"):
    P._baldes.clear()
    ia.filtro, ia.payloads = filtro, []
    return c.post("/ia/analisar", json=corpo or {"pergunta": texto}, headers={"X-CSRF-Token": "tok"})


print("\n=== 1. o pacote só tem totais ===")
ia.analise = "A MKB faturou 6.000 em agosto.   O Cliente 3 concentra metade."
r = analisar(adm, {**FILTRO, "cliente": None})
j = r.get_json()
check("responde 200 com o resultado e a análise", r.status_code == 200 and j["tipo"] == "tabela"
      and j["analise"] == "A MKB faturou 6.000 em agosto. O Cliente 3 concentra metade.", f"({r.status_code} {j.get('analise')})")
check("tabela da tela mantém os nomes reais", {x["rotulo"] for x in j["linhas"]} == set(NOMES))
check("duas chamadas: filtro e análise", len(ia.payloads) == 2)
env = json.dumps(ia.payloads[1], ensure_ascii=False)
pac = json.loads(ia.payloads[1]["messages"][1]["content"].strip('"'))
check("pacote só com assunto, itens e totais", set(pac) <= {"assunto", "itens", "valor", "total", "variacao", "variacao_pct", "rotulo", "observacao"}, f"({sorted(pac)})")
check("cada item só com rótulo e valor", all(set(x) == {"rotulo", "valor"} for x in pac["itens"]))
check("nenhum nome de cliente vai para a IA", not any(n in env for n in NOMES), f"({[x['rotulo'] for x in pac['itens']]})")
check("nomes viram Cliente 1, 2, 3", [x["rotulo"] for x in pac["itens"]] == ["Cliente 1", "Cliente 2", "Cliente 3"])
for proib in ("historico", "documento", "DOC0", "VL. NF", "770", "razao", "conta_cod", "3.1.1.01"):
    check(f"sem '{proib}' no que vai para a IA", proib not in env)
check("o total vai", pac["total"] == 6000.0)
r = analisar(adm, FILTRO)
env = json.dumps(ia.payloads[1], ensure_ascii=False).upper()
check("nome citado na pergunta também não vai", "SILVA" not in env, f"({ia.payloads[1]['messages'][1]['content'][:120]})")

print("\n=== 2. o servidor recalcula, não aceita número do navegador ===")
r = analisar(adm, {**FILTRO, "cliente": None}, corpo={"pergunta": "analise", "linhas": [{"rotulo": "X", "valor": 999999}],
                                                     "total": 123456, "valor": 777777})
env = json.dumps(ia.payloads[1])
check("números do corpo ignorados", "999999" not in env and "123456" not in env and "777777" not in env
      and r.get_json()["total"] == 6000.0)
import inspect                                                      # noqa: E402
fonte_rota = inspect.getsource(A.ia_analisar)
check("rota não lê o corpo por conta própria (só via _ia_ler_pergunta)",
      "request" not in fonte_rota and "_ia_ler_pergunta()" in fonte_rota)

print("\n=== 3. prompt e texto devolvido ===")
p = ia.payloads[1]
check("prompt de sistema separado", p["messages"][0]["content"] == P.PROMPT_ANALISE and p["messages"][0]["role"] == "system")
check("prompt manda usar só os números", "SOMENTE os números" in P.PROMPT_ANALISE and "Não invente número" in P.PROMPT_ANALISE)
check("prompt manda até 6 frases, em português", "no máximo 6 frases" in P.PROMPT_ANALISE and "português" in P.PROMPT_ANALISE)
ia.analise = "<script>alert(1)</script> " + "x" * 3000
j = analisar(adm, {**FILTRO, "cliente": None}).get_json()
check("texto volta puro (o front escapa com textContent) e cortado", j["analise"].startswith("<script>") and len(j["analise"]) == P.MAX_ANALISE)

print("\n=== 3b. outros caminhos do pacote ===")
conn = get_conn()
conn.execute("INSERT INTO razao (empresa_id, competencia, data_lanc, conta_cod, documento, historico, valor, credito, debito) "
             "VALUES (1, '2026-08', '2026-08-11', '4.4.1.02.01.999', 'F1', 'NF 901 DE PEDRO ALVES ME', -300, 0, 300)")
for o, (d, v, dest) in enumerate((("Base", 1.0, 0), ("Lucro", 2.0, 0), ("IRPJ a recolher " + "x" * 200, 99.0, 1)), 1):
    conn.execute("INSERT INTO irpj_csll (empresa_id, competencia, secao, ordem, descricao, valor, is_destaque) "
                 "VALUES (1, '2026-08', 'IRPJ', ?, ?, ?, ?)", (o, d, v, dest))
conn.commit()
conn.close()
ia.analise = "ok"
r = analisar(adm, {"intencao": "despesa_fornecedor", "empresa": "mkb", "inicio": "2026-08", "fim": "2026-08"})
env = json.dumps(ia.payloads[-1], ensure_ascii=False) if len(ia.payloads) > 1 else ""
check("fornecedor também vira 'Fornecedor n'", r.status_code == 200 and "PEDRO" not in env and "Fornecedor 1" in env,
      f"({r.status_code} {r.get_json().get('tipo')})")
r = analisar(adm, {"intencao": "despesa_fornecedor", "empresa": "mkb", "fornecedor": 'pedro" alves', "inicio": "2026-08"})
env = json.dumps(ia.payloads[-1], ensure_ascii=False).upper()
check("nome com aspas na busca não vai para a IA", len(ia.payloads) == 2 and "PEDRO" not in env and "ALVES" not in env)
r = analisar(adm, {"intencao": "irpj_csll", "empresa": "mkb", "competencia": "2026-08"})
pac = json.loads(ia.payloads[-1]["messages"][1]["content"].strip('"'))
check("rótulo de planilha cortado em 60", r.status_code == 200 and all(len(x["rotulo"]) <= 60 for x in pac["itens"]), f"({pac['itens']})")


class IAparte(IA):
    def __call__(self, url, corpo, cab, timeout):
        if corpo["messages"][0]["content"] == P.PROMPT_SISTEMA:
            return super().__call__(url, corpo, cab, timeout)
        return 200, json.dumps({"choices": [{"message": {"content": [{"type": "text", "text": "x"}]}}]}).encode()


ia_config._post_json = IAparte()
ia_config._post_json.filtro = {**FILTRO, "cliente": None}
r = adm.post("/ia/analisar", json={"pergunta": "a"}, headers={"X-CSRF-Token": "tok"})
check("content que não é texto vira 502, não 500", r.status_code == 502, f"({r.status_code})")
ia_config._post_json = ia

r = analisar(adm, {"intencao": "consulta", "base": "despesa", "fornecedor": "pedro", "historico": "NF 901",
                   "agrupar": "fornecedor", "inicio": "2026-08", "empresa": "mkb"})
env = json.dumps(ia.payloads[-1], ensure_ascii=False).upper()
check("consulta no Analisar: nome e texto do histórico não vão", r.status_code == 200 and len(ia.payloads) == 2
      and "PEDRO" not in env and "NF 901" not in env and "FORNECEDOR 1" in env, f"({r.status_code} {env[-200:]})")

r = analisar(adm, {"intencao": "consulta", "base": "razao", "conta": "Maria Silva CPF 123", "agrupar": "mes",
                   "inicio": "2026-08", "empresa": "mkb"})
check("texto de conta digitado não vai no assunto (sem conta que case, nem chama a IA)",
      "Maria" not in json.dumps(ia.payloads, ensure_ascii=False))
conn = get_conn()
conn.execute("INSERT OR REPLACE INTO contas (cod, empresa_id, descricao) VALUES ('3.1.1.01.01.001', 1, 'VENDA DE SERVICOS')")
conn.commit(); conn.close()
r = analisar(adm, {"intencao": "consulta", "base": "razao", "conta": "venda de serv", "agrupar": "mes", "inicio": "2026-08", "empresa": "mkb"})
pac = json.loads(ia.payloads[-1]["messages"][1]["content"].strip('"'))
check("assunto usa o nome da conta do plano, não o texto digitado", "VENDA DE SERVICOS" in pac["assunto"] and "venda de serv" not in pac["assunto"], f"({pac['assunto']})")

print("\n=== 4. sem resultado, não chama a IA de novo ===")
j = analisar(adm, {"intencao": "dre_linha", "empresa": "mkb", "inicio": "2019-01", "fim": "2019-01"}).get_json()
check("vazio: uma chamada só, sem análise", j["tipo"] == "vazio" and len(ia.payloads) == 1 and "analise" not in j)
j = analisar(adm, {"intencao": "nada"}).get_json()
check("não entendi: uma chamada só", j["tipo"] == "nao_entendi" and len(ia.payloads) == 1)

print("\n=== 5. acesso, CSRF, chave ===")
so = cli({"id": 7, "usuario": "c", "role": "leitura", "nome": "C", "origem": "hub", "empresas": ["MKB"], "modulos": ["controladoria"]})
r = analisar(so, {**FILTRO, "empresa": "gnileb", "cliente": None})
check("sessão só MKB pedindo GNILEB recebe 404 genérico", r.status_code == 404 and len(ia.payloads) == 1
      and "GNI" not in r.get_data(as_text=True))
r = adm.post("/ia/analisar", json={"pergunta": "x"})
check("sem token CSRF leva 400", r.status_code == 400)
r = cli(None).post("/ia/analisar", json={"pergunta": "x"}, headers={"X-CSRF-Token": "tok"})
check("sem sessão vai para o login", r.status_code == 302 and "/login" in r.headers["Location"])
r = analisar(adm, FILTRO, corpo={"pergunta": "y" * 301})
check("pergunta acima de 300 leva 400", r.status_code == 400)
(DADOS / "openai_key.txt").unlink()
r = analisar(adm, FILTRO)
check("sem chave leva 409", r.status_code == 409)
ia_config.salvar_chave("openai", "sk-provaANALISARabcdefghij1234567")

print("\n=== 6. balde compartilhado com o Perguntar ===")
P._baldes.clear()
ia.filtro = {"intencao": "folha", "empresa": "mkb"}
cods = [adm.post("/ia/perguntar", json={"pergunta": "p"}, headers={"X-CSRF-Token": "tok"}).status_code for _ in range(19)]
cods.append(adm.post("/ia/analisar", json={"pergunta": "a"}, headers={"X-CSRF-Token": "tok"}).status_code)
r = adm.post("/ia/analisar", json={"pergunta": "a"}, headers={"X-CSRF-Token": "tok"})
check("19 perguntas + 1 análise passam, a próxima leva 429", cods == [200] * 20 and r.status_code == 429, f"({cods[-2:]} {r.status_code})")

print("\n=== 7. log ===")
ia.analise = "TEXTO DA ANALISE SECRETO"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    analisar(adm, {**FILTRO, "cliente": None}, texto="PERGUNTA PRIVADA")
log = buf.getvalue()
check("evento IA_ANALISE", '"event": "IA_ANALISE"' in log)
check("sem pergunta nem análise no log", "PERGUNTA PRIVADA" not in log and "SECRETO" not in log)

print("\n" + ("PROVA VERDE" if ok else "PROVA VERMELHA"))
sys.exit(0 if ok else 1)
