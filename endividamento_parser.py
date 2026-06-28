"""
endividamento_parser.py -- MKB-Dashboard
Importador da planilha "Análise dívida tributária" (CSV) -- vinculação entre
cada parcelamento fiscal (PERT, Transação, ISS, COFINS, ...) e suas contas
contábeis de curto prazo (CP) e longo prazo (LP), com metadados do acordo
(quantidade de parcelas, datas, desembolso mensal, valor principal, saldo
fiscal). Upload manual, snapshot de 1 competência por upload.

O saldo devedor real (CP+LP) NÃO é armazenado aqui -- é calculado em tempo
real a partir de `razao.saldo_atual` (mais confiável que o snapshot estático
desta planilha, que só reflete a competência do upload). Ver app.py rota
/endividamento.

Formato do arquivo (confirmado em "Análise dívida tributária - MM.AAAA.csv"):
  - CSV ';'-delimitado
  - Linha "Competência: MM/AAAA" no topo -- define a competência de referência
  - Linha de cabeçalho: Tributo;N do Processo;CONTA CP;CONTA LP;Qtd Parcelas;
    Parcela Paga;Faltam;Dt início;Dt término;Saldo contabilidade;
    Desembolso mensal;VALOR PRINCIPAL;Observação;SALDO FISCAL;DIFERENÇA;...
  - 1 linha por parcelamento, até a linha "TOTAL DO ENDIVIDAMENTO" (usada só
    para validar a soma -- não é persistida)
  - Tabela de reconciliação no final do arquivo (saldo CP/LP por conta) é
    IGNORADA -- dado redundante, já temos o saldo real via razao.saldo_atual
"""

import csv
import re
import sqlite3
from pathlib import Path

from config import EMPRESAS

_RE_COMPETENCIA = re.compile(r"compet[êe]ncia\s*:?\s*(\d{1,2})\s*/\s*(\d{2,4})", re.IGNORECASE)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _limpa(s) -> str:
    if s is None:
        return ""
    return str(s).strip().strip("\xa0").strip()


def _to_float(s) -> float | None:
    s = _limpa(s)
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(".", "").replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


def _to_int(s) -> int | None:
    s = _limpa(s)
    if not s:
        return None
    try:
        return int(float(s.replace(",", ".")))
    except ValueError:
        return None


def _ler_linhas(caminho: Path) -> list:
    """Lê o CSV tentando utf-8 primeiro, com fallback latin-1 (exports
    Protheus às vezes vêm em latin-1, como os demais CSVs CT2 do projeto)."""
    for encoding in ("utf-8", "latin-1"):
        try:
            with open(caminho, encoding=encoding) as f:
                texto = f.read()
        except UnicodeDecodeError:
            continue
        return list(csv.reader(texto.splitlines(), delimiter=";"))
    raise ValueError(f"Não foi possível ler o arquivo com utf-8 nem latin-1: {caminho}")


# ─── PARSER PRINCIPAL ────────────────────────────────────────────────────────

def parse_vinculacao(caminho: Path) -> dict:
    """
    Lê a planilha de vinculação e retorna:
        {"competencia_ref": "2026-04", "registros": [...], "total_declarado": {...}}

    Cada registro tem as chaves prontas para `salvar_vinculacao()`. Não inclui
    "saldo contabilidade" do snapshot (usado só para validar o total, não é
    persistido -- o saldo real vem do razão em tempo real).
    """
    print(f"  Abrindo Endividamento (vinculação): {caminho.name}")
    linhas = _ler_linhas(caminho)

    # 1. Competência de referência ("Competência: 04/2026")
    competencia_ref = None
    for linha in linhas[:10]:
        m = _RE_COMPETENCIA.search(";".join(linha))
        if m:
            mes, ano = int(m.group(1)), m.group(2)
            ano = int(ano) if len(ano) == 4 else 2000 + int(ano)
            competencia_ref = f"{ano}-{mes:02d}"
            break

    if not competencia_ref:
        print("  AVISO: linha 'Competencia: MM/AAAA' nao encontrada -- abortando.")
        return {"competencia_ref": None, "registros": [], "total_declarado": {}}

    # 2. Linha de cabeçalho ("Tributo;N do Processo;CONTA CP;...")
    header_idx = next(
        (i for i, linha in enumerate(linhas) if linha and _limpa(linha[0]).lower() == "tributo"),
        None,
    )
    if header_idx is None:
        print("  AVISO: linha de cabecalho ('Tributo;...') nao encontrada -- abortando.")
        return {"competencia_ref": competencia_ref, "registros": [], "total_declarado": {}}

    # 3. Linhas de dados (até "TOTAL DO ENDIVIDAMENTO" -- usada só p/ validar)
    registros = []
    saldo_contab_snapshot_soma = 0.0
    total_declarado = {}

    for linha in linhas[header_idx + 1:]:
        if not linha or not _limpa(linha[0]):
            continue

        col = lambda i: linha[i] if len(linha) > i else None  # noqa: E731
        tributo = _limpa(col(0))

        if tributo.upper().startswith("TOTAL"):
            total_declarado = {
                "saldo_contabilidade": _to_float(col(9)),
                "desembolso_mensal":   _to_float(col(10)),
                "valor_principal":     _to_float(col(11)),
            }
            break  # ignora tudo após o total (tabela de reconciliação no fim)

        saldo_contab_snapshot = _to_float(col(9))
        saldo_contab_snapshot_soma += saldo_contab_snapshot or 0.0

        registros.append({
            "tributo":           tributo,
            "processo":          _limpa(col(1)) or None,
            "conta_cp":          _limpa(col(2)),
            "conta_lp":          _limpa(col(3)) or None,
            "qtd_parcelas":      _to_int(col(4)),
            "parcela_paga":      _to_int(col(5)),
            "faltam":            _to_int(col(6)),
            "dt_inicio":         _limpa(col(7)) or None,
            "dt_termino":        _limpa(col(8)) or None,
            # peso de rateio p/ contas compartilhadas entre parcelamentos --
            # ver app.py rota /endividamento
            "saldo_contabilidade_snapshot": saldo_contab_snapshot,
            "desembolso_mensal": _to_float(col(10)),
            "valor_principal":   _to_float(col(11)),
            "observacao":        _limpa(col(12)) or None,
            "saldo_fiscal":      _to_float(col(13)),
        })

    # Validação (não bloqueia a importação, só avisa no log)
    declarado = total_declarado.get("saldo_contabilidade")
    if declarado is not None and abs(saldo_contab_snapshot_soma - declarado) > 0.05:
        print(
            f"  AVISO: soma de 'Saldo contabilidade' das linhas ({saldo_contab_snapshot_soma:,.2f}) "
            f"difere do total declarado na planilha ({declarado:,.2f})."
        )

    print(f"  {len(registros)} parcelamentos | competência de referência: {competencia_ref}")
    return {
        "competencia_ref": competencia_ref,
        "registros": registros,
        "total_declarado": total_declarado,
    }


