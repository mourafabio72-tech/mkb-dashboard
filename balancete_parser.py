"""
balancete_parser.py — MKB-Dashboard

Lê o Balancete de Verificação do Protheus (aba "12-00 - Balancete de Verificac")
e persiste o saldo atual (acumulado) por conta, para validar a DRE detalhada
contra o balancete e localizar diferenças.

Layout (linha 1 = cabeçalho, dados a partir da linha 2):
  col1 Conta | col2 Descricao | col3 Saldo anterior | col4 Debito |
  col5 Credito | col6 Mov periodo | col7 Saldo atual (magnitude) | col8 D/C

Convenção de sinal (igual à DRE / v_lancamentos): crédito = +, débito = -.
  Saldo atual assinado = +magnitude se 'C', -magnitude se 'D'.
"""

import sqlite3
from pathlib import Path

import openpyxl

from config import EMPRESAS


def _num(v) -> float:
    """Converte célula numérica ou texto pt-BR para float (magnitude)."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    # remove sufixo de sinal se vier no próprio texto
    if s[-1] in ("C", "D"):
        s = s[:-1].strip()
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_signed_text(cell) -> float:
    """'136.579,05 C' -> +136579.05 ; '... D' -> negativo ; vazio -> 0.0"""
    if cell is None:
        return 0.0
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell).strip()
    if not s:
        return 0.0
    sign = 1
    if s.endswith("D"):
        sign = -1
    mag = _num(s)
    return sign * abs(mag)


def _saldo_assinado(mag_cell, sign_cell) -> float:
    """Saldo atual = magnitude (col7) com sinal D/C (col8). C/vazio = +, D = -."""
    mag = abs(_num(mag_cell))
    sign = (str(sign_cell).strip().upper() if sign_cell is not None else "")
    return -mag if sign == "D" else mag


def parse_balancete(caminho: Path, empresa_id: int) -> list[dict]:
    wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)

    # Aba do balancete (começa com "12-00 - Balancete...") ou a 1ª aba
    aba = next((s for s in wb.sheetnames if "balancete" in s.lower()), wb.sheetnames[0])
    ws = wb[aba]

    registros: list[dict] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # cabeçalho
        if not row or row[0] is None:
            continue
        conta = str(row[0]).strip()
        if not conta or not conta[0].isdigit():
            continue
        descricao   = str(row[1] or "").strip()
        mov_periodo = _parse_signed_text(row[5]) if len(row) > 5 else 0.0
        saldo_atual = _saldo_assinado(
            row[6] if len(row) > 6 else None,
            row[7] if len(row) > 7 else None,
        )
        registros.append({
            "empresa_id":  empresa_id,
            "conta_cod":   conta,
            "descricao":   descricao,
            "saldo_atual": round(saldo_atual, 2),
            "mov_periodo": round(mov_periodo, 2),
        })

    wb.close()
    return registros


def salvar_balancete(conn: sqlite3.Connection, registros: list[dict],
                     competencia: str) -> int:
    """Substitui o balancete da (empresa, competência) pelos novos registros."""
    if not registros:
        return 0
    emp_id = registros[0]["empresa_id"]
    conn.execute(
        "DELETE FROM balancete WHERE empresa_id=? AND competencia=?",
        (emp_id, competencia)
    )
    for r in registros:
        r["competencia"] = competencia
    conn.executemany(
        """
        INSERT INTO balancete
            (empresa_id, competencia, conta_cod, descricao, saldo_atual, mov_periodo)
        VALUES
            (:empresa_id, :competencia, :conta_cod, :descricao, :saldo_atual, :mov_periodo)
        """,
        registros,
    )
    conn.commit()
    return len(registros)


def importar_balancete(caminho: Path, empresa_chave: str, competencia: str,
                       conn: sqlite3.Connection) -> dict:
    emp = EMPRESAS.get(empresa_chave)
    if not emp:
        return {"erro": f"Empresa '{empresa_chave}' não encontrada"}
    registros = parse_balancete(caminho, emp["id"])
    qtd = salvar_balancete(conn, registros, competencia)
    return {"registros": qtd, "empresa": emp["sigla"], "competencia": competencia}
