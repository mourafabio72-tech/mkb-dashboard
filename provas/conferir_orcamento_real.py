"""Comparador com dado real: realizado do Rel_OrcRel (CQ2_TPSALD 1) x realizado do FinHub (razão).

Não guarda nada: os razões entram num banco temporário que some no fim, e a saída só traz
contagens, mês, conta e centro (nunca histórico, cliente ou fornecedor).

Uso:
  uv run --python 3.12 --with-requirements requirements.txt python provas/conferir_orcamento_real.py \\
      --orcrel ~/Downloads/Rel_OrcRel_2026.xlsx --ano 2026 --empresa mkb --razao ~/Downloads/"MKB G. - RAZÃO 0"*.xlsx

Com --razao-gnileb, cruza também o realizado do motor (orcamento_engine) com a DRE gerencial do
FinHub (calcular_todas_empresas_gerencial), mês a mês, na MKB, na Gnileb e no consolidado.

Saída 0 = todas as células batem (tolerância de 1 centavo); 1 = há diferença, listada por mês e centro.
"""
import argparse
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
TMP = Path(tempfile.mkdtemp(prefix="conferir_orc_"))
os.environ["DB_PATH"] = str(TMP / "conferir.db")

from config import EMPRESAS  # noqa: E402
from ingestion import criar_schema, get_conn, seed_empresas  # noqa: E402
from razao_parser import importar_razao  # noqa: E402
import orcamento_parser as op  # noqa: E402

TOL = 0.01


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orcrel", required=True)
    ap.add_argument("--ano", type=int, required=True)
    ap.add_argument("--empresa", default="mkb", choices=sorted(EMPRESAS))
    ap.add_argument("--razao", nargs="+", required=True)
    ap.add_argument("--razao-gnileb", nargs="*", default=[])
    ap.add_argument("--fase7", action="store_true", help="grava o orçado e confere a abertura por dimensão e os lançamentos")
    a = ap.parse_args()

    conn = get_conn()
    criar_schema(conn)
    seed_empresas(conn)
    for caminho in a.razao:
        importar_razao(Path(caminho), a.empresa, conn)
    for caminho in a.razao_gnileb:
        importar_razao(Path(caminho), "gnileb", conn)
    conn.commit()
    eid = EMPRESAS[a.empresa]["id"]
    finhub = defaultdict(float)
    for comp, conta, centro, valor in conn.execute(
            """SELECT competencia, trim(conta_cod), replace(COALESCE(centro_custo, ''), '.', ''), SUM(valor)
               FROM razao WHERE empresa_id = ? AND (conta_cod LIKE '3%' OR conta_cod LIKE '4%')
               GROUP BY 1, 2, 3""", (eid,)):
        finhub[(comp, conta, centro)] += valor or 0.0
    meses_razao = {k[0] for k in finhub}
    conn.close()

    relatorio = op.ler_orcamento(a.orcrel, a.ano)["realizado"]
    alvo = {k: v for k, v in relatorio.items() if k[0] in meses_razao}
    chaves = {k for k in set(alvo) | set(finhub) if k[0] in meses_razao}
    bate, difere = 0, []
    for k in sorted(chaves):
        r, f = alvo.get(k, 0.0), finhub.get(k, 0.0)
        if abs(r - f) <= TOL:
            bate += 1
        else:
            difere.append((k, r, f))
    print(f"meses comparados: {', '.join(sorted(meses_razao))}")
    print(f"células: {len(chaves)} | batem: {bate} | diferem: {len(difere)}")
    print(f"total realizado no relatório: {sum(alvo.values()):,.2f} | no FinHub: "
          f"{sum(v for k, v in finhub.items() if k[0] in meses_razao):,.2f}")
    por_mes = defaultdict(lambda: [0, 0.0])
    for (comp, _, _), r, f in difere:
        por_mes[comp][0] += 1
        por_mes[comp][1] += f - r
    for comp, (n, d) in sorted(por_mes.items()):
        print(f"  {comp}: {n} células, FinHub - relatório = {d:,.2f}")
    for (comp, conta, centro), r, f in sorted(difere, key=lambda x: -abs(x[2] - x[1]))[:15]:
        print(f"  {comp} {conta} centro {centro or '(vazio)'}: relatório {r:,.2f} | FinHub {f:,.2f}")
    falhou = bool(difere)
    if a.razao_gnileb:
        from dre_engine import calcular_todas_empresas_gerencial
        import orcamento_engine as oe
        linhas = ("ROB", "DED", "ROL", "CPV_TOTAL", "LB", "DADM_TOTAL", "ENC_FIN", "OUTROS_OP", "LAIR", "IRPJ_CSLL", "LL")
        conn = get_conn()
        n, dif = 0, 0
        for comp in sorted(meses_razao):
            dre = calcular_todas_empresas_gerencial(comp)
            for visao in ("mkb", "gnileb", "consolidado"):
                motor = {l["id"]: l["realizado"] for l in oe.calcular(conn, visao, int(comp[:4]), int(comp[5:]))["linhas"]}
                for lid in linhas:
                    n += 1
                    if abs(motor[lid] - dre[visao][lid]) > TOL:
                        dif += 1
                        print(f"  DRE x motor {comp} {visao} {lid}: DRE {dre[visao][lid]:,.2f} | motor {motor[lid]:,.2f}")
        conn.close()
        print(f"DRE gerencial x motor do orçamento: {n} células, {dif} diferenças")
        falhou = falhou or bool(dif)
    if a.fase7:
        falhou = conferir_fase7(a, sorted(meses_razao)) or falhou
    return 1 if falhou else 0


