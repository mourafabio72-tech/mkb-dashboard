-- schema.sql — MKB-Dashboard
-- Executado uma vez para criar o banco SQLite.

-- ─── USUÁRIOS (login individual, 2 níveis: admin / leitura) ────────────────
-- Substitui o DASHBOARD_USERS (env var, senha única compartilhada) -- esse
-- env var passa a servir só de SEED do 1º admin (ver auth.py bootstrap).
CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario     TEXT NOT NULL UNIQUE,   -- login (curto, ex.: "fabio")
    nome        TEXT NOT NULL,
    email       TEXT,
    senha_hash  TEXT NOT NULL,          -- werkzeug.security.generate_password_hash
    role        TEXT NOT NULL DEFAULT 'leitura',  -- 'admin' | 'leitura'
    ativo       INTEGER NOT NULL DEFAULT 1,
    criado_em   TEXT DEFAULT (datetime('now'))
);

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
    saldo_atual   REAL,                -- coluna "SALDO ATUAL" do razão (C=positivo,
                                        -- D=negativo) -- usado por Endividamento
                                        -- Tributário para saldo acumulado por conta;
                                        -- DRE/CT1 não dependem desta coluna
    UNIQUE (empresa_id, data_lanc, documento, conta_cod)
);

CREATE INDEX IF NOT EXISTS idx_razao_emp_comp ON razao (empresa_id, competencia);
CREATE INDEX IF NOT EXISTS idx_razao_conta    ON razao (conta_cod);
CREATE INDEX IF NOT EXISTS idx_razao_data     ON razao (data_lanc);

-- ─── Endividamento Tributário: vinculação parcelamento × conta contábil ─────
-- Snapshot mensal da planilha "Análise dívida tributária" -- upload manual,
-- 1 upload = 1 competência de referência (substitui tudo daquela competência).
-- O saldo devedor real (CP+LP) é calculado em tempo real a partir de
-- `razao.saldo_atual`, não armazenado aqui (mais confiável que o snapshot) --
-- EXCETO quando 2+ parcelamentos compartilham a mesma conta_cp/conta_lp (ex.:
-- "TRANSAÇÃO - DEMAIS DÉBITOS" e "TRANSAÇÃO - DÉBITOS PREVIDENCIÁRIOS" usam a
-- mesma conta 2.1.3.05.06.001): nesse caso o saldo real combinado da conta
-- precisa ser RATEADO entre os parcelamentos, e `saldo_contabilidade_snapshot`
-- (o valor já pré-dividido que vem na própria planilha) é usado como peso do
-- rateio -- confirmado que a soma dos snapshots de tributos que compartilham
-- conta bate exatamente com o saldo combinado real da conta.
CREATE TABLE IF NOT EXISTS parcelamentos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id        INTEGER NOT NULL,
    competencia_ref   TEXT NOT NULL,      -- 'YYYY-MM', da linha "Competência: MM/AAAA"
    tributo           TEXT NOT NULL,
    processo          TEXT,
    conta_cp          TEXT NOT NULL,
    conta_lp          TEXT,
    qtd_parcelas      INTEGER,
    parcela_paga      INTEGER,
    faltam            INTEGER,
    dt_inicio         TEXT,               -- 'mmm/aa' como na planilha
    dt_termino        TEXT,
    desembolso_mensal REAL,
    valor_principal   REAL,
    observacao        TEXT,
    saldo_fiscal      REAL,
    saldo_contabilidade_snapshot REAL,  -- peso de rateio p/ conta compartilhada
    -- chave por `tributo` (não `conta_cp`): a mesma conta pode acumular mais
    -- de um parcelamento (ex.: "TRANSAÇÃO - DEMAIS DÉBITOS" e "TRANSAÇÃO -
    -- DÉBITOS PREVIDENCIÁRIOS" compartilham a conta 2.1.3.05.06.001)
    UNIQUE (empresa_id, competencia_ref, tributo)
);

CREATE INDEX IF NOT EXISTS idx_parcel_emp_comp ON parcelamentos (empresa_id, competencia_ref);

