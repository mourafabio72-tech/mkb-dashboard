"""
ct2_despesas_parser.py -- MKB-Dashboard
Parser do CT2-Lançamentos Contábeis em formato CSV detalhado por
fornecedor/NF (relatório Protheus de detalhe de DESPESAS/CUSTOS --
ex.: "MKB - CT2  (2).csv").

Irmão de `ct2_receita_parser.py` -- mesmo formato de arquivo (CSV ';',
latin-1, 2 linhas de cabeçalho de relatório), mas:
  - traz lançamentos de despesas/custos (contas 4.x), já segregados por
    fornecedor ("Cli_For/Lj") e histórico (NF embutida no texto)
  - o campo "Razão Social" vem praticamente vazio neste relatório
    (diferente do de receita) -- o nome do fornecedor precisa ser
    extraído do "Historico" ou completado via cadastro mestre
    (ver fornecedores_parser.py)
  - "Num.NF/Titulo" está preenchido em só ~38% das linhas e se repete
    entre splits de conta -- NÃO serve como chave de upsert sozinho
    (95% de colisão). Usamos uma chave SINTÉTICA determinística:
        documento = "{Lote}.{SubLote}.{Linha}"  [+ "#N" em colisões]
    numerado na ordem de leitura do arquivo -- estável entre
    reimportações enquanto a ordem de exportação do Protheus não mudar.
  - mesma convenção de sinal do arquivo de receita: "Valor DB ou CR"
    com crédito NEGATIVO -- inverter para bater com `valor = crédito -
    débito` (validado: para despesas, o resultado fica negativo, como
    esperado na convenção DRE).

Colunas esperadas (na 3ª linha do arquivo) -- mesmas do CT2-Receita:
  Emp_Filial; Emp_Fil_Origem; Data; Lote; Sub-Lote; Linha; Historico;
  Conta Resumo; Conta Mãe; Valor DB ou CR; C.Custo Resumo; Tipo C.Custo;
  Cli_For/Lj; Razão Social; Num.NF/Titulo; Num.Pedido
"""

import csv
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from config import EMPRESAS

# ─── PADRÕES ────────────────────────────────────────────────────────────────

_LINHAS_CABECALHO = 2          # título do relatório + linha em branco antes do header
_PREFIXO_DESPESA  = "4."       # custos e despesas (todas as contas 4.x)

# Mapa sigla (como aparece em "Emp_Filial") → empresa_id
_SIGLA_TO_ID = {emp["sigla"].upper(): emp["id"] for emp in EMPRESAS.values()}

_RE_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


# ─── PARSERS AUXILIARES (idênticos a ct2_receita_parser) ────────────────────

def _limpa(s) -> str:
    """Remove espaços e non-breaking spaces (\\xa0) que o Protheus injeta no export."""
    if s is None:
        return ""
    return str(s).strip().strip("\xa0").strip()


def _parse_data(data_str: str) -> tuple:
    """'DD/MM/AAAA' → ('AAAA-MM-DD', 'AAAA-MM'). Retorna (None, None) se inválido."""
    m = _RE_DATA.match(data_str.strip())
    if not m:
        return None, None
    dd, mm, aaaa = m.groups()
    return f"{aaaa}-{mm}-{dd}", f"{aaaa}-{mm}"


def _parse_valor(valor_str: str) -> float:
    """'-1.616,09' (formato BR) → -1616.09 (float)."""
    s = valor_str.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# ─── PARSER PRINCIPAL ────────────────────────────────────────────────────────

