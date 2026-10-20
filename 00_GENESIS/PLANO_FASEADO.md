---
tipo: plano
projeto: FinHub (_deploy_mkb), trabalho Orçamento
gerado_em: 2026-10-20
status_geral: in_progress
aprovado_por_usuario: true (2026-10-20, reaprovado com D2 = 2c)
---

# Plano faseado: Orçamento (Orçado x Realizado)

Objetivo (palavras do Fábio, 2026-10-20): "comparar o realizado que já temos com orçamento que iremos subir".
O orçado e o realizado casam por conta contábil + centro de custo + mês.

**Este arquivo é o contrato.** Escopo novo para tudo, entra aqui, e só depois vira código.

Decisões fechadas na Fase 0 (Fábio respondeu "aprovado" sem alterar os padrões, 2026-10-20):
- D1 Arquivo do orçamento = Rel_OrcRel exportado do Protheus, leitor fixo (1a).
- D2 Empresas = MKB e Gnileb, cada uma com o seu orçamento, mais o consolidado (2c; trocado de 2b pelo Fábio em 2026-10-20).
- D5 Consolidado: centro de custo com o mesmo código na MKB e na Gnileb é o mesmo centro e soma (Fábio, 2026-10-20).
- D6 Consolidado: vendas entre MKB e Gnileb são eliminadas, no orçado e no realizado (Fábio, 2026-10-20).
  ABERTO: como reconhecer a venda entre elas no razão e no Rel_OrcRel (conta própria ou outra marca). O consolidado da DRE
  de hoje (`dre_engine.calcular_consolidado`) elimina só a Equivalência Patrimonial, não venda entre as empresas.
  Medido na Fase 3 (razão 2026) e confirmado pelo Fábio em 2026-10-20: não há venda entre MKB e Gnileb; o único lançamento
  entre elas é a Equivalência Patrimonial (CONTAS_EP do dre_engine). Regra: o consolidado do orçamento elimina só a
  Equivalência Patrimonial, igual à DRE consolidada; as duas telas dão o mesmo número. Volta se surgir conta própria de
  venda entre elas. A receita da Gnileb é de terceiros (Fábio).
- D7 Gnileb (Fábio, 2026-10-20): não existe orçamento da Gnileb neste momento. A Gnileb entra com orçado zero e
  realizado do razão, que não tem centro de custo: na Gnileb só se abre por linha da DRE; no consolidado, o realizado
  dela vai para "Sem centro de custo".
- D3 Linhas do quadro = DRE gerencial do FinHub, as mesmas linhas da tela DRE (3a).
- D4 Estilo dos seletores = Abrir por: multi opções; No mês/Acumulado: duas opções (4a).

---

## Fase 0: Aprovação do plano

- **Status:** done (2026-10-20)
- **Critério de aceite:** Fábio responde D1 a D4 e "aprovado" (ou "ajusta X"); linha `plano_aprovado` no LOG.

## Fase 1: Base do orçamento e leitor do Rel_OrcRel

- **Status:** done (2026-10-20)
- **Duração estimada:** 3h
- **O que entra:** tabelas novas no SQLite, criadas no boot pelo `criar_schema` (padrão `PRAGMA table_info` do `ingestion.py`):
  `orcamento` (empresa_id, competencia, conta_cod, centro_custo, valor, lote_id; UNIQUE empresa+competência+conta+centro),
  `centros_custo` (empresa_id, codigo, descricao, servico, coordenador, filial, tipo; UNIQUE empresa+código) e
  `orcamento_lotes` (quem, quando, ano, arquivo, linhas, total). Módulo novo `orcamento_parser.py`: lê as abas DADOS
  (`CQ2_TPSALD=0`, orçado) e CTT, mês por extenso ou 1 a 12, ano digitado (a coluna ANO vem incompleta), conta sem espaço,
  centro sem ponto, sinal na convenção do `razao.valor` do FinHub (crédito menos débito).
- **Critério de aceite:** `provas/prova_orcamento_leitor.py` passa com planilha sintética gerada na própria prova
  (sem dado de cliente no git): conta, centro, mês, sinal, linha inválida rejeitada com motivo, aba faltando dá erro claro.
  Rodar o leitor no `Rel_OrcRel_2026.xlsx` real dá 45.335 linhas de orçado, o mesmo número conferido no app de origem.
- **Notas:** Padrao_Mass_Assignment, Padrao_Validacao_de_Input, Pagina_Web_SQLite, Escada_Preguica_de_Codigo.
- **Dependências:** Fase 0.
- **Output:** `orcamento_parser.py`, `schema.sql` (ou bloco em `ingestion.py`), `provas/prova_orcamento_leitor.py`.

