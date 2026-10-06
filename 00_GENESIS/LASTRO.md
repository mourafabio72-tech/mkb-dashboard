---
tipo: lastro
projeto: FinHub (_deploy_mkb)
gerado_em: 2026-10-05 20:10
metodo_descoberta: mapa + 5 batedores em paralelo (sonnet) + 1 batedor do código
---

# LASTRO do projeto `FinHub`

Notas que REGEM este projeto. Recarregar em toda retomada de sessão.

**O projeto é anterior ao padrão GENESIS.** Este 00_GENESIS cobre daqui para frente, a partir do
trabalho "Pergunte à IA" (aberto em 2026-10-05). O LOG.md já trazia o diário do cerco de segurança
de 08 e 09/2026; ele continua e não foi reescrito.

## Tipo e regime

- Tipo equivalente: **App WEB com login por perfil** (nota `04_Tipos_de_App/App_Online_Auth.md`),
  mas em **Flask + SQLite**, não Postgres. Decisão antiga do projeto, em produção, não se reabre.
- Regime: **WEB (segurança obrigatória)**.
- Acesso: perfis `admin` e `leitura` (tabela `usuarios`), mais SSO por cookie do Zoaria Hub com
  restrição por empresa (`auth.empresas_permitidas()`, `app._guard_empresa`).
- Visual: **Sage & Creme** (tema claro creme + oliva, com alternador escuro), decisão do dono
  unificada em todos os apps Zoaria. Não reabrir.

## Doutrinas (pétreas, universais)

- `00B_DOUTRINAS/Anti_Puxa_Saco.md` (189 linhas): verdade útil antes de agradável; erro em local, causa, correção.
- `00B_DOUTRINAS/Leitura_e_Retencao_de_Notas.md` (236 linhas): nota se lê inteira; LASTRO no chat; não citar o que não leu.

## Notas da vault que regem o trabalho "Pergunte à IA"

Caminhos relativos a `/Users/fabiomoura/ObsidianJovi/01_SISTEMAS/`.

### Processo
- `08_Processo_Dev/Brainstorming_Socratico_por_Tarefa.md`: perguntas feitas e respondidas em 2026-10-05.
- `07_Regras_de_Ouro/Escada_Preguica_de_Codigo.md`: reusar as funções do `dre_engine.py`; marcador `# escada:` em corte consciente; uma prova executável por lógica não trivial.
- `01_Padroes_Gerais/Padrao_CLAUDE_MD_Projeto.md`: o projeto não tinha CLAUDE.md (Fase 1).
- `01_Padroes_Gerais/Padrao_Graphify_Projeto_Novo.md`: mapa gerado em 2026-10-05 (469 nós, 1150 ligações).

### IA (o centro do trabalho)
- `01_Padroes_Gerais/Padrao_Marca_IA.md`: `ph-sparkle`, família roxa `#7C3AED`, `.bloco-ia`, `.btn-ia`, `.tag-ia`, texto descritivo.
- `07_Regras_de_Ouro/Sempre_Marcar_IA.md`: IA sempre roxa; exceção só para a tela técnica de configuração (corpo neutro, tag IA roxa).
- `02_Seguranca/Mapa_de_Conceitos_de_Seguranca.md` (seção "AI Security", linhas 485-499): prompt injection, insecure output handling. **A vault não tem `Padrao_AI_Security`**: este mapa é a referência.

### Segurança
- `02_Seguranca/Vazamento_de_Chaves.md`, `Revisao_Vulnerabilidades.md`, `Principios.md`
- `02_Seguranca/Padrao_Validacao_de_Input.md`, `Padrao_Mass_Assignment.md`, `Padrao_IDOR.md`
- `02_Seguranca/Padrao_Logging_Estruturado.md`, `CSRF_Cookies_Headers.md`, `Controle_de_IP.md`
- `02_Seguranca/Padrao_Dependencias_Lockfile.md`, `Padrao_Container_Seguro.md`

### Acesso
- `03_Auth_Perfis_Permissoes/Matriz_VER_EDITAR.md`, `Perfis_e_Modulos.md`, `Painel_Desenvolvedor.md`, `Admin_Inicial_Padrao.md`

### Tela
- `01_Padroes_Gerais/Padrao_Formulario.md`, `Acao_Primaria_a_Direita.md`, `Padrao_Box_Card.md`
- `01_Padroes_Gerais/Padrao_Toggle_Tipos.md` (tipo 2 escolhido), `Padrao_Loading_Estado.md`, `07_Regras_de_Ouro/Sempre_Mostrar_Loading.md`
- `01_Padroes_Gerais/Padrao_Tabela.md`, `Padrao_Cabecalho_da_Tabela.md`, `Padrao_Estado_Vazio.md`, `Padrao_KPI_Dashboard.md`, `07_Regras_de_Ouro/Listagens_sem_KPI.md`
- `01_Padroes_Gerais/Componente_SelectBusca.md`, `07_Regras_de_Ouro/Sem_Select_Nativo.md`
- `01_Padroes_Gerais/Padrao_Modal.md` + `Padrao_Modal_Nao_Fecha_Sozinho.md` (esta vence nos itens de fechar)
- `01_Padroes_Gerais/Sistema_de_Estilos.md`, `Icones_Phosphor.md`