def parse_ct2_despesas(caminho: Path) -> list:
    """
    Lê o CSV de detalhe de despesas/custos (CT2 por fornecedor/NF) e
    retorna lista de dicts no MESMO formato que `razao_parser.parse_razao()`
    devolve, prontos para `salvar_razao()`.

    Linhas que não sejam de despesa/custo (conta fora do prefixo "4.") ou
    de empresa não identificável são ignoradas (com contagem no log).

    ⚠ Diferente do CT2-Receita (multi-empresa, "Emp_Filial" sempre
    preenchido com a sigla), ESTE relatório vem como exportação
    MONO-EMPRESA com a coluna "Emp_Filial" VAZIA em 100% das linhas
    (confirmado em "MKB - CT2 (2).csv" -- 35.169/35.169). Nesses casos,
    a sigla é inferida do NOME DO ARQUIVO (ex.: "MKB - CT2 (2).csv" → MKB).
    Se a coluna vier preenchida em uma exportação futura, ela tem prioridade.

    A exclusão dos grupos de folha/encargos/pró-labore (4.1.1.01.x e
    4.4.1.01.x) NÃO é feita aqui -- o lançamento bruto é gravado por
    completo em `razao` para reaproveitamento futuro (ex.: análises de
    DP); a exclusão acontece na camada de análise
    (`analisar_despesas_fornecedores`, em dre_engine.py).
    """
    print(f"  Abrindo CT2-Despesas (CSV): {caminho.name}")

    # Sigla padrão inferida do NOME DO ARQUIVO -- usada quando "Emp_Filial"
    # vem vazio (caso deste relatório, mono-empresa). Ex.: "MKB - CT2  (2).csv"
    # → contém "MKB" → empresa_id correspondente.
    _nome_arquivo = caminho.stem.upper()
    _sigla_padrao_id = next(
        (emp_id for sigla, emp_id in _SIGLA_TO_ID.items() if sigla in _nome_arquivo),
        None,
    )
    if _sigla_padrao_id:
        _sigla_padrao_nome = next(s for s, i in _SIGLA_TO_ID.items() if i == _sigla_padrao_id)
        print(f"  \"Emp_Filial\" vazio neste relatório -- usando \"{_sigla_padrao_nome}\" "
              f"(detectado no nome do arquivo) como empresa padrão")
    else:
        print(f"  ⚠ Não foi possível inferir a empresa pelo nome do arquivo "
              f"\"{caminho.name}\" -- linhas sem \"Emp_Filial\" preenchido serão ignoradas")

    with open(caminho, encoding="latin-1") as f:
        linhas = f.read().splitlines()

    reader = csv.reader(linhas[_LINHAS_CABECALHO:], delimiter=";")
    header = [_limpa(h) for h in next(reader)]

    registros = []
    n_fora_despesa = 0
    n_empresa_desconhecida = 0
    n_data_invalida = 0
    n_zerado = 0

    # Contador de colisões para a chave sintética documento = Lote.SubLote.Linha
    # (algumas combinações se repetem -- ex.: um mesmo lançamento dividido em
    # múltiplas linhas de rateio por conta/centro de custo)
    _contador_chave: dict[tuple, int] = defaultdict(int)

    for linha in reader:
        if len(linha) < len(header):
            continue
        row = dict(zip(header, [_limpa(c) for c in linha]))

        conta_cod = row.get("Conta Resumo", "")
        if not conta_cod.startswith(_PREFIXO_DESPESA):
            n_fora_despesa += 1
            continue

        # "Emp_Filial" vem vazio neste relatório (mono-empresa) -- usa a
        # sigla padrão inferida do nome do arquivo (calculada acima).
        # Se algum dia vier preenchido, ela tem prioridade sobre o padrão.
        sigla = row.get("Emp_Filial", "").upper()
        empresa_id = _SIGLA_TO_ID.get(sigla) or _sigla_padrao_id
        if not empresa_id:
            n_empresa_desconhecida += 1
            continue

        data_lanc, competencia = _parse_data(row.get("Data", ""))
        if not data_lanc:
            n_data_invalida += 1
            continue

        # Sinal: mesma convenção do CT2-Receita -- no export, crédito vem
        # NEGATIVO. Inverte para a convenção do sistema (valor = crédito -
        # débito); para despesas isso resulta em valor negativo, como esperado.
        bruto = _parse_valor(row.get("Valor DB ou CR", "0"))
        if bruto < 0:
            credito, debito = -bruto, 0.0
        else:
            credito, debito = 0.0, bruto
        valor = credito - debito

        if debito == 0 and credito == 0:
            n_zerado += 1
            continue

        # Chave sintética determinística: Lote.SubLote.Linha, com sufixo
        # "#N" apenas quando colide dentro de (empresa, data, conta) --
        # contagem na ordem de leitura do arquivo (estável entre reimportações
        # enquanto a exportação do Protheus mantiver a mesma ordem de linhas).
        lote, sublote, num_linha = row.get("Lote", ""), row.get("Sub-Lote", ""), row.get("Linha", "")
        base_doc = f"{lote}.{sublote}.{num_linha}".strip(".")
        chave_grupo = (empresa_id, data_lanc, base_doc, conta_cod)
        seq = _contador_chave[chave_grupo]
        _contador_chave[chave_grupo] += 1
        documento = base_doc if seq == 0 else f"{base_doc}#{seq}"

        historico = row.get("Historico") or None
        razao_social = row.get("Razão Social") or None
        fornecedor_cod = row.get("Cli_For/Lj") or None
        filial = row.get("Emp_Fil_Origem") or None

        registros.append({
            "empresa_id":    empresa_id,
            "competencia":   competencia,
            "data_lanc":     data_lanc,
            "conta_cod":     conta_cod,
            "documento":     documento,
            "historico":     historico[:200] if historico else None,
            "conta_partida": None,   # "Conta Mãe" aqui é descrição, não código de contrapartida
            "filial":        filial if filial not in ("", "00") else None,
            "centro_custo":  row.get("C.Custo Resumo") or None,
            "debito":        debito,
            "credito":       credito,
            "valor":         valor,
            # Código do fornecedor ("Cli_For/Lj") -- coluna nativa de `razao`
            # (parceiro_cod), usada por `analisar_despesas_fornecedores` para
            # consolidar fornecedores de forma estável (evita duplicidade por
            # truncamento do nome no histórico).
            "parceiro_cod":  fornecedor_cod,
            # Campo extra (não faz parte do schema de `razao`; vem vazio neste
            # relatório -- mantido apenas para inspeção/diagnóstico).
            "_razao_social": razao_social,
        })

    print(f"  {len(registros)} lançamentos de despesa/custo (4.x) | "
          f"{n_fora_despesa} fora do prefixo despesa | "
          f"{n_empresa_desconhecida} empresa desconhecida | "
          f"{n_data_invalida} data inválida | {n_zerado} zerados")

    return registros


