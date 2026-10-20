---
tipo: notas_lidas
projeto: FinHub, trabalho Orçamento
gerado_em: 2026-10-20
---

# Notas lidas na descoberta (2026-10-20)

Vault: `/Users/fabiomoura/ObsidianJovi`. Lidas integralmente pelo principal: as duas doutrinas,
`Importacao_Externa_Pergunta_Estrategia` (103 linhas, fim "Ver também") e `Padrao_IDOR` (199 linhas, fim "Histórico").
As demais vieram em ficha de dois batedores sonnet (eixo UI e eixo segurança/estilo), com regra literal, proibido e prova.
A ficha de segurança foi conferida contra a `Padrao_IDOR` aberta pelo principal.

| Nota | Como foi achada | Trecho chave | Fase |
|---|---|---|---|
| Anti_Puxa_Saco | boot | "Fale a verdade util, nao a verdade agradavel." | todas |
| Leitura_e_Retencao_de_Notas | boot | "Proibido citar nota da vault sem ter feito Read nela NESTA sessao." | todas |
| Brainstorming_Socratico_por_Tarefa | skill (A3) | 2 a 4 perguntas com opções objetivas, numa mensagem só, antes do plano | 0 |
| Importacao_Externa_Pergunta_Estrategia | grep (importação) | arquivo de ERP: perguntar A (mapeamento) ou B (parser fixo) ou híbrido | 0, 1 |
| Padrao_Validacao_de_Input | batedor seg | magic bytes (xlsx = ZIP `50 4B 03 04`), `MAX_CONTENT_LENGTH`, `request.form.get`, int em try | 2 |
| Padrao_IDOR | principal | filtro de dono no próprio SELECT; sem dono, 404 | 1, 2, 3, 4 |
| Padrao_Mass_Assignment | batedor seg | whitelist de campos; colunas nunca montadas a partir do cabeçalho da planilha | 1, 2 |
| CSRF_Cookies_Headers | batedor seg | todo POST com `csrf_token` ou `X-CSRF-Token` | 2 |
| Padrao_Logging_Estruturado | batedor seg | importação e export geram evento; conteúdo da planilha nunca no log | 2, 4 |
| Principios / Revisao_Vulnerabilidades | batedor seg | SQL parametrizado; sem `| safe` em dado do usuário | todas |
| Padrao_Dependencias_Lockfile | batedor seg | dependência pinada (openpyxl e pandas já estão com `==`) | 1 |
| Pagina_Web_SQLite | batedor seg | um worker; nunca SQL com f-string; upload fora de `static/` | todas |
| Padrao_Upload_Arquivo | batedor UI | `label.im-drop` + input fora da tela; `.im-msg` antes do botão; sem `alert(` | 2 |
| Padrao_Excel_Template_Importacao | batedor UI | linha 1 cabeçalho, linha 2 exemplo, `freeze_panes="A2"`, `DataValidation` | 2 (condicional) |
| Padrao_Tabela / Cabecalho / Filtro_por_Coluna | batedor UI | menu `ph-list` dentro do card; export só linhas visíveis; `placeholder="filtrar"` | 4 |
| Padrao_Barra_de_Filtros | batedor UI | `.fu-bar`, controles na mesma altura, Consultar à direita | 4 |
| Padrao_KPI_Dashboard | batedor UI | `.val` com `tabular-nums`, `.lbl` min-height 25px; KPI só em relatório | 4 |
| Componente_SelectBusca | batedor UI | nunca `<select>` nativo; `<div class="selectbusca">` + `selectbusca.js` | 2, 4 |
| Padrao_Toggle_Tipos | batedor UI | 3 estilos; **perguntar** qual; estado `.on`; `role="radiogroup"` | 4 |
| Padrao_Loading_Estado | batedor UI | texto no gerúndio e específico; proibido "Carregando..." | 2, 4 |
| Padrao_Box_Card / Sem_Popup_Nativo / Padrao_Acao_Primaria_na_Topbar | batedor UI | raio por token; sem `alert/confirm/prompt`; ação primária na topbar | 2, 4 |
| Verificacoes_Mecanicas_de_Tela | batedor UI | bateria de grep de fechamento de fase de tela | 2, 4, 5 |
| Sistema_de_Estilos / Icones_Phosphor | batedor seg | cor só por token; ícone `ph ph-*` | 2, 4 |
| Escada_Preguica_de_Codigo | batedor seg | 7 degraus; guardrails intocáveis; uma checagem executável por lógica não trivial | plano |

## Lidas e descartadas

- Padrao_Menu_Sidebar: FinHub tem navbar no topo, herança declarada.
- Perfis_e_Modulos, Matriz_VER_EDITAR, Auto_Liberacao_por_Grupo: FinHub não tem tabela `modulos`; admin/leitura.
- Forca_Bruta_Login, Admin_Inicial_Padrao, Timeout_de_Sessao: login existente, fora do escopo.
- Padrao_Marca_IA: sem IA no módulo. (Divergência registrada: a nota manda roxo; o FinHub usa teal `--ia-*` por decisão anterior.)
- Padrao_Tabs, Padrao_Modal_Popup_Centrado: só entram se a tela precisar; o plano não prevê aba nem modal com SelectBusca.

## Fontes fora da vault (medidas, não notas)

- Levantamento do app de origem: `side-session-notes/.../finhub_orcamento_origem.md` (DDL literal e riscos do port).
- Medição de casamento: razão `~/Downloads/MKB - RAZÃO 05.2026.xlsx` lido pelo `razao_parser.parse_razao` do FinHub
  contra `app-contabil-com-ia/Rel_OrcRel_2026.xlsx`, aba DADOS. 27.147 lançamentos, 10.721 de resultado, 0 sem centro.
  Com normalização: 4.182 de 4.182 chaves do razão existem no orçamento; 4.180 de 4.180 células de REALIZADO batem.
