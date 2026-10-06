# FinHub (MKB-Dashboard)

> Antes de TUDO: existe uma **vault Obsidian** em `/Users/fabiomoura/ObsidianJovi/` que é a
> **fonte da verdade** para regras técnicas, padrões visuais, segurança, auth, layout e copy.
> Nada neste projeto se decide de cabeça quando a vault tem nota sobre o assunto.

## ANTES de qualquer tarefa, OBRIGATÓRIO LER (vault Obsidian)

1. `/Users/fabiomoura/ObsidianJovi/CLAUDE.md`
   manual mestre, com o BOOT DA VAULT e a tabela de precedência
2. `/Users/fabiomoura/ObsidianJovi/00A_MAPAS/_MAPA_CHAVES.md`
   índice de todos os padrões técnicos
3. `/Users/fabiomoura/ObsidianJovi/00B_DOUTRINAS/Anti_Puxa_Saco.md`
   cláusula pétrea universal: verdade útil antes de tom agradável
4. `/Users/fabiomoura/ObsidianJovi/00B_DOUTRINAS/Leitura_e_Retencao_de_Notas.md`
   cláusula pétrea universal: nota se lê integral, e citação exige Read na sessão
5. `/Users/fabiomoura/ObsidianJovi/01_SISTEMAS/07_Regras_de_Ouro/Padroes_do_Vault_na_Integra.md`
   padrão da vault se cumpre inteiro: citação, checklist, gate e auto-revisão
6. `/Users/fabiomoura/ObsidianJovi/01_SISTEMAS/07_Regras_de_Ouro/Economia_de_Tokens.md`
7. `/Users/fabiomoura/ObsidianJovi/01_SISTEMAS/07_Regras_de_Ouro/Cross_Pasta_via_Mapa.md`

E mais um, que não é da vault e vale só aqui:

8. `/Users/fabiomoura/CLAUDE_FABIO/CLAUDE.md`
   convenções do ecossistema Zoaria e BPS4: SSO do Hub, EasyPanel, tema Sage e Creme,
   regra de segredo por variável de ambiente

## Antes de ESCREVER UI, HTML ou CSS, ler os padrões aplicáveis

Pelo `_MAPA_CHAVES.md`, identifique e leia ANTES de escrever uma linha:

| Se envolver | Leia |
|---|---|
| Menu lateral | `Padrao_Menu_Sidebar`, `Padrao_Sidebar_Rodape` |
| Listagem com 4 ou mais linhas | `Padrao_Tabela`, `Padrao_Cabecalho_da_Tabela`, `Padrao_Barra_de_Filtros`, `Padrao_Filtro_por_Coluna` |
| Indicadores no topo | `Padrao_KPI_Dashboard`, `Listagens_sem_KPI` |
| Formulário | `Padrao_Formulario`, `Componente_SelectBusca`, `Font_Inherit_em_Form` |
| Caixa ou card | `Padrao_Box_Card` |
| Modal | `Padrao_Modal`, `Padrao_Modal_Nao_Fecha_Sozinho`, `Padrao_Modal_Popup_Centrado`, `Sem_Popup_Nativo` |
| Upload | `Padrao_Upload_Arquivo`, `Padrao_Validacao_de_Input` |
| Liga e desliga | `Padrao_Toggle_OnOff`, `Padrao_Toggle_Tipos` |
| Abas | `Padrao_Tabs` |
| Modelo de Excel | `Padrao_Excel_Template_Importacao` |
| Loading | `Padrao_Loading_Estado`, `Sempre_Mostrar_Loading` |
| Qualquer coisa vinda de modelo de IA | `Padrao_Marca_IA`, `Sempre_Marcar_IA` |

Se não leu, não escreva HTML. Pergunte qual padrão usa.

**Cumpra o padrão na íntegra, não um resumo dele.** Antes de codar: cite o trecho da nota com
arquivo e linha, vire cada regra em item de checklist, mostre e espere o ok, e no fim releia a nota
marcando item a item. Cortar item em silêncio é bug, não economia. Vale igual para segurança e auth.

## Skill que rege a execução

Este projeto é conduzido pelo método GENESIS. Para retomar, `/genesis-continuar`: ela lê o `LOG.md`
integral, recarrega o LASTRO e continua da fase aberta.

A skill `obsidian-keys` citada pelo template original da vault **não existe nesta máquina**. O que
existe aqui é o pacote `joviano-obsidian` e as skills `genesis-*`.

## Hierarquia de precedência (em conflito, vence quem está mais abaixo)