### Língua
- `01_Padroes_Gerais/Padrao_Texto_e_Linguagem.md` (cópia lida no pacote do plugin, não existe na vault), `07_Regras_de_Ouro/Revisao_Professor_Pasquale.md`, `Portugues_BR_Acentuacao.md`, `Sem_Travessao.md`

## Decisões do dono (2026-10-05), regras locais que não vêm da vault

1. **Dois modos.** "Perguntar" (padrão): só a pergunta e a data de hoje vão para a IA, que devolve
   um filtro; o FinHub valida e calcula. "Analisar": vão os **totais agregados** do resultado (nunca
   lançamento individual, nunca histórico, nunca nome de pessoa física), com aviso na tela.
2. **Escopo das perguntas: tudo o que o app tem** (DRE, receita por cliente, despesa por fornecedor,
   folha, endividamento tributário e bancário, IRPJ/CSLL).
3. **Quem pergunta:** todo usuário logado, sempre dentro de `empresas_permitidas()`.
4. **Onde:** pílula "pergunte à IA" na barra de módulos (tela própria) **e** caixa no topo do dashboard.
5. **Toggle:** tipo 2, duas opções (Perguntar / Analisar; OpenAI / NVIDIA).
6. **Fornecedor:** a versão 1 responde pela **despesa de competência** e diz isso na tela. Pagamento de
   caixa ficou fora (ver PLANO, seção fora de escopo).
7. **Tela de chaves:** fica com o **admin** (conflito com `Painel_Desenvolvedor`, decidido pelo dono:
   o FinHub não tem perfil Desenvolvedor e o admin é ele).
8. **Guarda da chave:** a tela grava no volume, como hoje (`/data/openai_key.txt`) e como no Tareffas.
   Conflito com `Vazamento_de_Chaves`, decidido pelo dono. Compensação obrigatória: a chave **nunca**
   volta para o navegador (só mascarada `sk-...ab12`), nunca vai para log, o arquivo fica fora do git
   e da imagem, e a variável de ambiente, se existir, continua vencendo o arquivo.
9. **URL do provedor é fixa no código** (allowlist de duas URLs). Diferente do Tareffas, que deixa a
   URL editável: aqui não, para fechar SSRF.

10. **Cor de IA: teal da paleta, não roxo** (2026-10-06, Fábio: "a cor está fora da paleta de cores").
   Conflito com `Padrao_Marca_IA` ("Cor de IA é SEMPRE roxa") decidido pelo dono: vale o sinal de IA
   que a casa já usa na Conciliação Contábil, teal `#3A7D76` (fundo `#DCEFED`), tokens `--ia-*` em
   `static/style.css`. Continua valendo da nota: ícone `ph-sparkle`, cor exclusiva de IA (nunca o
   oliva `--accent`), texto descritivo, `.tag-ia` no resultado.

## Regras locais do projeto (quirks)

- Publica do branch **`master`**, não `main`.
- Python mínimo **3.11** (pandas 3.0.2); o Mac tem 3.9 no sistema: rodar com `uv run --python 3.12`.
- `Dockerfile` usa `COPY . .`: arquivo novo entra na imagem, mas tudo que o `.dockerignore` não barra também.
- Carimbo de versão em `GET /health` (`{"build":"AAAAMMDD-HHMM"}`).
- Provas: scripts em `provas/` com `DB_PATH` temporário apontado ANTES de importar `app`.
- Ajuste de saldo exige aprovação (nunca automático). Protheus lança retroativo.

## Conflitos vault x projeto (registrados, não resolvidos neste trabalho)

- Phosphor via CDN (jsdelivr); a vault pede self-host. Herança do app inteiro.
- `<select>` nativo em 9 templates antigos; a vault proíbe. **Tela nova não usa `<select>`.**
- CSS inline em templates antigos; a vault proíbe. **Tela nova não escreve `style=`.**
- Tokens: o FinHub usa `--primary`, `--accent`, `--card`, `--border`, `--text`, `--muted` (não `--cor-primaria`).
  Tela nova usa os tokens do FinHub; o roxo de IA entra como tokens `--roxo*` em `static/style.css`.

## Notas que NÃO regem (lidas e descartadas)

- `Padrao_Menu_Sidebar`, `Padrao_Sidebar_Rodape`: o FinHub não tem menu lateral.
- `Padrao_Modal_Popup_Centrado`: não haverá SelectBusca dentro de modal.
- `Padrao_Upload_Arquivo`: nada de arquivo neste trabalho.
- `Padrao_Toggle_OnOff`: nenhuma escolha é liga/desliga.
- `Padrao_Convite_de_Acesso`, `Auto_Liberacao_por_Grupo`, `Instrucao_Replicar_Sistema_Perfis`: o FinHub usa roles, não matriz de perfis.
- `Padrao_Impersonacao_Segura`, `Timeout_de_Sessao`, `Forca_Bruta_Login`, `Padrao_CI_CD_Seguro`: fora do escopo.
- `Padrao_Barra_de_Filtros`, `Padrao_Paginacao_Servidor`, `Padrao_Filtro_por_Coluna`: o resultado é limitado no servidor (ver CHECKLIST), não há barra de filtro na tela nova.