## Fase 2: Tela Importar orçamento (com a segurança do upload)

- **Status:** done (2026-10-20)
- **Duração estimada:** 4h
- **O que entra:** rota `/orcamento/importar` (GET e POST, `@login_required` + `@admin_required`), escolha de empresa e ano,
  upload no padrão `im-drop`, **prévia** (linhas, total por mês, centros novos, contas sem grupo na DRE) antes de gravar,
  confirmar substitui o ano inteiro daquela empresa numa transação. Componente SelectBusca criado aqui
  (`static/selectbusca.js` + CSS), usado só em tela nova. Segurança junto da superfície que ela protege: CSRF no form,
  `MAX_CONTENT_LENGTH`, magic bytes do xlsx (`50 4B 03 04`), nome do arquivo trocado por UUID e apagado depois de ler,
  empresa do POST validada contra `empresas_permitidas()`, evento de log de importação sem conteúdo da planilha.
- **Critério de aceite:** prova com cliente de teste do Flask: POST sem token dá 400; usuário `leitura` não importa;
  `.exe` renomeado para `.xlsx` é recusado; empresa fora do escopo é recusada; importar duas vezes o mesmo ano não duplica;
  bateria da `Verificacoes_Mecanicas_de_Tela` zerada no template novo.
- **Notas:** Padrao_Upload_Arquivo, Componente_SelectBusca, Padrao_Loading_Estado, Sem_Popup_Nativo, CSRF_Cookies_Headers,
  Padrao_Validacao_de_Input, Padrao_IDOR, Padrao_Logging_Estruturado, Padrao_Acao_Primaria_na_Topbar.
- **Dependências:** Fase 1.
- **Output:** `templates/orcamento_importar.html`, `static/selectbusca.js`, CSS em `static/style.css`, rotas, `provas/prova_orcamento_importar.py`.

## Fase 3: Cálculo do Orçado x Realizado

- **Status:** done (2026-10-20)
- **Duração estimada:** 4h
- **O que entra:** `orcamento_engine.py`, motor nosso. Realizado direto da `razao` (contas 3 e 4, centro sem ponto),
  orçado da `orcamento`, linhas pela DRE gerencial do FinHub (`classificar_conta`, o mesmo mapa das telas DRE),
  No mês e Acumulado no ano, variação em valor e %, Abrir por linha da DRE, serviço, coordenador, filial ou centro, e
  filtros por esses quatro. Mês sem razão importado sai marcado como "sem realizado", e não como zero.
  Visão Consolidado: soma MKB + Gnileb por conta + centro + mês (D5), elimina a Equivalência Patrimonial como a DRE já faz
  e as vendas entre as duas pela regra de D6, com a eliminação numa linha própria (Ajuste), como na DRE consolidada.
- **Critério de aceite:** `provas/prova_orcamento_calculo.py` com base sintética: total do quadro = soma do orçado e do
  realizado; Abrir por qualquer dimensão soma o mesmo total; acumulado = soma dos meses; consolidado = MKB + Gnileb menos a
  equivalência patrimonial (D6), com o valor eliminado devolvido à parte (eliminado_equivalencia) para a tela mostrar a linha
  de Ajuste na Fase 4. Realizado do motor = DRE gerencial do FinHub, mês a mês, nas três visões. Mais um comparador versionado
  (`provas/conferir_orcamento_real.py`, recebe os caminhos dos arquivos por argumento e não guarda dado) que reproduz a
  conferência do app de origem: REALIZADO da aba DADOS x realizado do FinHub, célula a célula. Já medido em maio/2026: 4.180 de 4.180.
- **Notas:** Escada_Preguica_de_Codigo (reusar `dre_engine`), Padrao_IDOR (toda consulta filtra empresa).
- **Dependências:** Fase 1 (Fase 2 em paralelo não, os dois mexem em `app.py`).
- **Output:** `orcamento_engine.py`, as duas provas.

## Fase 4: Tela Orçado x Realizado

- **Status:** pending
- **Duração estimada:** 5h
- **O que entra:** rota `/orcamento` (`@login_required`, empresa por `_guard_empresa`), card novo no hub do dashboard,
  KPIs (Orçado, Realizado, Variação, % realizado), barra de filtros (empresa com MKB, Gnileb e Consolidado, ano, mês, No mês/Acumulado, Abrir por,
  filtros de centro, serviço, coordenador e filial com SelectBusca), tabela no padrão do card com menu `ph-list`
  (Filtro por coluna, Exportar CSV, Exportar Excel, só linhas visíveis), sinal de cor por variação pelos tokens.
