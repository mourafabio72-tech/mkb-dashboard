---
tipo: lastro
projeto: FinHub (_deploy_mkb), trabalho "Orçamento: Orçado x Realizado"
gerado_em: 2026-10-20
metodo_descoberta: mapa + batedores em paralelo (sonnet) + medição em dado real
---

# LASTRO do trabalho Orçamento (FinHub)

O trabalho anterior (Pergunte à IA) fechou em 2026-10-05; o histórico dele está em
`checkpoint 20261005 222736.zip`. Este LASTRO cobre só o módulo de Orçamento.

## Tipo e regime

- Tipo: **Página WEB com SQLite** (`01_SISTEMAS/04_Tipos_de_App/Pagina_Web_SQLite.md`), app em produção
  em `dre.zoaria.com.br`, login pelo SSO do Hub mais sessão local, duas empresas isoladas (MKB, Gnileb).
- Regime: **WEB (segurança obrigatória)**.
- Stack travada: Flask + SQLite + Jinja + HTML/CSS/JS puro. Um worker. Nada de framework novo.
- Publica do branch **master**. `Dockerfile` usa `COPY . .`; `provas/`, `00_GENESIS/` e `*.db` ficam fora pelo `.dockerignore`.

## Doutrinas (ler integral em toda retomada)

- `00B_DOUTRINAS/Anti_Puxa_Saco.md`: verdade útil antes de tom agradável; erro em local, causa, correção.
- `00B_DOUTRINAS/Leitura_e_Retencao_de_Notas.md`: nota se lê integral; citar só o que foi lido na sessão; LASTRO com N de linhas e `fim:`.

## Notas de padrão que regem (fichas em NOTAS_LIDAS.md)

- Padrao_Validacao_de_Input, Padrao_IDOR, Padrao_Mass_Assignment, CSRF_Cookies_Headers, Padrao_Logging_Estruturado,
  Principios, Revisao_Vulnerabilidades, Padrao_Dependencias_Lockfile: upload e gravação do orçamento.
- Importacao_Externa_Pergunta_Estrategia: arquivo do Protheus exige decidir leitor fixo (B) ou mapeamento (A).
- Padrao_Upload_Arquivo, Padrao_Excel_Template_Importacao (só se o Fábio escolher modelo preenchido à mão).
- Padrao_Tabela, Padrao_Cabecalho_da_Tabela, Padrao_Filtro_por_Coluna, Padrao_Barra_de_Filtros, Padrao_KPI_Dashboard,
  Componente_SelectBusca, Padrao_Toggle_Tipos, Padrao_Loading_Estado, Padrao_Box_Card, Sem_Popup_Nativo,
  Padrao_Acao_Primaria_na_Topbar, Verificacoes_Mecanicas_de_Tela: as duas telas novas.
- Sistema_de_Estilos, Icones_Phosphor: cor só por token, ícone Phosphor.
- Escada_Preguica_de_Codigo, Paralelismo_e_Subagentes, Brainstorming_Socratico_por_Tarefa: processo.

## Decisões cravadas (do projeto, não da vault)

- **Token de cor:** os do FinHub (`--primary`, `--accent`, `--card`, `--border`, `--text`, `--muted`) em `static/style.css`.
  Onde a nota da vault diz `--cor-primaria`, `--borda` ou `--branco`, usa o equivalente do FinHub. PROIBIDO hex em template novo.
- **Menu:** o FinHub não tem menu lateral; tem navbar no topo e o hub de cards do `dashboard.html`. A entrada do módulo é
  um card novo no hub. `Padrao_Menu_Sidebar` não se aplica (herança "não reabrir" do CLAUDE.md do projeto).
- **Herança mantida:** Phosphor por CDN no `base.html`, `<select>` nativo e CSS inline das telas antigas. Tela nova não repete.
- **SelectBusca não existe no FinHub:** nasce neste trabalho (`static/selectbusca.js`), usado só nas telas novas.
- **Perfis:** o FinHub só tem `admin` e `leitura`. Importar = `@admin_required`; ver = `@login_required`. Empresa sempre
  por `_guard_empresa` / `empresas_permitidas()`; empresa vinda em POST é validada à mão.
- **Casamento orçado x realizado:** chave conta contábil + centro de custo + mês, a mesma do Protheus (decisão do Fábio,
  2026-10-20). Medido em maio/2026 da MKB: casa 100% com duas normalizações e sem de-para:
  conta sem espaço no fim (`'3.1.3.01.02.001     '` vira `'3.1.3.01.02.001'`) e centro sem ponto
  (`01.02.069.11` no razão vira `010206911`, formato do orçamento).
- **Realizado:** sai da tabela `razao` do FinHub (tem `centro_custo`), não da `v_lancamentos` (que soma e perde o centro).
  Mês sem razão importado não tem realizado por centro: a tela avisa, não inventa.
- **Origem do código:** do `app-contabil-com-ia` só se aproveita, como referência reescrita, o que é do Fábio
  (Trabalho 2: leitura do Rel_OrcRel, `abrir_por`, filtros). O motor de DRE de lá (`construir_dre`, `calcular`) é da base
  do Joviano, de licença restrita, e **não entra**. Aqui o motor é o `dre_engine` do próprio FinHub.
- **IA:** o módulo não usa IA. `Padrao_Marca_IA` não se aplica.

## Notas que NÃO regem

- Padrao_Menu_Sidebar: o FinHub usa navbar no topo (herança).
- Forca_Bruta_Login, Admin_Inicial_Padrao, Padrao_Convite_de_Acesso: o login já existe e não é tocado.
- Padrao_Impersonacao_Segura, Padrao_CI_CD_Seguro, Padrao_Container_Seguro: o módulo não toca nisso.
- Perfis_e_Modulos / Matriz_VER_EDITAR: o FinHub não tem tabela `modulos`; a granularidade é admin/leitura (herança).
- 70_ESTILO e Padrao_Texto_e_Linguagem: não encontradas na vault (procurado por nome e grep em toda a vault).

## Graphify

Mapa atualizado em 2026-10-20 (`graphify update .`). Depois de mexer no código: `graphify update .`.

## Skills de UI

`ui-ux-pro-max` e `frontend-design` não estão instaladas nesta máquina. As telas usam `z-design` e `conferir-telas`
(nossas, dentro do Sage & Creme) no lugar delas.
