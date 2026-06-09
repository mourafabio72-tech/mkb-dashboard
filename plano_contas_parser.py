"""
plano_contas_parser.py -- MKB-Dashboard
Importador do PLANO DE CONTAS oficial (export do Protheus em CSV "Conta;Descricao",
ex.: "plano de contas mkb.csv") -- fonte AUTORITATIVA da descrição de cada conta
contábil, usada como classificação PRIMÁRIA na análise de Despesas por Fornecedor
(`analisar_despesas_fornecedores`, em dre_engine.py): cada código de conta passa a
ser exibido com sua descrição oficial (ex. "SERV DE INFORMATICA"), em vez do
"balde" largo de grupo DRE (ex. "Serviço Contratado (Custo)").

Não cria tabela nova -- a tabela `contas` (cod, empresa_id, descricao, grupo_dre)
já existe no schema (alimentada parcialmente por importações anteriores de CT2) e
é exatamente o destino certo: este importador faz UPSERT em `contas.descricao`,
SOBRESCREVENDO qualquer descrição aproximada herdada de outras fontes -- o plano
de contas oficial é a referência de verdade.

Formato do arquivo (confirmado em "plano de contas mkb.csv"):
  - CSV ';'-delimitado, 2 colunas: "Conta;Descricao"
  - encoding latin-1 (mesmo padrão dos demais relatórios Protheus do projeto)
  - cobre TODO o plano (grupos 1-Ativo, 2-Passivo, 2.3-PL, 3-Receitas, 4-Custos
    e Despesas), com códigos de 1 a 6 segmentos (ex. "1", "4.4.1.06.01.004")
  - export PAGINADO: a linha de cabeçalho "Conta;Descricao" se REPETE ao longo
    do arquivo (uma vez a cada "página" do relatório original) -- é detectada e
    ignorada linha a linha (não é preciso saber de antemão quantas há)
  - 5 descrições do arquivo de origem trazem bytes de controle (mojibake de
    acentuação -- ex. "SELECA\\x84O" em vez de "SELEÇÃO"); são gravadas como
    vieram (a corrupção é do arquivo de origem, não do parser) -- cosmético,
    não afeta o agrupamento (a chave é o CÓDIGO da conta, que é numérico e
    sempre íntegro)
"""

import csv
import re
import sqlite3
from pathlib import Path

from config import EMPRESAS

# ─── PADRÕES ────────────────────────────────────────────────────────────────

# Código de conta: um ou mais segmentos numéricos separados por ponto
# (ex. "1", "4.1", "4.4.1.06.01.004"). Usado para validar e descartar
# eventuais linhas de rodapé/lixo do export que não sejam contas de fato.
_RE_COD_CONTA = re.compile(r"^\d+(\.\d+)*$")


# ─── PARSERS AUXILIARES ──────────────────────────────────────────────────────

def _limpa(s) -> str:
    """Remove espaços e non-breaking spaces (\\xa0) que o Protheus injeta no export."""
    if s is None:
        return ""
    return str(s).strip().strip("\xa0").strip()


# ─── PARSER PRINCIPAL ────────────────────────────────────────────────────────