- **Critério de aceite:** bateria da `Verificacoes_Mecanicas_de_Tela` zerada nos templates novos; `conferir-telas` sem erro
  em computador e celular, claro e escuro; usuário de uma empresa não vê a outra (404/redirect, testado na prova);
  número da tela = número da prova da Fase 3 para o mesmo filtro.
- **Notas:** Padrao_Tabela, Padrao_Cabecalho_da_Tabela, Padrao_Filtro_por_Coluna, Padrao_Barra_de_Filtros,
  Padrao_KPI_Dashboard, Padrao_Toggle_Tipos, Componente_SelectBusca, Padrao_Loading_Estado, Padrao_Box_Card, Sistema_de_Estilos, Icones_Phosphor.
- **Dependências:** Fases 2 e 3.
- **Output:** `templates/orcamento.html`, JS da tabela, CSS, item no hub, `provas/prova_orcamento_tela.py`.

## Fase 5: Conferência com dado real, publicação e entrega

- **Status:** pending
- **Duração estimada:** 2h
- **Critério de aceite:**
  - Banco local de teste com os razões reais da MKB (jan a ago/2026, em `~/Downloads`, fora do git) e o Rel_OrcRel 2026:
    o comparador da Fase 3 bate nos 8 meses (diferença só onde houver lançamento retroativo, com mês e centro listados).
  - Antes do push, `Revisao_Vulnerabilidades` rodado e colado no LOG; todas as provas de `provas/` verdes.
  - `CLAUDE.md` do projeto ganha o módulo (mapa de arquivos, tabelas, quirk do centro sem ponto).
  - Push no `master`; `curl -s https://dre.zoaria.com.br/health` com o `build` igual ao HEAD.
  - Fábio importa o orçamento real em produção e confere um mês na tela.
  - ZIP de versão em `z_Versoes/` e linha `fase=5 acao=entrega resultado=ok` no LOG.
- **Dependências:** Fase 4.

---

## Riscos conhecidos

- **Chave do razão sem centro de custo.** A UNIQUE do `razao` é (empresa, data, documento, conta). Rateio do mesmo
  documento em dois centros, na mesma conta e no mesmo dia, sobrescreve um ao outro no CT1. Em maio/2026 a medição bateu
  100%, então não aconteceu ali. O comparador da Fase 5 olha os 8 meses; se aparecer, vira fase própria (mexer na chave
  do razão é mexer na DRE inteira, e não entra calado).
- **Mês só com CT2 Comparativo** não tem centro de custo: o quadro mostra "sem realizado" naquele mês.
- **Retroativo do Protheus:** o razão envelhece até reimportar. Mesma regra que o FinHub já tem.

## Fora de escopo (cortado pela escada)

- Tela de mapeamento de colunas (opção A da importação): cortada se D1 = Rel_OrcRel de layout fixo. Volta se o layout variar.
- Cadastro editável de centros de custo: os centros vêm da aba CTT a cada importação. Volta se o CTT vier incompleto.
- Versões de orçamento (original x revisado): importar substitui o ano. Volta se o Fábio pedir revisão orçamentária.
- Gráfico: o quadro é tabela com KPIs. Volta se pedirem.
- Os 17 grupos do Rel_OrcRel (CONTAS AGRUPADAS) como linhas: fora pelo padrão de D3. Volta se D3 = b.
- Conferência com a coluna REALIZADO do arquivo dentro do app: fica no comparador de `provas/`, não vira tela.

## Histórico de mudanças neste plano

- 2026-10-20: plano criado (genesis-iniciar, ampliação).
- 2026-10-20: aprovado pelo Fábio ("aprovado"), D1 a D4 nos padrões 1a, 2b, 3a, 4a.
- 2026-10-20: D2 trocado para 2c (consolidado entra), com D5 (mesmo código de centro = mesmo centro) e D6 (eliminar venda
  entre MKB e Gnileb). Fases 3 e 4 ampliadas. Reaprovado pelo Fábio ("aprovado"); regra da D6 medida e confirmada na Fase 3.
- 2026-10-20 (Fase 3): D6 fechada (elimina só a equivalência patrimonial) e D7 (Gnileb sem orçamento, razão sem centro).
- 2026-10-20 (Fase 3): critério do consolidado reescrito pela D6 (não há venda entre as empresas; elimina só a equivalência) e cruzamento com a DRE gerencial acrescentado ao aceite.
