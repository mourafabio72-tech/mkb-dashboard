"""
ct2_receita_parser.py -- MKB-Dashboard
Parser do CT2-Lançamentos Contábeis em formato CSV detalhado por cliente/NF
(relatório Protheus de detalhe de receita -- ex.: "modelo ct2 receita.csv").

Diferente do Razão CT1 (xlsx, ver razao_parser.py), este arquivo:
  - vem em CSV, separado por ';', encoding latin-1, com 2 linhas de cabeçalho
    de relatório antes da linha de colunas
  - traz lançamentos individuais de receita (3.1.1.x) já segregados por
    cliente (campo "Razão Social") e por nota fiscal ("Num.NF/Titulo")
  - mistura múltiplas empresas no mesmo arquivo (coluna "Emp_Filial": MKB / GNILEB)
  - usa convenção de sinal "Valor DB ou CR" onde crédito (receita) aparece
    NEGATIVO -- precisa inverter o sinal para bater com a convenção do
    sistema (valor = crédito - débito; receita = positivo)

Colunas esperadas (na 3ª linha do arquivo):
  Emp_Filial; Emp_Fil_Origem; Data; Lote; Sub-Lote; Linha; Historico;
  Conta Resumo; Conta Mãe; Valor DB ou CR; C.Custo Resumo; Tipo C.Custo;
  Cli_For/Lj; Razão Social; Num.NF/Titulo; Num.Pedido

Chave de upsert usada na tabela `razao` -- (empresa_id, data_lanc, documento,
conta_cod) -- é satisfeita usando `documento = Num.NF/Titulo`, que se mostrou
100% único dentro de (empresa, data, conta) nesta exportação (0 colisões em
1.519 linhas testadas).
"""

import csv
import re
import sqlite3
from pathlib import Path

from config import EMPRESAS

# ─── PADRÕES ────────────────────────────────────────────────────────────────

_LINHAS_CABECALHO = 2          # título do relatório + linha em branco antes do header
_PREFIXO_RECEITA  = "3.1.1"    # só importamos receita bruta deste arquivo

# Mapa sigla (como aparece em "Emp_Filial") → empresa_id
_SIGLA_TO_ID = {emp["sigla"].upper(): emp["id"] for emp in EMPRESAS.values()}

_RE_DATA = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


# ─── PARSERS AUXILIARES ─────────────────────────────────────────────────────

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

def parse_ct2_receita(caminho: Path) -> list:
    """
    Lê o CSV de detalhe de receita (CT2 por cliente/NF) e retorna lista de
    dicts no MESMO formato que `razao_parser.parse_razao()` devolve, prontos
    para `salvar_razao()`.

    Linhas que não sejam de receita bruta (conta fora do prefixo 3.1.1) ou
    de empresa não cadastrada em EMPRESAS são ignoradas (com contagem no log).
    """
    print(f"  Abrindo CT2-Receita (CSV): {caminho.name}")

    with open(caminho, encoding="latin-1") as f:
        linhas = f.read().splitlines()

    reader = csv.reader(linhas[_LINHAS_CABECALHO:], delimiter=";")
    header = [_limpa(h) for h in next(reader)]

    registros = []
    n_fora_receita = 0
    n_empresa_desconhecida = 0
    n_data_invalida = 0
    n_zerado = 0

    for linha in reader:
        if len(linha) < len(header):
            continue
        row = dict(zip(header, [_limpa(c) for c in linha]))

        conta_cod = row.get("Conta Resumo", "")
        if not conta_cod.startswith(_PREFIXO_RECEITA):
            n_fora_receita += 1
            continue

        sigla = row.get("Emp_Filial", "").upper()
        empresa_id = _SIGLA_TO_ID.get(sigla)
        if not empresa_id:
            n_empresa_desconhecida += 1
            continue

        data_lanc, competencia = _parse_data(row.get("Data", ""))
        if not data_lanc:
            n_data_invalida += 1
            continue

        # Sinal: no export, crédito (receita) vem NEGATIVO. Inverte para a
        # convenção do sistema: valor = crédito - débito (receita = positivo).
        bruto = _parse_valor(row.get("Valor DB ou CR", "0"))
        if bruto < 0:
            credito, debito = -bruto, 0.0
        else:
            credito, debito = 0.0, bruto
        valor = credito - debito

        if debito == 0 and credito == 0:
            n_zerado += 1
            continue

        documento = row.get("Num.NF/Titulo") or None
        historico = row.get("Historico") or None
        razao_social = row.get("Razão Social") or None
        cliente_cod = row.get("Cli_For/Lj") or None
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
            # Campos extras (não fazem parte do schema padrão de `razao`;
            # ficam disponíveis para quem quiser usá-los, ex.: enriquecimento futuro)
            "_razao_social": razao_social,
            "_cliente_cod":  cliente_cod,
        })

    print(f"  {len(registros)} lançamentos de receita (3.1.1.x) | "
          f"{n_fora_receita} fora do prefixo receita | "
          f"{n_empresa_desconhecida} empresa desconhecida | "
          f"{n_data_invalida} data inválida | {n_zerado} zerados")

    return registros


# ─── FUNÇÃO DE IMPORTAÇÃO ────────────────────────────────────────────────────

def importar_ct2_receita(caminho: Path, conn: sqlite3.Connection) -> dict:
    """
    Importa o CSV de detalhe de receita (multi-empresa) para a tabela `razao`,
    reaproveitando `salvar_razao()` do razao_parser.

    Retorna resumo: {registros, competencias, empresas: {sigla: qtd}}
    """
    from razao_parser import salvar_razao

    registros = parse_ct2_receita(caminho)
    if not registros:
        return {"erro": "Nenhum lançamento de receita (3.1.1.x) válido encontrado no arquivo."}

    # Remove os campos extras antes de gravar (salvar_razao espera só as
    # colunas nativas de `razao`; os extras `_razao_social`/`_cliente_cod`
    # servem apenas para inspeção/relatório nesta etapa).
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
        print("Uso: python ct2_receita_parser.py <caminho_do_csv>")
        sys.exit(1)

    caminho = Path(sys.argv[1])
    conn = get_conn()
    resultado = importar_ct2_receita(caminho, conn)
    conn.close()
    print("\nResultado:", resultado)
