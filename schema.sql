-- schema.sql — MKB-Dashboard
-- Executado uma vez para criar o banco SQLite.

CREATE TABLE IF NOT EXISTS empresas (
    id     INTEGER PRIMARY KEY,
    sigla  TEXT NOT NULL UNIQUE,
    nome   TEXT NOT NULL,
    cnpj   TEXT
);

CREATE TABLE IF NOT EXISTS contas (
    cod        TEXT NOT NULL,
    empresa_id INTEGER NOT NULL,
    descricao  TEXT,
    grupo_dre  TEXT,
    PRIMARY KEY (cod, empresa_id)
);

-- ─── CT2: Saldo mensal por conta (importação via Comparativo) ───────────────
CREATE TABLE IF NOT EXISTS lancamentos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id   INTEGER NOT NULL,
    competencia  TEXT NOT NULL,   -- 'YYYY-MM'
    conta_cod    TEXT NOT NULL,
    valor        REAL NOT NULL,   -- C → positivo, D → negativo
    UNIQUE (empresa_id, competencia, conta_cod)
);

CREATE INDEX IF NOT EXISTS idx_lanc_emp_comp ON lancamentos (empresa_id, competencia);
CREATE INDEX IF NOT EXISTS idx_lanc_conta    ON lancamentos (conta_cod);

-- ─── CT1: Lançamentos individuais do Razão Contábil ─────────────────────────
CREATE TABLE IF NOT EXISTS razao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id    INTEGER NOT NULL,
    competencia   TEXT NOT NULL,       -- 'YYYY-MM' (derivado de data_lanc)
    data_lanc     TEXT,                -- 'YYYY-MM-DD'
    conta_cod     TEXT NOT NULL,       -- '4.1.1.01.02.001'
    documento     TEXT,                -- número do lote/doc Protheus
    historico     TEXT,                -- descrição do lançamento (até 200 chars)
    conta_partida TEXT,                -- contra conta (partida dupla)
    filial        TEXT,                -- filial de origem
    centro_custo  TEXT,                -- centro de custo (se preenchido)
    debito        REAL DEFAULT 0,
    credito       REAL DEFAULT 0,
    valor         REAL,                -- credito - debito (sinal DRE)
    parceiro_cod  TEXT,                -- código Cli_For/Lj (CT2 detalhe: cliente em 3.x, fornecedor em 4.x)
    UNIQUE (empresa_id, data_lanc, documento, conta_cod)
);

CREATE INDEX IF NOT EXISTS idx_razao_emp_comp ON razao (empresa_id, competencia);
CREATE INDEX IF NOT EXISTS idx_razao_conta    ON razao (conta_cod);
CREATE INDEX IF NOT EXISTS idx_razao_data     ON razao (data_lanc);

-- ─── VIEW: agrega Razão → formato mensal (compatibilidade com dre_engine) ───
-- Quando CT1 (Razão) está disponível, esta view une as duas fontes.
-- O dre_engine consulta esta view; se razao estiver vazia, usa lancamentos.
CREATE VIEW IF NOT EXISTS v_lancamentos AS
    -- Lançamentos do Razão (CT1) — agregados por mês
    SELECT empresa_id, competencia, conta_cod, SUM(valor) AS valor
    FROM razao
    GROUP BY empresa_id, competencia, conta_cod
    UNION ALL
    -- Lançamentos do Comparativo (CT2) — apenas contas não presentes no Razão
    SELECT l.empresa_id, l.competencia, l.conta_cod, l.valor
    FROM lancamentos l
    WHERE NOT EXISTS (
        SELECT 1 FROM razao r
        WHERE r.empresa_id  = l.empresa_id
          AND r.competencia = l.competencia
          AND r.conta_cod   = l.conta_cod
    );

-- ─── Cadastro mestre de fornecedores (código → razão social) ────────────────
-- Alimentado pelo relatório de cadastro do Protheus (ex.: "SA2 - Cadastro de
-- Fornecedores"). Enquanto vazio, a análise de Despesas por Fornecedor usa o
-- nome aproximado extraído do histórico do lançamento; quando populado, passa
-- a exibir a razão social oficial (ver fornecedores_parser.py).
CREATE TABLE IF NOT EXISTS fornecedores_cadastro (
    cliente_cod   TEXT PRIMARY KEY,   -- código "Cli_For/Lj" do Protheus
    razao_social  TEXT NOT NULL,
    nome_fantasia TEXT,
    cnpj_cpf      TEXT,
    importado_em  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ─── Log de importações ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS importacoes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id   INTEGER NOT NULL,
    competencia  TEXT NOT NULL,
    arquivo      TEXT NOT NULL,
    formato      TEXT DEFAULT 'CT2',   -- 'CT1' ou 'CT2'
    importado_em TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    registros    INTEGER
);