-- ─── ENDIVIDAMENTO BANCÁRIO (cadastro manual, não é importação mensal) ──────
-- Diferente de `parcelamentos` (tributário, snapshot por upload de CSV),
-- aqui o cadastro é único por contrato e raramente muda. Saldo devedor e
-- total pago são calculados em tempo real a partir do Razão (mesmo padrão
-- do Endividamento Tributário) -- ver rota /endividamento-bancario.
CREATE TABLE IF NOT EXISTS emprestimos_bancarios (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id             INTEGER NOT NULL,
    banco                  TEXT NOT NULL,
    descricao              TEXT,                -- ex.: "Capital de Giro - CEF"
    conta_cp_principal     TEXT NOT NULL,
    conta_cp_juros         TEXT,                -- "(-) Juros a Apropriar", contra CP
    conta_lp_principal     TEXT,
    conta_lp_juros         TEXT,                -- "(-) Juros a Apropriar", contra LP
    valor_contratado       REAL NOT NULL,       -- valor líquido liberado (sem juros)
    valor_total_com_juros  REAL,                -- total a pagar já com juros embutidos
    qtd_parcelas           INTEGER NOT NULL,
    data_primeira_parcela  TEXT NOT NULL,       -- 'YYYY-MM'
    criado_em              TEXT DEFAULT (datetime('now'))
);

-- ─── CRONOGRAMA DE AMORTIZAÇÃO (tabela Price do contrato) ───────────────────
-- Importado uma vez da planilha do banco -- fonte confiável pro detalhamento
-- mês a mês enquanto o Razão da empresa não tem as 4 contas do empréstimo
-- (ver emprestimos_bancarios). Quando o Razão cobrir essas contas, a rota
-- pode cruzar/validar contra esta tabela.
CREATE TABLE IF NOT EXISTS emprestimos_parcelas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    emprestimo_id   INTEGER NOT NULL REFERENCES emprestimos_bancarios(id),
    numero_parcela  INTEGER NOT NULL,    -- N da planilha (1 = primeira parcela real, exclui N=0 desembolso)
    competencia     TEXT NOT NULL,       -- 'YYYY-MM'
    amortizacao     REAL,                -- parte da parcela que abate o principal
    juros           REAL,                -- parte da parcela que é juros do período
    saldo_devedor   REAL,                -- SD após esta parcela
    valor_parcela   REAL,                -- PMT (amortização + juros)
    UNIQUE (emprestimo_id, numero_parcela)
);

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

-- ─── IRPJ/CSLL: apuração de Lucro Real (planilha anual "ANUAL") ─────────────
-- Upload manual e independente do CT2 -- não tem relação com o grupo IRPJ_CSLL
-- (provisão contábil, conta 4.5.x) calculado em dre_engine.py a partir do CT2.
-- Cada linha da planilha (coluna A=conta, B=descrição, C+=meses) gera 1 registro
-- por competência, preservando a ordem original (`ordem`) para exibição fiel.
CREATE TABLE IF NOT EXISTS irpj_csll (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id  INTEGER NOT NULL,
    competencia TEXT NOT NULL,      -- 'YYYY-MM'
    secao       TEXT NOT NULL,      -- 'CSLL' | 'IRPJ'
    ordem       INTEGER NOT NULL,   -- preserva ordem original da planilha
    conta_cod   TEXT,               -- coluna A (pode ser vazia em linhas de cálculo)
    descricao   TEXT NOT NULL,      -- coluna B
    valor       REAL,               -- NULL = linha de cabeçalho de bloco (sem valor)
    is_destaque INTEGER DEFAULT 0,  -- linha "final"/"a recolher" -> card de resumo
    is_subtotal INTEGER DEFAULT 0,  -- linha de subtotal (lucro contábil, adições,
                                     -- exclusões, base bruta, devida...) -> negrito
    UNIQUE (empresa_id, competencia, secao, ordem)
);

CREATE INDEX IF NOT EXISTS idx_irpj_emp_comp ON irpj_csll (empresa_id, competencia);
