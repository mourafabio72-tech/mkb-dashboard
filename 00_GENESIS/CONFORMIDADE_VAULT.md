# CONFORMIDADE_VAULT

Projeto: FinHub (`_deploy_mkb`), trabalho Orçamento
Criado em: 2026-10-20

Uma linha por REGRA. `Status` só vira `ok` com a saída real do comando em `Evidencia`, ou com
`conferencia visual feita em <data>, tela <qual>`. **Fase de tela não fecha com linha pendente.**
Escopo dos greps: só os arquivos novos do módulo (`templates/orcamento*.html`, `static/orcamento*`,
`static/selectbusca.js`, `orcamento_*.py`). As telas antigas são herança declarada no CLAUDE.md do projeto.

## Decisões cravadas na abertura

```
Token de cor: os do FinHub (--primary, --accent, --card, --border, --text, --muted)
Arquivo do token: static/style.css
Valor inicial: Sage & Creme do FinHub (já existente)
Tema: ambos, com alternador (já existente)
Estilo de toggle escolhido: Abrir por = multi opções; No mês/Acumulado = duas opções (D4 = 4a, 2026-10-20)
PROIBIDO: o hex aparecer em qualquer template novo
```

## Matriz

| Nota | Regra literal | Proibido | Onde aplica | Prova | Evidencia | Status |
|---|---|---|---|---|---|---|
| Sistema_de_Estilos | cor só via `var(--token)` | hex em template | templates novos | `grep -rniE "#[0-9a-f]{3,6}\b" templates/orcamento*.html` vazio | Fases 2 e 4, 2026-10-20: vazio, ok (templates orcamento*, orcamento.css, cartões do cadastro e do hub sem hex) | ok |
| Sistema_de_Estilos | nenhuma tela escreve CSS inline ou `<style>` | `style="`, `<style` | templates novos | `grep -rn 'style="\|<style' templates/orcamento*.html` vazio | Fases 2 e 4 (refeita em 2026-10-20 com orcamento.html e orcamento_tela.js): vazio, ok | ok |
| Componente_SelectBusca | sempre SelectBusca | `<select` nativo | templates novos | `grep -rn "<select" templates/orcamento*.html` vazio | Fases 2 e 4 (refeita em 2026-10-20 com orcamento.html e orcamento_tela.js): vazio, ok (o comentário que acusava foi reescrito) | ok |
| Icones_Phosphor | `ph ph-*`, sem emoji | emoji, `fa-`, `bi-` | templates novos | `grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]" templates/orcamento*.html` vazio | Fases 2 e 4 (refeita em 2026-10-20 com orcamento.html e orcamento_tela.js): vazio, ok | ok |
| Verificacoes_Mecanicas_de_Tela | sem travessão em tela | `—` | templates e JS novos | `grep -rn "—" templates/orcamento*.html static/orcamento* static/selectbusca.js` vazio | Fases 2 e 4 (refeita em 2026-10-20 com orcamento.html e orcamento_tela.js): vazio, ok | ok |
| Sem_Popup_Nativo | nunca `alert/confirm/prompt` | `alert(` | JS e templates novos | `grep -rn "alert(\|confirm(\|prompt(" templates/orcamento* static/orcamento* static/selectbusca.js` vazio | Fases 2 e 4 (refeita em 2026-10-20 com orcamento.html e orcamento_tela.js): vazio, ok | ok |
| Padrao_Loading_Estado | texto no gerúndio e específico | "Carregando...", "Aguarde..." | importar e consultar | `grep -rnE "Carregando\.\.\.\|Aguarde\.\.\.\|Processando\.\.\." templates/orcamento* static/orcamento*` vazio | Fases 2 e 4 (refeita em 2026-10-20 com orcamento.html e orcamento_tela.js): vazio, ok ('Lendo...' e 'Gravando o orçamento de <ano>...') | ok |
| Padrao_Upload_Arquivo | `.im-msg` antes do botão; drop e clique no mesmo `label.im-drop` | botão antes da mensagem; input file visível | /orcamento/importar | CONFERENCIA_VISUAL + `grep -n "im-msg" templates/orcamento_importar.html` | Fase 2: im-msg em :51 e :92, antes dos botões; conferência no Chrome em 2026-10-20, /orcamento/importar em 1366, 375 e escuro (drop, clique, estado verde, recusa de PDF) | ok |
| Padrao_Validacao_de_Input | magic bytes `50 4B 03 04`, `MAX_CONTENT_LENGTH`, UUID | confiar na extensão | upload | prova: `.exe` renomeado recusado | Fase 2: prova .exe renomeado = 400, 31 MB = 413, sem tamanho = 411 | ok |
| CSRF_Cookies_Headers | todo POST com `csrf_token` | POST sem token aceito | importar | prova: POST sem token = 400 | Fase 2: prova sem token = 400, token errado = 400 | ok |
| Padrao_IDOR | filtro de empresa no próprio SELECT; fora do escopo = 404 | `WHERE id = ?` sem empresa | consultas novas | prova: usuário da empresa A pede B | Fase 2 (importar): empresa fora = 404 com ACESSO_NEGADO_IDOR. Fase 4 (leitura): cliente do hub da MKB = 403/404 na Gnileb e 404 no consolidado (prova_orcamento_tela) | ok |
| Padrao_Mass_Assignment | whitelist fixa de colunas | INSERT montado do cabeçalho | leitor | `grep -n "join(.*columns" orcamento_*.py` vazio | Fase 1, 2026-10-20: vazio, ok (COLUNAS fixa em orcamento_parser.py:27). Refazer na Fase 2 com a gravação | ok |
| Pagina_Web_SQLite | SQL parametrizado | `execute(f"` | Python novo | `grep -n 'execute(f' orcamento_*.py` vazio | Fase 1, 2026-10-20: vazio, ok (o leitor não fala com o banco). Refazer na Fase 2 | ok |
| Padrao_Logging_Estruturado | evento de importação sem conteúdo de linha | log com dado da planilha | importar | prova lê o log | Fase 2: prova lê o log: ORCAMENTO_IMPORTADO com request_id, sem conta, centro nem descrição | ok |
| Padrao_KPI_Dashboard | `.val` com `tabular-nums`, `.lbl` min-height 25px | KPI sem tabular-nums | /orcamento | `grep -n "tabular-nums" static/style.css` (bloco do módulo) | Fase 4, 2026-10-20: tabular-nums em static/orcamento.css:213, lbl min-height 25px em :209 | ok |
| Padrao_Tabela | menu `ph-list` dentro do card; export só visíveis | `ph-dots-three`, `id="...Toolbar"` | /orcamento | `grep -rn "ph-dots-three\|Toolbar\"" templates/orcamento* static/orcamento*` vazio | Fase 4: grep vazio; menu na ordem do padrão (prova passo 6) | ok |
| Padrao_Cabecalho_da_Tabela | `.tabela-wrap` sem `overflow:hidden` | `overflow:hidden` no card do menu | /orcamento | `grep -n "tabela-wrap" static/style.css` | Fase 4: static/orcamento.css:226 sem overflow; popup inteiro no Chrome | ok |
| Padrao_Filtro_por_Coluna | `placeholder="filtrar"`, evento `input` | filtro no Enter | /orcamento | `grep -rn 'placeholder="filtrar"' static/orcamento* templates/orcamento*` | Fase 4: templates/orcamento.html:147; Chrome 'norte' = 1 de 4 | ok |
| Padrao_Barra_de_Filtros | controles na mesma altura, Consultar à direita | Consultar à esquerda | /orcamento | CONFERENCIA_VISUAL | Fase 4: conferência visual no Chrome em 2026-10-20, /orcamento em 1366, 375 e escuro: controles em 38px, Consultar à direita | ok |
| Padrao_Toggle_Tipos | estilo escolhido em D4, estado `.on`, `role="radiogroup"` | estilo escolhido sozinho; `<a>` no lugar de `<button>` | /orcamento | `grep -n 'role="radiogroup"' templates/orcamento.html` + CONFERENCIA_VISUAL | Fase 4: role=radiogroup em templates/orcamento.html:50 e :63; conferência visual em 2026-10-20 (tipo 2 sólido, tipo 1 suave) | ok |
| Padrao_Box_Card | raio e sombra por token | `border-radius: 6px`, sombra rgba solta | CSS novo | `grep -nE "border-radius:\s*(6\|10)px" static/orcamento*` vazio | Fase 2, 2026-10-20: vazio, ok, depois de trocar dois 10px por 12px (Fase 2) e um 6px por 8px (Fase 4) que a própria matriz acusou | ok |
| Escada_Preguica_de_Codigo | uma checagem executável por lógica não trivial | parser sem prova | Fases 1 a 4 | `ls provas/prova_orcamento_*.py` | Fase 1, 2026-10-20: provas/prova_orcamento_leitor.py (43 ok, exit 0; mutação no centro derruba). Fases 2 a 4: prova_orcamento_importar (52), prova_orcamento_calculo (49), prova_orcamento_tela (49) | ok |
| Revisao_Vulnerabilidades | checklist antes do deploy | segredo em `.py`, `| safe` | Fase 5 | greps da Fase 5 do CHECKLIST | | pendente |