def conferir_fase7(a, meses):
    """Com o orçado gravado: as quatro aberturas somam a mesma MC; a soma das linhas = total; a chave de cada
    linha, como filtro, isola a linha; os lançamentos de cada conta somam o realizado dela na árvore."""
    import orcamento_engine as oe
    lido = op.ler_orcamento(a.orcrel, a.ano)
    eid = EMPRESAS[a.empresa]["id"]
    conn = get_conn()
    lote = conn.execute("INSERT INTO orcamento_lotes (empresa_id, ano, usuario, arquivo, linhas, total) VALUES (?, ?, 'conferir', 'real', ?, 0)",
                        (eid, a.ano, len(lido["orcado"]))).lastrowid
    conn.executemany("INSERT INTO orcamento (empresa_id, competencia, conta_cod, centro_custo, valor, lote_id) VALUES (?, ?, ?, ?, ?, ?)",
                     [(eid, c, conta, centro, round(v, 2), lote) for (c, conta, centro), v in lido["orcado"].items()])
    conn.executemany("INSERT INTO centros_custo (empresa_id, codigo, descricao, servico, coordenador, filial, tipo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     [(eid, k, c["descricao"], c["servico"], c["coordenador"], c["filial"], c["tipo"]) for k, c in lido["centros"].items()])
    conn.commit()
    ultimo = int(meses[-1][5:])
    periodos = [(m, m) for m in range(1, ultimo + 1)] + [(1, ultimo)]
    checagens, erros = 0, 0

    def confere(cond, msg):
        nonlocal checagens, erros
        checagens += 1
        if not cond:
            erros += 1
            print("  FASE 7:", msg)

    for de, ate in periodos:
        totais = {}
        for d in ("servico", "coordenador", "filial", "centro"):
            r = oe.por_dimensao(conn, a.empresa, a.ano, de, ate, d)
            totais[d] = r["total"]["mc"]
            soma = [round(sum(l["mc"][i] or 0 for l in r["linhas"]), 2) for i in (0, 1)]
            confere(all(abs(soma[i] - (r["total"]["mc"][i] or 0)) <= TOL * max(1, len(r["linhas"])) for i in (0, 1)),
                    f"{de}-{ate} {d}: soma das linhas {soma} x total {r['total']['mc']}")
            if d == "servico":
                for l in r["linhas"]:
                    so = oe.por_dimensao(conn, a.empresa, a.ano, de, ate, d, {d: [l["chave"]]})["total"]["mc"]
                    confere(all(abs((so[i] or 0) - (l["mc"][i] or 0)) <= TOL for i in (0, 1)), f"{de}-{ate} {d} {l['chave']}: filtro {so} x linha {l['mc']}")
        pn = oe.painel(conn, a.empresa, a.ano, de, ate)
        ind = pn["indicadores"]
        confere([ind["mc"]["orcado"], ind["mc"]["realizado"]] == totais["servico"], f"{de}-{ate}: dashboard MC {ind['mc']} x tabela {totais['servico']}")
        arv_p = oe.arvore(conn, a.empresa, a.ano, de, ate)["total"]
        confere(ind["resultado"]["realizado"] == arv_p["acumulado"][1] and pn["mensal"]["resultado"] == arv_p["meses"],
                f"{de}-{ate}: dashboard Resultado x árvore")
        base = totais["servico"]
        confere(all(all(abs((t[i] or 0) - (base[i] or 0)) <= 0.05 for i in (0, 1)) for t in totais.values()),
                f"{de}-{ate}: MC difere entre as aberturas {totais}")
    arv = oe.arvore(conn, a.empresa, a.ano, 1, ultimo)
    contas = sorted((l for l in arv["linhas"] if l["nivel"] == 3), key=lambda l: -abs(l["acumulado"][1] or 0))[:40]
    for l in contas:
        lc = oe.lancamentos(conn, a.empresa, a.ano, 1, ultimo, l["codigo"])
        confere(abs(lc["total"] - (l["acumulado"][1] or 0)) <= TOL, f"lançamentos {l['codigo']}: {lc['total']} x árvore {l['acumulado'][1]}")
    import time
    for nome, fn in (("abertura por centro, jan a " + meses[-1][5:], lambda: oe.por_dimensao(conn, a.empresa, a.ano, 1, ultimo, "centro")),
                     ("árvore, jan a " + meses[-1][5:], lambda: oe.arvore(conn, a.empresa, a.ano, 1, ultimo)),
                     ("lançamentos da maior conta", lambda: oe.lancamentos(conn, a.empresa, a.ano, 1, ultimo, contas[0]["codigo"]))):
        t0 = time.perf_counter()
        fn()
        print(f"  tempo: {nome}: {time.perf_counter() - t0:.2f} s")
    conn.close()
    print(f"Fase 7 com dado real: {checagens} checagens, {erros} diferenças ({len(periodos)} períodos, {len(contas)} contas nos lançamentos)")
    return bool(erros)


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