# ─── FUNÇÃO DE IMPORTAÇÃO ────────────────────────────────────────────────────

def importar_ct2_despesas(caminho: Path, conn: sqlite3.Connection) -> dict:
    """
    Importa o CSV de detalhe de despesas/custos para a tabela `razao`,
    reaproveitando `salvar_razao()` do razao_parser.

    Retorna resumo: {registros, competencias, empresas: {sigla: qtd}}
    """
    from razao_parser import salvar_razao

    registros = parse_ct2_despesas(caminho)
    if not registros:
        return {"erro": "Nenhum lançamento de despesa/custo (4.x) válido encontrado no arquivo."}

    # Remove os campos extras antes de gravar (salvar_razao espera só as
    # colunas nativas de `razao`; os extras `_razao_social`/`_fornecedor_cod`
    # servem apenas para a análise por fornecedor).
    registros_db = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in registros
    ]

    qtd = salvar_razao(conn, registros_db, caminho)

    competencias = sorted({r["competencia"] for r in registros})
    id_to_sigla = {emp["id"]: emp["sigla"] for emp in EMPRESAS.values()}
    por_empresa = {}
    for r in registros:
        sigla = id_to_sigla.get(r["empresa_id"], str(r["empresa_id"]))
        por_empresa[sigla] = por_empresa.get(sigla, 0) + 1

    return {
        "registros":    qtd,
        "competencias": competencias,
        "empresas":     por_empresa,
    }


# ─── CLI DE TESTE ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from ingestion import get_conn

    if len(sys.argv) < 2:
        print("Uso: python ct2_despesas_parser.py <caminho_do_csv>")
        sys.exit(1)

    caminho = Path(sys.argv[1])
    conn = get_conn()
    resultado = importar_ct2_despesas(caminho, conn)
    conn.close()
    print("\nResultado:", resultado)