```
Doutrinas da vault (00B_DOUTRINAS/, cláusula pétrea, nunca perdem)
        >>>
Convenções gerais da vault (01_SISTEMAS/)
        >>>
Convenções do workspace Zoaria (/Users/fabiomoura/CLAUDE_FABIO/CLAUDE.md)
        >>>
Quirks deste projeto (descritos NESTE arquivo abaixo; decisões do Pergunte à IA no zip do 00_GENESIS)
        >>>
Pedido específico desta sessão
```

---

# CONVENÇÕES ESPECÍFICAS DESTE PROJETO

## O que o app faz

FinHub do Grupo Markbuilding (MKB e MKB Participações / Gnileb): DRE contábil e gerencial,
receita por cliente, despesa por fornecedor, IRPJ/CSLL, endividamento tributário e bancário,
balanço e validação DRE x balancete. Em produção em `dre.zoaria.com.br`, entrada pelo SSO do Hub.

## Stack e como rodar no Mac

- Flask + SQLite. Python mínimo **3.11** (pandas 3.0.2). O Mac tem 3.9 no sistema:
  rodar com `uv run --python 3.12 python app.py`.
- Banco: `DB_PATH` (prod `/data/mkb_dre.db`, volume do EasyPanel). Sem a variável, usa
  `mkb_dre.db` na pasta do projeto.
- Os caminhos `C:\Users\FabioMoura\...` do `config.py` são do Windows antigo: no Mac a
  importação entra por upload em `/ingest`, não pela pasta do OneDrive.

## Mapa de arquivos

| Arquivo | Papel |
|---|---|
| `app.py` | rotas, guards (`_guard_empresa`, `admin_required`), CSRF, headers, `/health` |
| `auth.py` | sessão local + SSO do Hub, `empresas_permitidas()` |
| `dre_engine.py` | cálculo: `calcular_dre_mensal`, `calcular_dre_detalhada`, `analisar_receita_clientes`, `analisar_despesas_fornecedores`, `classificar_conta` |
| `*_parser.py`, `ingestion.py` | importação de balancete, razão, endividamento, IRPJ/CSLL |
| `config.py` | env vars, empresas, caminhos |
| `versao.py` | carimbo do `/health` |
| `provas/` | provas executáveis, uma por lógica não trivial |
| `templates/`, `static/style.css` | telas (Jinja) e o tema Sage & Creme |

## Variáveis de ambiente

`SECRET_KEY`, `DB_PATH`, `PORT`, `DEBUG` (padrão `false`), `DASHBOARD_USERS` (seed do 1º
admin, sem valor padrão), `ZOARIA_SECRET_KEY`, `ZOARIA_COOKIE_DOMAIN`, `ZOARIA_COOKIE_NAME`,
`HUB_URL`, `OPENAI_API_KEY`, `AI_RESOLVER_ENABLED`. Valor nunca neste arquivo.

## Quirks

- **Publica do branch `master`**, não `main`. Auto-deploy por webhook do GitHub.
- **`Dockerfile` usa `COPY . .`**: arquivo novo entra na imagem; tudo que o `.dockerignore`
  não barra também entra. Conferir o `.dockerignore` antes de acrescentar pasta.
- **Carimbo de versão em `GET /health`** (`{"build":"AAAAMMDD-HHMM"}`): é assim que se
  pergunta à produção o que ela serve.
- **Provas:** scripts em `provas/` apontam `DB_PATH` para um arquivo temporário ANTES de
  importar `app`. Rodar com `uv run --python 3.12 python provas/<arquivo>.py`.
- **Visual Sage & Creme** com alternador claro/escuro. Tokens do FinHub: `--primary`,
  `--accent`, `--card`, `--border`, `--text`, `--muted`. IA usa `--ia-*` em teal
  `#3A7D76` (sinal de IA da paleta, o mesmo da Conciliação), nunca roxo.
- **Ajuste de saldo exige aprovação humana:** o app nunca lança `AJUSTE-SALDO` sozinho.
- **Protheus lança retroativo:** o delator é o "Saldo anterior" do balancete; excluir o razão
  do mês antes de reimportar.
- **Chave de IA:** variável de ambiente vence o arquivo no diretório do banco
  (`/data/openai_key.txt`, `/data/nvidia_key.txt`). A chave nunca volta ao navegador nem ao log.
- **Isolamento por empresa:** toda rota com `<empresa>` ou `?empresa=` passa por
  `_guard_empresa`. Código novo que recebe empresa valida contra `empresas_permitidas()`.

## Herança conhecida (não reabrir sem pedido)

Phosphor via CDN, `<select>` nativo e CSS inline em templates antigos, CSP sem nonce. (`z_Versoes/` e `*.db` ficam fora da imagem
de produção porque o `.gitignore` já os barra e o build parte do GitHub.) Tela nova não repete nada disso.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
