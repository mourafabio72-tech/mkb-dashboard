# config.py — MKB-Dashboard
# Caminhos e constantes do projeto.
# Edite apenas os caminhos BASE_MKB e BASE_GNILEB se os arquivos mudarem de local.
# Em produção (Render / nuvem), configure as variáveis de ambiente listadas abaixo.

import os
from pathlib import Path

# ─── RAIZ DOS ARQUIVOS FONTE ──────────────────────────────────────────────────
BASE_CONTAB = Path(r"C:\Users\FabioMoura\BPS4 OUTSOURCING\Intranet BPS4 - Op. CONTABILIDADE")
BASE_MKB    = BASE_CONTAB / "04 - Grupo Markbuilding" / "00 - MKB" / "Apresentação Mensal" / "BPS4"
BASE_GNILEB = BASE_CONTAB / "04 - Grupo Markbuilding" / "02 -  Mark Participações - Gnileb" / "Apresentação GNILEB"

# ─── BANCO DE DADOS ──────────────────────────────────────────────────────────
# Em produção defina DB_PATH=/data/mkb_dre.db (disco persistente do Render).
# Localmente usa o arquivo mkb_dre.db na pasta do projeto.
_db_env = os.environ.get("DB_PATH")
DB_PATH = Path(_db_env) if _db_env else Path(__file__).parent / "mkb_dre.db"

# ─── EMPRESAS ─────────────────────────────────────────────────────────────────
EMPRESAS = {
    "mkb": {
        "id": 1,
        "nome": "Mark Building Gerenciamento Predial Ltda",
        "cnpj": "35.935.907/0001-27",
        "sigla": "MKB",
    },
    "gnileb": {
        "id": 2,
        "nome": "MKB Participações Ltda (Gnileb)",
        "cnpj": "",   # preencher se necessário
        "sigla": "GNILEB",
    },
}

# ─── PADRÃO DOS ARQUIVOS POR MÊS ─────────────────────────────────────────────
# {ano}/{mm:02d}/1 - MKB - DRE {mm:02d}{ano}.xlsx
def caminho_mkb(ano: int, mes: int) -> Path:
    return BASE_MKB / str(ano) / f"{mes:02d}" / f"1 - MKB - DRE {mes:02d}{ano}.xlsx"

# {ano}/{mm:02d}/MKB Participações - DRE {mm:02d}.{ano}.xlsx
def caminho_gnileb(ano: int, mes: int) -> Path:
    return BASE_GNILEB / str(ano) / f"{mes:02d}" / f"MKB Participações - DRE {mes:02d}.{ano}.xlsx"

# ─── CONFIGURAÇÃO DA ABA TEMPLATE DRE PROTHEUS ───────────────────────────────
SHEET_TEMPLATE = "Template DRE Protheus"

# Linha do cabeçalho (1-based) por empresa
HEADER_ROW = {
    "mkb":    5,
    "gnileb": 4,
}

# Colunas 2026 (1-based): coluna 1 = Cod Conta, coluna 2 = Descrição,
# colunas 3..14 = PERIODO 1..12, coluna 15 = TOTAL
COL_COD_CONTA   = 1
COL_DESCRICAO   = 2
COL_PERIODO_INI = 3   # PERIODO 1 = coluna 3
COL_PERIODO_FIM = 14  # PERIODO 12 = coluna 14

# Linha de totais (ignorar ao importar)
SKIP_DESCRICOES = {"TOTAL", ""}

# ─── FLASK ────────────────────────────────────────────────────────────────────
# Em produção defina SECRET_KEY como variável de ambiente (string aleatória longa).
SECRET_KEY = os.environ.get("SECRET_KEY", "mkb-dashboard-2026-local-only")
PORT       = int(os.environ.get("PORT", 5001))
DEBUG      = os.environ.get("DEBUG", "false").lower() == "true"

# ─── AUTENTICAÇÃO ─────────────────────────────────────────────────────────────
# DASHBOARD_USERS = "usuario1:senha1,usuario2:senha2"
# Em produção defina como variável de ambiente no Render (nunca comite senhas).
# Localmente o valor abaixo serve de fallback para desenvolvimento.
DASHBOARD_USERS_RAW = os.environ.get(
    "DASHBOARD_USERS",
    "admin:admin123"          # ← troque antes de fazer deploy em produção!
)