def parse_plano_contas(caminho: Path) -> list:
    """
    Lê o CSV do plano de contas (export paginado "Conta;Descricao", com a
    linha de cabeçalho repetida ao longo do arquivo) e retorna a lista de
    contas válidas, prontas para `salvar_plano_contas()`:

        [{"conta_cod": "4.1.1.02.03.008", "descricao": "SERV DE INFORMATICA"}, ...]

    Linhas de cabeçalho repetido, em branco, ou cujo "código" não bate com o
    padrão N(.N)* são ignoradas (com contagem no log) -- não interrompem a
    leitura do restante do arquivo.
    """
    print(f"  Abrindo Plano de Contas (CSV): {caminho.name}")

    with open(caminho, encoding="latin-1") as f:
        linhas = f.read().splitlines()

    reader = csv.reader(linhas, delimiter=";")

    registros = []
    vistos = set()          # dedup -- a mesma conta pode repetir entre páginas
    n_cabecalho = 0
    n_invalida = 0
    n_vazia = 0
    n_duplicada = 0

    for linha in reader:
        if not linha or all(not _limpa(c) for c in linha):
            n_vazia += 1
            continue
        if len(linha) < 2:
            n_invalida += 1
            continue

        cod, desc = _limpa(linha[0]), _limpa(linha[1])

        # Linha de cabeçalho repetida ("Conta;Descricao", reimpressa a cada
        # "página" do relatório original) -- detecta pelo texto da 1ª coluna,
        # não pela posição (pode aparecer em qualquer lugar do arquivo).
        if cod.lower() == "conta" and desc.lower().startswith("descri"):
            n_cabecalho += 1
            continue

        if not _RE_COD_CONTA.match(cod):
            n_invalida += 1
            continue
        if not desc:
            n_vazia += 1
            continue

        if cod in vistos:
            n_duplicada += 1
            continue
        vistos.add(cod)

        registros.append({"conta_cod": cod, "descricao": desc})

    print(f"  {len(registros)} contas válidas | "
          f"{n_cabecalho} linhas de cabeçalho repetido | "
          f"{n_duplicada} duplicadas (entre páginas) | "
          f"{n_invalida} código inválido | {n_vazia} vazias")

    return registros


# ─── GRAVAÇÃO ────────────────────────────────────────────────────────────────

def salvar_plano_contas(conn: sqlite3.Connection, registros: list, empresa_id: int) -> int:
    """
    UPSERT na tabela EXISTENTE `contas` (cod, empresa_id, descricao, grupo_dre)
    -- grava/sobrescreve `descricao` com o valor oficial do plano de contas.
    `grupo_dre` não é tocado aqui (é classificado dinamicamente por
    `classificar_conta()`/`account_map.json`, em dre_engine.py).

    Retorna a quantidade de contas gravadas/atualizadas.
    """
    conn.executemany(
        """
        INSERT INTO contas (cod, empresa_id, descricao)
        VALUES (:conta_cod, :empresa_id, :descricao)
        ON CONFLICT (cod, empresa_id) DO UPDATE SET
            descricao = excluded.descricao
        """,
        [{**r, "empresa_id": empresa_id} for r in registros],
    )
    conn.commit()
    return len(registros)


# ─── FUNÇÃO DE IMPORTAÇÃO ────────────────────────────────────────────────────

def importar_plano_contas(caminho: Path, empresa_chave: str, conn: sqlite3.Connection) -> dict:
    """
    Importa o CSV do plano de contas para a empresa indicada (chave curta,
    ex. "mkb"/"gnileb" -- resolvida via `config.EMPRESAS`), sobrescrevendo
    `contas.descricao` com a fonte oficial.

    Retorna resumo: {registros, empresa: <sigla>} ou {"erro": <msg>}.
    """
    emp = EMPRESAS.get(empresa_chave)
    if not emp:
        return {"erro": f"Empresa \"{empresa_chave}\" não encontrada em config.EMPRESAS."}

    registros = parse_plano_contas(caminho)
    if not registros:
        return {"erro": "Nenhuma conta válida encontrada no arquivo do plano de contas."}

    qtd = salvar_plano_contas(conn, registros, emp["id"])

    return {
        "registros": qtd,
        "empresa":   emp["sigla"],
    }


# ─── CLI DE TESTE ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from ingestion import get_conn

    if len(sys.argv) < 3:
        print("Uso: python plano_contas_parser.py <caminho_do_csv> <empresa (ex. mkb)>")
        sys.exit(1)

    caminho = Path(sys.argv[1])
    empresa_chave = sys.argv[2]
    conn = get_conn()
    resultado = importar_plano_contas(caminho, empresa_chave, conn)
    conn.close()
    print("\nResultado:", resultado)
