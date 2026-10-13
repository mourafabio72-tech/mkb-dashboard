"""
ia_conversa.py -- a janela do mascote responde em texto livre (2026-10-14).

Pedido do Fábio: "aplique esse modelo para os demais apps", o modelo do
FinControl. Até aqui a janela do FinHub usava o /ia/perguntar, em que a IA só
traduz a pergunta num filtro e o FinHub desenha uma tabela. Agora ela conversa:
o FinHub manda os NÚMEROS à IA e a IA responde em texto. O /ia/perguntar e a
tela /ia continuam como estavam.

TRÊS DECISÕES QUE VALEM SER LIDAS ANTES DE MEXER AQUI:

1. NOME DE CLIENTE E DE FORNECEDOR NÃO SAI. Saem a DRE mensal, a receita por
   cliente e a despesa por fornecedor, mas cada cliente e fornecedor vai como
   código neutro (X01, X02...), achado e trocado aqui, e destrocado na resposta.
   Código neutro, e não "C01": no FinControl o C lia como "cliente" e a IA
   chamava fornecedor de cliente. Histórico do razão e número de NF não saem.
   Decisão do Fábio em 2026-10-14 ("pode, como no FinControl"), que troca a
   regra antiga desta janela (só a pergunta saía).
2. O ESCOPO É O DA SESSÃO. Só entram as empresas de `empresas_permitidas()`, o
   mesmo corte de todo o resto do FinHub.
3. PRECISÃO ANTES DE TUDO. Modelo gpt-4.1-mini (o 4o-mini se perdia no JSON
   grande), temperatura 0, histórico de 4 mensagens, e instruções que proíbem
   estimar. Os campos dizem o sentido do dinheiro no próprio nome.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata

import ia_config
from config import EMPRESAS
from dre_engine import (DRE_META, analisar_despesas_fornecedores, analisar_receita_clientes,
                        calcular_dre_mensal)

MAX_HISTORICO = 4
MAX_TEXTO_HISTORICO = 2000
MESES_DRE = 12
TOP = 20
MAX_CITADOS = 8
MAX_POR_TERMO = 4
MODELO_OPENAI = "gpt-4.1-mini"
CACHE_SEG = 300

LINHAS = {lid: re.sub(r"^\([^)]*\)\s*", "", label) for lid, label, _t, _s in DRE_META}

INSTRUCOES = """Você é o assistente do FinHub, a DRE e o financeiro contábil das empresas do Grupo Markbuilding (MKB e Gnileb), atendidas pela BPS4.
Responda SOMENTE com base nos DADOS em JSON que vêm a seguir. Se o dado não estiver lá, diga que não tem;
nunca estime, complete ou invente valor, mês ou nome.

O QUE É CADA COISA:
- Os números são CONTÁBEIS, por competência (o mês do lançamento no razão do Protheus), e não de caixa.
  O FinHub não sabe se um cliente PAGOU ou se uma conta foi QUITADA: isso fica no FinControl. Se perguntarem
  "pagou?", explique isso e diga o que o FinHub sabe (o faturamento ou a despesa lançada).
- "dre_mensal": a DRE por empresa e mês. Receitas positivas; custos e despesas negativos.
- "clientes": a RECEITA BRUTA faturada a cada cliente (dinheiro que o grupo tem a receber deles), por mês.
- "fornecedores": a DESPESA lançada de cada fornecedor (dinheiro que o grupo deve ou pagou a eles), por mês,
  sem folha, encargos e pró-labore. Valores de despesa vêm negativos.
- Cliente e fornecedor NUNCA se trocam: quem está em "clientes" é cliente, quem está em "fornecedores" é
  fornecedor. Os dois aparecem como códigos neutros (X01, X02...). Escreva o código exatamente como veio;
  o sistema troca pelo nome antes de mostrar. Nunca adivinhe nomes.
- "citados": os clientes e fornecedores que a pergunta citou, com a série mês a mês. Se a pergunta cita
  um nome que não virou código, diga que não achou esse cliente ou fornecedor no razão.
