# config.py — MKB-Dashboard
# Caminhos e constantes do projeto.
# Edite apenas os caminhos BASE_MKB e BASE_GNILEB se os arquivos mudarem de local.
# Em produção (Render / nuvem), configure as variáveis de ambiente listadas abaixo.

import os
from pathlib import Path

# ─── RAIZ DOS ARQUIVOS FONTE ──────────────────────────────────────────────────
BASE_CONTAB     = Path(r"C:\Users\FabioMoura\BPS4 OUTSOURCING\Intranet BPS4 - Op. CONTABILIDADE")
BASE_MKB_ROOT    = BASE_CONTAB / "04 - Grupo Markbuilding" / "00 - MKB"
BASE_GNILEB_ROOT = BASE_CONTAB / "04 - Grupo Markbuilding" / "02 -  Mark Participações - Gnileb"

BASE_MKB    = BASE_MKB_ROOT / "Apresentação Mensal" / "BPS4"
BASE_GNILEB = BASE_GNILEB_ROOT / "Apresentação GNILEB"

# Pasta "Fechamento" -- onde Razão (CT1) e Balancete do mês são salvos com
# nome padronizado (mais confiável que "Apresentação Mensal" para a Razão).
BASE_MKB_FECHAMENTO    = BASE_MKB_ROOT / "Fechamento"
BASE_GNILEB_FECHAMENTO = BASE_GNILEB_ROOT / "Fechamento"

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


# ─── LOCALIZAÇÃO AUTOMÁTICA — IMPORTAÇÃO "MÊS COMPLETO" ──────────────────────
# Resolve por padrão glob (não nome exato) porque o nome real varia um pouco
# entre meses (ex.: sufixo " - v2", prefixo numérico "6 - " presente em alguns
# meses e ausente em outros). Em caso de mais de um arquivo bater com o
# padrão, usa o modificado mais recentemente (normalmente a versão corrigida).
def _resolver_arquivo(pasta: Path, padrao: str) -> Path | None:
    if not pasta.is_dir():
        return None
    candidatos = sorted(pasta.glob(padrao), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidatos[0] if candidatos else None


# Fechamento/{ano}/{mm}/MKB - RAZÃO {mm}.{ano}*.xlsx (aba "12-00 - Emissao do Razao Conta")
def caminho_razao_mkb(ano: int, mes: int) -> Path | None:
    pasta = BASE_MKB_FECHAMENTO / str(ano) / f"{mes:02d}"
    return _resolver_arquivo(pasta, f"MKB - RAZÃO {mes:02d}.{ano}*.xlsx")


# Fechamento/{ano}/{mm}/MKB PART - RAZÃO {mm}.{ano}*.xlsx
def caminho_razao_gnileb(ano: int, mes: int) -> Path | None:
    pasta = BASE_GNILEB_FECHAMENTO / str(ano) / f"{mes:02d}"
    return _resolver_arquivo(pasta, f"MKB PART - RAZÃO {mes:02d}.{ano}*.xlsx")


# Apresentação Mensal/BPS4/{ano}/{mm}/MKB GERENC IRPJ CSLL LUCRO REAL {mm}_{ano}*.xlsx (aba "ANUAL")
# Só MKB -- a versão Gnileb é trimestral, com nome irregular ("...1º TRIMESTRE..."),
# por isso fica de fora da localização automática (continua manual em /ingest).
def caminho_irpj_csll_mkb(ano: int, mes: int) -> Path | None:
    pasta = BASE_MKB / str(ano) / f"{mes:02d}"
    return _resolver_arquivo(pasta, f"MKB GERENC IRPJ CSLL LUCRO REAL {mes:02d}_{ano}*.xlsx")

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
import secrets as _secrets
SECRET_KEY = os.environ.get("SECRET_KEY") or _secrets.token_hex(32)
PORT       = int(os.environ.get("PORT", 5001))
DEBUG      = os.environ.get("DEBUG", "false").lower() == "true"

# ─── SSO ZOARIA HUB (opt-in via env) ─────────────────────────────────────────
# Quando ZOARIA_SECRET_KEY é definida (a MESMA do hub em zoaria.com.br), a
# sessão criada no hub passa a valer aqui via cookie compartilhado no domínio
# .zoaria.com.br. Sem essas env vars, o login local continua como sempre.
ZOARIA_SECRET_KEY = os.environ.get("ZOARIA_SECRET_KEY", "").strip()
if ZOARIA_SECRET_KEY:
    SECRET_KEY = ZOARIA_SECRET_KEY
ZOARIA_COOKIE_DOMAIN = os.environ.get("ZOARIA_COOKIE_DOMAIN", "").strip() or None
ZOARIA_COOKIE_NAME   = os.environ.get("ZOARIA_COOKIE_NAME", "zoaria_session")
HUB_URL    = os.environ.get("HUB_URL", "").strip().rstrip("/")
MODULO_HUB = "controladoria"   # módulo deste app no catálogo do hub

# ─── OPENAI (sugestão automática de aliases de fornecedores) ─────────────────
# Lê de env var OU de /data/openai_key.txt (fallback para Easypanel onde
# variáveis de ambiente nem sempre chegam ao container)
def _ler_openai_key() -> str:
    chave = os.environ.get("OPENAI_API_KEY", "").strip()
    if chave:
        return chave
    try:
        p = Path("/data/openai_key.txt")
        if p.exists():
            return p.read_text().strip()
    except Exception:
        pass
    return ""

OPENAI_API_KEY = _ler_openai_key()

# ─── AUTENTICAÇÃO ─────────────────────────────────────────────────────────────
# DASHBOARD_USERS = "usuario1:senha1,usuario2:senha2"
# Em produção defina como variável de ambiente no Render (nunca comite senhas).
# Localmente o valor abaixo serve de fallback para desenvolvimento.
DASHBOARD_USERS_RAW = os.environ.get(
    "DASHBOARD_USERS",
    "admin:admin123"          # ← troque antes de fazer deploy em produção!
)
