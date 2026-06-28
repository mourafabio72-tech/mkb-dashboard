"""
importar_mes.py -- MKB-Dashboard
Importação automática de um mês completo: localiza os arquivos do Protheus
direto nas pastas conhecidas (sem upload manual) e importa tudo de uma vez.

Cobre (auto-localizados por padrão de pasta/nome, verificado em 2026):
  - DRE (MKB + Gnileb)        -- ingestion.importar() [já existia]
  - Razão CT1 (MKB + Gnileb)  -- razao_parser.importar_razao()
  - IRPJ/CSLL ANUAL (MKB)     -- irpj_csll_parser.importar_irpj_csll()

Ficam de fora (continuam manuais em app.py /ingest -- ver justificativa):
  - Plano de Contas  -- export ad-hoc do Protheus (CSV "Conta;Descricao"),
                        sem arquivo "do mês" -- não tem o que localizar.
  - Endividamento     -- a pasta mensal tem um .xlsx de nome parecido
                        ("Análise dívida tributária - MM.AAAA.xlsx"), mas é
                        um relatório histórico de % dívida/receita desde 2018,
                        ESTRUTURALMENTE DIFERENTE da planilha de vinculação
                        parcelamento×conta que o parser espera (confirmado
                        lendo o conteúdo real do arquivo). O .csv correto só
                        existe quando alguém o gera manualmente -- sem padrão
                        de pasta confiável para localizar automaticamente.
  - IRPJ/CSLL Gnileb  -- apuração trimestral, nome irregular
                        ("MARK PART IRPJ CSLL 1º TRIMESTRE 2026.xlsx").

Uso direto:
    python importar_mes.py --ano 2026 --mes 4
"""

import argparse
from datetime import datetime

from config import caminho_razao_mkb, caminho_razao_gnileb, caminho_irpj_csll_mkb
from ingestion import get_conn, criar_schema, seed_empresas, importar
from razao_parser import importar_razao
from irpj_csll_parser import importar_irpj_csll

_RESOLVER_RAZAO = {"mkb": caminho_razao_mkb, "gnileb": caminho_razao_gnileb}


def importar_mes_completo(ano: int, mes: int, empresas: list | None = None) -> dict:
    """
    Importa tudo o que é localizável automaticamente para o mês/ano indicado.
    Retorna {"importados": [...], "nao_encontrados": [...], "erros": [...]}
    -- itens em "nao_encontrados" precisam de upload manual (ver /ingest).
    """
    if empresas is None:
        empresas = ["mkb", "gnileb"]

    conn = get_conn()
    criar_schema(conn)
    seed_empresas(conn)

    relatorio = {"ano": ano, "mes": mes, "importados": [], "nao_encontrados": [], "erros": []}

    # ── DRE (já automatizado) ───────────────────────────────────────────────
    res_dre = importar(ano, mes, empresas=empresas)
    for chave in empresas:
        if res_dre.get(chave):
            relatorio["importados"].append(f"DRE {chave.upper()}: {res_dre[chave]} lançamentos")
    relatorio["erros"] += res_dre.get("erros", [])

    # ── Razão CT1 ────────────────────────────────────────────────────────────
    for chave in empresas:
        resolver = _RESOLVER_RAZAO.get(chave)
        if not resolver:
            continue
        caminho = resolver(ano, mes)
        if not caminho:
            relatorio["nao_encontrados"].append(f"Razão {chave.upper()} {mes:02d}/{ano}")
            continue
        try:
            res = importar_razao(caminho, chave, conn)
            if "erro" in res:
                relatorio["erros"].append(f"Razão {chave.upper()}: {res['erro']}")
            else:
                relatorio["importados"].append(
                    f"Razão {chave.upper()}: {res.get('registros', 0)} lançamentos ({caminho.name})"
                )
        except Exception as e:
            relatorio["erros"].append(f"Razão {chave.upper()}: {e}")

    # ── IRPJ/CSLL ANUAL (MKB apenas) ────────────────────────────────────────
    if "mkb" in empresas:
        caminho = caminho_irpj_csll_mkb(ano, mes)
        if not caminho:
            relatorio["nao_encontrados"].append(f"IRPJ/CSLL MKB {mes:02d}/{ano}")
        else:
            try:
                res = importar_irpj_csll(caminho, "mkb", conn)
                if "erro" in res:
                    relatorio["erros"].append(f"IRPJ/CSLL MKB: {res['erro']}")
                else:
                    relatorio["importados"].append(
                        f"IRPJ/CSLL MKB: {res.get('registros', 0)} linhas ({caminho.name})"
                    )
            except Exception as e:
                relatorio["erros"].append(f"IRPJ/CSLL MKB: {e}")

    conn.close()
    return relatorio


def main():
    parser = argparse.ArgumentParser(description="Importa o mês completo (auto-localizado) do MKB-Dashboard")
    parser.add_argument("--ano", type=int, default=datetime.now().year)
    parser.add_argument("--mes", type=int, default=datetime.now().month)
    parser.add_argument("--empresas", nargs="+", default=["mkb", "gnileb"])
    args = parser.parse_args()

    print(f"\n{'='*60}\nImportando mês completo: {args.mes:02d}/{args.ano}\n{'='*60}")
    relatorio = importar_mes_completo(args.ano, args.mes, empresas=args.empresas)

    print("\n✔ Importados:")
    for msg in relatorio["importados"]:
        print(f"  - {msg}")
    if relatorio["nao_encontrados"]:
        print("\n⚠ Não encontrados (faça upload manual em /ingest):")
        for msg in relatorio["nao_encontrados"]:
            print(f"  - {msg}")
    if relatorio["erros"]:
        print("\n✖ Erros:")
        for msg in relatorio["erros"]:
            print(f"  - {msg}")


if __name__ == "__main__":
    main()