- Meses vêm como AAAA-MM. Escreva "agosto de 2026", não "2026-08".

COMO RESPONDER: valores em reais no formato R$ 1.234,56; porcentagens inteiras; português do Brasil, curto
e direto; lista quando houver mais de dois itens; diga sempre a empresa (MKB, Gnileb ou consolidado)."""


class ErroConversa(Exception):
    """Falha que a tela mostra como frase."""


# ---- Nomes citados: achar, codificar, destrocar (o mesmo do FinControl) ------

GENERICAS = set((
    "comercio servicos servico industria engenharia energia solar construcoes construtora consultoria "
    "assessoria contabilidade contabil transportes transporte distribuidora representacoes empreendimentos "
    "participacoes holding tecnologia sistemas solucoes grupo brasil brasileira nacional materiais produtos "
    "alimentos importacao exportacao administracao administradora associacao condominio instituto centro "
    "clinica hotel hoteis restaurante posto banco caixa receita federal prefeitura municipal estado governo "
    "secretaria fundo cliente fornecedor empresa pagou pagamento hoje semana valor quanto clientes "
    "fornecedores empresas pagamentos recebimento recebimentos recebido recebidos recebeu pago pagos pagar "
    "receber aberto vencido vencidos vencer venceu ontem amanha mes ano dia dias todas todos todo liste "
    "lista listar mostre mostra olhe existe existem quais qual quem onde quando como total totais valores "
    "saldo saldos conta contas despesa despesas receitas maior maiores menor menores faturou faturamento "
    "gastou gasto gastos custo custos lucro resultado margem mkb gnileb consolidado janeiro fevereiro marco "
    "abril maio junho julho agosto setembro outubro novembro dezembro predial gerenciamento ltda eireli"
).split())
_SUFIXOS = ("ltda", "me", "epp", "eireli", "s a", "sa", "s/a", "mei", "ss", "limitada")


def sem_acento(t) -> str:
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def chave_do_nome(nome) -> str:
    """Núcleo do nome: sem acento, caixa, pontuação e forma jurídica no fim."""
    t = sem_acento(nome)
    mudou = True
    while mudou and t:
        mudou = False
        for suf in _SUFIXOS:
            if t.endswith(" " + suf) and len(t) > len(suf) + 1:
                t = t[: -len(suf) - 1].strip()
                mudou = True
    return t


def rotulo_do_nome(nome) -> str:
    return " ".join(str(nome or "").split()).title()


_VARIANTES = {"a": "aáàâãä", "e": "eéèêë", "i": "iíìîï", "o": "oóòôõö", "u": "uúùûü", "c": "cç"}
_FORA = r"[^0-9A-Za-zÀ-ÿ]"


def _regex_do_termo(termo: str):
    corpo = f"{_FORA}+".join("".join(f"[{_VARIANTES[ch]}]" if ch in _VARIANTES else re.escape(ch) for ch in w)
                             for w in termo.split())
    return re.compile(rf"(^|{_FORA})({corpo})(?=$|{_FORA})", re.IGNORECASE)


def pseudonimizar(pergunta: str, historico: list, nomes: list) -> dict:
    """Acha os nomes citados (inteiros, ou por palavra/par de palavras contido no
    nome sem espaços) e troca por código. Devolve pergunta e histórico já
    codificados e a lista `citados` [{codigo, nomes, rotulo}]."""
    grupos: dict[str, dict] = {}
    for n in nomes or []:
        k = chave_do_nome(n)
        if not k:
            continue
        marca = next((w for w in k.split() if len(w) >= 4 and not w.isdigit() and w not in GENERICAS), None)
        g = grupos.setdefault(k, {"nucleo": k, "compacto": k.replace(" ", ""), "nomes": [], "marca": marca})
        if n not in g["nomes"]:
            g["nomes"].append(n)
    textos = [pergunta or ""] + [str((h or {}).get("texto") or "") for h in historico or []]
    palavras = sem_acento(" \n ".join(textos)).split()
    alvo = " " + " ".join(palavras) + " "
    termos_de: dict[str, set] = {}
    for k, g in grupos.items():
        if f" {k} " in alvo:
            termos_de.setdefault(k, set()).add(k)
    candidatos = set(palavras) | {f"{a} {b}" for a, b in zip(palavras, palavras[1:])}
    for termo in candidatos:
        ws = termo.split()
        if any(w in GENERICAS or len(w) < 2 for w in ws):
            continue
        compacto = "".join(ws)
        if compacto.isdigit():
            continue
        hits = [g for g in grupos.values()
                if (len(compacto) >= 5 and compacto in g["compacto"]) or (len(ws) == 1 and g["marca"] == termo)]
        if hits and len(hits) <= MAX_POR_TERMO:
            for g in hits:
                termos_de.setdefault(g["nucleo"], set()).add(termo)
    achados = sorted(termos_de, key=lambda k: k)[:MAX_CITADOS]
    citados = []
    for i, k in enumerate(achados, 1):
        g = grupos[k]
        termos = set(termos_de[k]) | {g["nucleo"]} | ({g["marca"]} if g["marca"] else set())
        citados.append({"codigo": f"X{i:02d}", "nomes": g["nomes"], "termos": termos,
                        "rotulo": rotulo_do_nome(max(g["nomes"], key=len))})
    por_termo: dict[str, list] = {}
    for c in citados:
        for t in c["termos"]:
            por_termo.setdefault(t, []).append(c["codigo"])

    def codificar(texto: str) -> str:
        t = str(texto or "")
        for termo in sorted(por_termo, key=len, reverse=True):
            t = _regex_do_termo(termo).sub(lambda m, cod="/".join(por_termo[termo]): m.group(1) + cod, t)
        return t

    return {"pergunta": codificar(pergunta),
            "historico": [{**h, "texto": codificar((h or {}).get("texto"))} for h in historico or []],
            "citados": [{k: c[k] for k in ("codigo", "nomes", "rotulo")} for c in citados]}


class Codificador:
    """Código para os clientes e fornecedores que aparecem nos DADOS: o citado
    mantém o código que já tem; os outros ganham os seguintes."""
    def __init__(self, citados: list):
        self.lista = list(citados)
        self._por_chave = {chave_do_nome(n): c["codigo"] for c in citados for n in c["nomes"]}

    def codigo(self, nome) -> str | None:
        k = chave_do_nome(nome)
        if not k:
            return None
        if k not in self._por_chave:
            cod = f"X{len(self.lista) + 1:02d}"
            self._por_chave[k] = cod
            self.lista.append({"codigo": cod, "nomes": [nome], "rotulo": rotulo_do_nome(nome)})
        return self._por_chave[k]


def destrocar(texto: str, citados: list) -> str:
    mapa = {c["codigo"]: c["rotulo"] for c in citados}
    return re.sub(r"\bX\d{2,3}\b", lambda m: mapa.get(m.group(0), m.group(0)), str(texto or ""))


# ---- Os dados ----------------------------------------------------------------

_cache: dict = {}


def _analises(emp_id: int, comps: tuple) -> tuple:
    """(clientes, fornecedores) do razão, com cache curto: o razão só muda na importação."""
    chave = (emp_id, comps)
    agora = time.time()
    if chave in _cache and agora - _cache[chave][0] < CACHE_SEG:
        return _cache[chave][1]
    cli = analisar_receita_clientes(emp_id, list(comps)).get("clientes", [])
    forn = analisar_despesas_fornecedores(emp_id, list(comps)).get("por_fornecedor", [])
    _cache[chave] = (agora, (cli, forn))
    return cli, forn


def _r2(v) -> float:
    return round(float(v or 0), 2)


def _empresas_visiveis(perm) -> list:
    return [k for k in EMPRESAS if perm is None or k in perm]


def montar_contexto(pergunta: str, historico: list, perm, competencias: list, hoje: str) -> tuple:
    """(pergunta codificada, histórico codificado, JSON dos dados, codificador)."""
    emps = _empresas_visiveis(perm)
    if not emps:
        raise ErroConversa("Seu acesso não tem nenhuma empresa liberada no FinHub.")
    comps = tuple(sorted(competencias)[-MESES_DRE:])
    analises = {k: _analises(EMPRESAS[k]["id"], comps) for k in emps}
    nomes = [x["nome"] for k in emps for lst in analises[k] for x in lst if x.get("nome")]
    cod = pseudonimizar(pergunta, historico, nomes)
    codf = Codificador(cod["citados"])

    dre = {}
    chaves_dre = emps + (["consolidado"] if len(emps) == len(EMPRESAS) else [])
    for k in chaves_dre:
        dre[k] = [{"mes": m, **{LINHAS[l]: _r2(v.get(l)) for l in LINHAS}}
                  for m, v in calcular_dre_mensal(k, list(comps)).items()]

    def serie(item, sinal=1):
        return {m: _r2(sinal * v) for m, v in sorted((item.get("totais") or {}).items()) if v}

    clientes, fornecedores, citados = {}, {}, []
    cods_citados = {c["codigo"] for c in cod["citados"]}
    for k in emps:
        cli, forn = analises[k]
        clientes[k] = [{"cliente": codf.codigo(c["nome"]), "total": _r2(c.get("total_geral")), "por_mes": serie(c)}
                       for c in sorted(cli, key=lambda c: -abs(c.get("total_geral") or 0))[:TOP]]
        fornecedores[k] = [{"fornecedor": codf.codigo(f["nome"]), "total": _r2(f.get("total_geral")),
                            "por_mes": serie(f)}
                           for f in sorted(forn, key=lambda f: -abs(f.get("total_geral") or 0))[:TOP]]
        for c in cli:
            if codf.codigo(c["nome"]) in cods_citados:
                citados.append({"codigo": codf.codigo(c["nome"]), "empresa": k, "papel": "cliente",
                                "receita_faturada_por_mes": serie(c), "total": _r2(c.get("total_geral"))})
        for f in forn:
            if codf.codigo(f["nome"]) in cods_citados:
                citados.append({"codigo": codf.codigo(f["nome"]), "empresa": k, "papel": "fornecedor",
                                "despesa_lancada_por_mes": serie(f), "total": _r2(f.get("total_geral"))})
    dados = {"hoje": hoje, "empresas_visiveis": emps, "meses": list(comps), "dre_mensal": dre,
             "clientes": clientes, "fornecedores": fornecedores, "citados": citados}
    return cod["pergunta"], cod["historico"], json.dumps(dados, ensure_ascii=False), codf


def modelo(provedor: str) -> str | None:
    """Na OpenAI, gpt-4.1-mini (ou OPENAI_MODEL); na NVIDIA, o que a configuração escolheu."""
    if provedor == "openai":
        return os.getenv("OPENAI_MODEL", "").strip() or MODELO_OPENAI
    return None


def conversar(pergunta: str, historico: list, perm, competencias: list, hoje: str) -> str:
    perg, hist, contexto, codf = montar_contexto(pergunta, historico or [], perm, competencias, hoje)
    mensagens = [{"role": "system", "content": INSTRUCOES}, {"role": "system", "content": "DADOS:\n" + contexto}]
    for item in hist[-MAX_HISTORICO:]:
        texto = str(item.get("texto") or "")[:MAX_TEXTO_HISTORICO]
        if texto:
            mensagens.append({"role": "assistant" if item.get("papel") == "assistente" else "user",
                              "content": texto})
    mensagens.append({"role": "user", "content": perg})
    prov = ia_config.ler_config()["ativo"]
    texto = ia_config.chamar(mensagens, prov, max_tokens=900, temperature=0, timeout=45, modelo=modelo(prov))
    return destrocar(texto.strip(), codf.lista)
