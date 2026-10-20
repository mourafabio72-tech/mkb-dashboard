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
| Sistema_de_Estilos | cor só via `var(--token)` | hex em template | templates novos | `grep -rniE "#[0-9a-f]{3,6}\b" templates/orcamento*.html` vazio | | pendente |
| Sistema_de_Estilos | nenhuma tela escreve CSS inline ou `<style>` | `style="`, `<style` | templates novos | `grep -rn 'style="\|<style' templates/orcamento*.html` vazio | | pendente |
| Componente_SelectBusca | sempre SelectBusca | `<select` nativo | templates novos | `grep -rn "<select" templates/orcamento*.html` vazio | | pendente |
| Icones_Phosphor | `ph ph-*`, sem emoji | emoji, `fa-`, `bi-` | templates novos | `grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]" templates/orcamento*.html` vazio | | pendente |
| Verificacoes_Mecanicas_de_Tela | sem travessão em tela | `—` | templates e JS novos | `grep -rn "—" templates/orcamento*.html static/orcamento* static/selectbusca.js` vazio | | pendente |
| Sem_Popup_Nativo | nunca `alert/confirm/prompt` | `alert(` | JS e templates novos | `grep -rn "alert(\|confirm(\|prompt(" templates/orcamento* static/orcamento* static/selectbusca.js` vazio | | pendente |
| Padrao_Loading_Estado | texto no gerúndio e específico | "Carregando...", "Aguarde..." | importar e consultar | `grep -rnE "Carregando\.\.\.\|Aguarde\.\.\.\|Processando\.\.\." templates/orcamento* static/orcamento*` vazio | | pendente |
| Padrao_Upload_Arquivo | `.im-msg` antes do botão; drop e clique no mesmo `label.im-drop` | botão antes da mensagem; input file visível | /orcamento/importar | CONFERENCIA_VISUAL + `grep -n "im-msg" templates/orcamento_importar.html` | | pendente |
| Padrao_Validacao_de_Input | magic bytes `50 4B 03 04`, `MAX_CONTENT_LENGTH`, UUID | confiar na extensão | upload | prova: `.exe` renomeado recusado | | pendente |
| CSRF_Cookies_Headers | todo POST com `csrf_token` | POST sem token aceito | importar | prova: POST sem token = 400 | | pendente |
| Padrao_IDOR | filtro de empresa no próprio SELECT; fora do escopo = 404 | `WHERE id = ?` sem empresa | consultas novas | prova: usuário da empresa A pede B | | pendente |
| Padrao_Mass_Assignment | whitelist fixa de colunas | INSERT montado do cabeçalho | leitor | `grep -n "join(.*columns" orcamento_*.py` vazio | Fase 1, 2026-10-20: vazio, ok (COLUNAS fixa em orcamento_parser.py:27). Refazer na Fase 2 com a gravação | ok |
| Pagina_Web_SQLite | SQL parametrizado | `execute(f"` | Python novo | `grep -n 'execute(f' orcamento_*.py` vazio | Fase 1, 2026-10-20: vazio, ok (o leitor não fala com o banco). Refazer na Fase 2 | ok |
| Padrao_Logging_Estruturado | evento de importação sem conteúdo de linha | log com dado da planilha | importar | prova lê o log | | pendente |
| Padrao_KPI_Dashboard | `.val` com `tabular-nums`, `.lbl` min-height 25px | KPI sem tabular-nums | /orcamento | `grep -n "tabular-nums" static/style.css` (bloco do módulo) | | pendente |
| Padrao_Tabela | menu `ph-list` dentro do card; export só visíveis | `ph-dots-three`, `id="...Toolbar"` | /orcamento | `grep -rn "ph-dots-three\|Toolbar\"" templates/orcamento* static/orcamento*` vazio | | pendente |
| Padrao_Cabecalho_da_Tabela | `.tabela-wrap` sem `overflow:hidden` | `overflow:hidden` no card do menu | /orcamento | `grep -n "tabela-wrap" static/style.css` | | pendente |
| Padrao_Filtro_por_Coluna | `placeholder="filtrar"`, evento `input` | filtro no Enter | /orcamento | `grep -rn 'placeholder="filtrar"' static/orcamento* templates/orcamento*` | | pendente |
| Padrao_Barra_de_Filtros | controles na mesma altura, Consultar à direita | Consultar à esquerda | /orcamento | CONFERENCIA_VISUAL | | pendente |
| Padrao_Toggle_Tipos | estilo escolhido em D4, estado `.on`, `role="radiogroup"` | estilo escolhido sozinho; `<a>` no lugar de `<button>` | /orcamento | `grep -n 'role="radiogroup"' templates/orcamento.html` + CONFERENCIA_VISUAL | | pendente |
| Padrao_Box_Card | raio e sombra por token | `border-radius: 6px`, sombra rgba solta | CSS novo | `grep -nE "border-radius:\s*(6\|10)px" static/orcamento*` vazio | | pendente |
| Escada_Preguica_de_Codigo | uma checagem executável por lógica não trivial | parser sem prova | Fases 1 a 4 | `ls provas/prova_orcamento_*.py` | Fase 1, 2026-10-20: provas/prova_orcamento_leitor.py (43 ok, exit 0; mutação no centro derruba). Fases 2 a 4 acrescentam as delas | parcial |
| Revisao_Vulnerabilidades | checklist antes do deploy | segredo em `.py`, `| safe` | Fase 5 | greps da Fase 5 do CHECKLIST | | pendente |