# ─── PERSISTÊNCIA ─────────────────────────────────────────────────────────────

def salvar_vinculacao(conn: sqlite3.Connection, competencia_ref: str, registros: list,
                       empresa_id: int, arquivo: Path) -> int:
    """
    Substitui (delete + insert) os parcelamentos da competência de referência,
    para esta empresa -- evita lixo de parcelamento encerrado/renomeado entre
    uploads do mesmo período.
    """
    if not registros:
        return 0

    conn.execute(
        "DELETE FROM parcelamentos WHERE empresa_id=? AND competencia_ref=?",
        (empresa_id, competencia_ref),
    )

    conn.executemany(
        """
        INSERT INTO parcelamentos
            (empresa_id, competencia_ref, tributo, processo, conta_cp, conta_lp,
             qtd_parcelas, parcela_paga, faltam, dt_inicio, dt_termino,
             desembolso_mensal, valor_principal, observacao, saldo_fiscal,
             saldo_contabilidade_snapshot)
        VALUES
            (:empresa_id, :competencia_ref, :tributo, :processo, :conta_cp, :conta_lp,
             :qtd_parcelas, :parcela_paga, :faltam, :dt_inicio, :dt_termino,
             :desembolso_mensal, :valor_principal, :observacao, :saldo_fiscal,
             :saldo_contabilidade_snapshot)
        """,
        [{**r, "empresa_id": empresa_id, "competencia_ref": competencia_ref} for r in registros],
    )

    conn.execute(
        """
        INSERT INTO importacoes (empresa_id, competencia, arquivo, formato, registros)
        VALUES (?, ?, ?, 'ENDIVIDAMENTO', ?)
        """,
        (empresa_id, competencia_ref, str(arquivo), len(registros)),
    )

    conn.commit()
    return len(registros)


# ─── FUNÇÃO DE IMPORTAÇÃO ────────────────────────────────────────────────────

def importar_vinculacao(caminho: Path, empresa_chave: str, conn: sqlite3.Connection) -> dict:
    """
    Importa a planilha de vinculação para a empresa indicada.
    Retorna {registros, competencia_ref, empresa} ou {"erro": <msg>}.
    """
    emp = EMPRESAS.get(empresa_chave)
    if not emp:
        return {"erro": f"Empresa \"{empresa_chave}\" não encontrada em config.EMPRESAS."}

    resultado = parse_vinculacao(caminho)
    if not resultado["competencia_ref"]:
        return {"erro": "Não encontrei a linha \"Competência: MM/AAAA\" no arquivo."}
    if not resultado["registros"]:
        return {"erro": "Nenhum parcelamento válido encontrado (verifique o cabeçalho \"Tributo;...\")."}

    qtd = salvar_vinculacao(conn, resultado["competencia_ref"], resultado["registros"], emp["id"], caminho)

    return {
        "registros": qtd,
        "competencia_ref": resultado["competencia_ref"],
        "empresa": emp["sigla"],
    }


# ─── CLI DE TESTE ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from ingestion import get_conn, criar_schema, seed_empresas

    if len(sys.argv) < 3:
        print("Uso: python endividamento_parser.py <caminho_do_csv> <empresa (ex. mkb)>")
        sys.exit(1)

    caminho = Path(sys.argv[1])
    empresa_chave = sys.argv[2]
    conn = get_conn()
    criar_schema(conn)
    seed_empresas(conn)
    resultado = importar_vinculacao(caminho, empresa_chave, conn)
    conn.close()
    print("\nResultado:", resultado)
