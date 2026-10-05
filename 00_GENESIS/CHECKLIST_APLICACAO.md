---
tipo: checklist
projeto: FinHub (_deploy_mkb)
gerado_em: 2026-10-05 20:10
trabalho: Pergunte à IA
---

# Checklist de aplicação

Só marcar `[x]` com EVIDÊNCIA apontável (arquivo:linha ou saída de prova). Fonte da regra entre parênteses.

```
Cor de marca: tokens do FinHub (--primary, --accent, --card, --border, --text, --muted), tema Sage & Creme
Token de IA: --roxo #7C3AED, --roxo-escuro #6D28D9, --roxo-claro #A78BFA, --roxo-texto #5B21B6,
             --roxo-borda #C4B5FD, --roxo-pastel-1 #FAF5FF, --roxo-pastel-2 #EDE9FE, --roxo-suave #F3EEFF
Arquivo do token: static/style.css (bloco :root e [data-theme="light"])
PROIBIDO: hex de qualquer cor dentro de template
Tema: claro (padrão) e escuro, com o alternador que já existe
Acesso: perfil (admin / leitura) + SSO do Hub com escopo de empresa
Toggle: tipo 2, duas opções
```

---

## Fase 1: CLAUDE.md e higiene do mapa

- [x] `CLAUDE.md` na raiz, começando pelo bloco do template, com os caminhos do Mac: `/Users/fabiomoura/ObsidianJovi/CLAUDE.md` etc. (Padrao_CLAUDE_MD_Projeto)
      EVIDÊNCIA: CLAUDE.md:1-76 (bloco da vault, caminhos /Users/fabiomoura/ObsidianJovi/, _MAPA_CHAVES em 00A_MAPAS/); `head -5 CLAUDE.md` mostra o título e o aviso da vault
- [x] Seção "CONVENÇÕES ESPECÍFICAS": branch `master`, Python 3.11+ (`uv run --python 3.12`), `/health`, `COPY . .`, provas com `DB_PATH` antes do import, Sage & Creme, ajuste de saldo exige aprovação, Protheus retroativo, chave de IA no volume (decisão 8). (Padrao_CLAUDE_MD_Projeto: só o que é do projeto)
      EVIDÊNCIA: CLAUDE.md:77-135 (master, Python 3.11+/uv, /health, COPY . ., provas DB_PATH, Sage & Creme, ajuste com aprovação, Protheus retroativo, chave de IA no volume)
- [x] Nenhuma credencial no CLAUDE.md: `grep -niE "sk-|nvapi-|senha *[:=]" CLAUDE.md` vazio (Admin_Inicial_Padrao regra 5)
      EVIDÊNCIA: grep rc=1, vazio, ok
- [x] `graphify claude install` rodado DEPOIS do CLAUDE.md, bloco da vault preservado (Padrao_Graphify_Projeto_Novo, ordem item 4)
      EVIDÊNCIA: `diff <(head -135 CLAUDE.md) copia_antes` sem diferença; seção `## graphify` apensada em CLAUDE.md:136+; hooks em .claude/settings.json
- [x] `graphify-out/` em `.gitignore` e `.dockerignore`
      EVIDÊNCIA: `git check-ignore graphify-out` -> graphify-out; .gitignore:50, .dockerignore:13

## Fase 2: Configuração dos provedores

- [x] `ia_config.py`: env vence arquivo; arquivo em `Path(DB_PATH).parent` (prod `/data`) (decisão 8)
      EVIDÊNCIA: ia_config.py:ler_chave (env antes de `_dir_dados()/arquivo`), `_dir_dados()` = `Path(config.DB_PATH).parent`; prova seção 1 (6 OK)
- [x] Arquivos `openai_key.txt`, `nvidia_key.txt`, `ia_config.json` com permissão `0o600` ao gravar (decisão 8, compensação)
      EVIDÊNCIA: ia_config.py:_gravar_privado (mkstemp 0o600 + os.replace, atômico; trocado após verificação); prova seção 2: os três arquivos 0o600 e regravar reaperta
- [x] `PROVEDORES` com URL fixa: `https://api.openai.com/v1/chat/completions` e `https://integrate.api.nvidia.com/v1/chat/completions`; nenhum campo de URL (Mapa_de_Conceitos A10 SSRF: "Whitelist de domínios em requisição HTTP do servidor")
      EVIDÊNCIA: ia_config.py:PROVEDORES; prova seção 3 e 7b: allowlist = as duas URLs, redirect não seguido (mutação: sem _SemRedirect a prova fica VERMELHA), tela sem `name=...url`, chamada NVIDIA vai à URL fixa
- [x] Rotas `/config/ia*` com `@login_required` + `@admin_required` (Principios: "Toda rota que muda dado ou mostra dado privado exige login")
      EVIDÊNCIA: app.py:2198-2243, as três com @login_required + @admin_required; prova seção 4: sem sessão 302 /login, leitura barrada em GET, salvar e testar
- [x] Chave nunca volta ao navegador, só `mascarar(chave)` = 3 primeiros + `...` + 4 últimos (Revisao_Vulnerabilidades: "Nenhuma chave de API pode chegar ao navegador")
      PROVA: na prova, o HTML de `GET /config/ia` não contém a chave semeada
      EVIDÊNCIA: prova seção 5: HTML sem CHAVE_OA e CHAVE_NV, com `sk-...XYZ9`; estado_publico sem a chave; JSON do testar sem a chave (seção 7)
- [x] Campo de chave vazio ao salvar = mantém a atual (não apaga sem querer)
      EVIDÊNCIA: ia_config.salvar_chave devolve None com vazio; prova seção 6 'campo vazio mantém a chave'
- [x] Validação: chave OpenAI começa com `sk-`, NVIDIA com `nvapi-`, 20 a 200 caracteres, sem espaço; modelo até 80 caracteres em `[A-Za-z0-9._/:-]` (Padrao_Validacao_de_Input)
      EVIDÊNCIA: ia_config.py `_RE_CHAVE` {20,200} sem espaço + prefixo; `_RE_MODELO` [A-Za-z0-9._/:-]{1,80}; prova seção 6: prefixo errado, espaço, modelo com `;`, modelo 81, provedor desconhecido recusados
- [x] Erro do provedor genérico, sem `r.text` nem `str(e)` na resposta (Padrao_Logging_Estruturado: "Header Authorization ou Cookie brutos" nunca em log)
      EVIDÊNCIA: ia_config.chamar: 3 mensagens fixas (HTTP <código>, não consegui falar, resposta que não entendi), `from None`; prova seção 7 (401 com chave no corpo, OSError com chave, JSON torto). Irmão corrigido: app.py sugerir-ia trocou `str(e)` por mensagem fixa, 502 (prova seção 8). O único `str(e)` restante (ia_config.testar) é de ErroIA, texto montado por nós.
- [x] Nenhum log com chave ou cabeçalho: `grep -nE "log.*(key|chave|Authorization)" ia_config.py app.py` vazio
      EVIDÊNCIA: `grep -nE "log.*(key|chave|Authorization)" ia_config.py app.py` rc=1, vazio, ok
- [x] Nenhum pacote novo: chamada HTTP pela `urllib` (Padrao_Dependencias_Lockfile: "Eu realmente preciso disso, ou consigo com stdlib?"); `git diff requirements.txt` vazio. Item trocado em 2026-10-05 (era `httpx` pinado, premissa falsa)
      EVIDÊNCIA: `git diff --stat requirements.txt` vazio; `grep "import httpx|import requests" ia_config.py` rc=1; HTTP por urllib (ia_config._post_json)
- [x] `/cadastro/aliases/config-ia` grava via `ia_config.py`; sugestão de aliases continua funcionando (Escada degrau 2: reusar)
      EVIDÊNCIA: app.py aliases_config_ia usa ia_config.validar_chave/salvar_chave; sugerir-ia usa ia_config.ler_chave; config.py sem _ler_openai_key; prova seção 8: rota antiga grava 0o600, SDK recebe a chave, sugestão responde 200
- [x] `provas/prova_ia_config.py` verde, sem rede
      EVIDÊNCIA: `uv run --no-project --python 3.12 --with-requirements requirements.txt python provas/prova_ia_config.py` -> PROVA VERDE, rc=0 (70 checagens, depois da verificação adversarial); provas antigas 5/5 verdes

## Fase 3: Motor do modo Perguntar

- [x] Prompt de sistema separado da mensagem do usuário; pergunta entre `"""` no `user` (Mapa_de_Conceitos: "sempre system prompt separado do user input")
      EVIDÊNCIA: ia_perguntas.interpretar: messages[0] system = PROMPT_SISTEMA constante, pergunta só em messages[1] entre aspas triplas; prova seção 6
- [x] `response_format json_object` só para OpenAI; leitor de JSON tolera cerca de texto (NVIDIA)
      EVIDÊNCIA: ia_config.chamar só põe response_format para openai (prova_ia_config seção 3); ia_perguntas.ler_json usa JSONDecoder.raw_decode e devolve o 1º objeto válido (prova: dois objetos no texto); prova seção 5 'JSON cercado de texto é lido'
- [x] Timeout 30 s; exceção vira "Não consegui falar com a <provedor> agora."
      EVIDÊNCIA: interpretar(timeout=30); ErroIA 'Não consegui falar com a OpenAI agora.' -> 502; prova seção 5
- [x] Lista fechada `INTENCOES = {...}` com campos por intenção; campo fora da lista ignorado e listado em `ignorados` (Padrao_Mass_Assignment: "Tudo que veio no body e nao esta na whitelist eh ignorado")
      EVIDÊNCIA: ia_perguntas.INTENCOES (8 intenções); validar() exige str e lista fora da lista em `ignorados` (até 10); prova seção 3: empresa_id e sql ignorados, intencao lista/dict/número/None/bool -> Não entendi 200 (mutação sem isinstance: prova rc=1, TypeError)
- [x] `empresa` validada contra `empresas_permitidas()` DA SESSÃO; fora do escopo = recusa sem revelar dado (Padrao_IDOR)
      PROVA: sessão restrita a MKB perguntando da GNILEB recebe recusa
      EVIDÊNCIA: ia_perguntas._empresa (perm da sessão; consolidado só para quem vê todas); prova seção 2: sessão só MKB pedindo GNILEB e consolidado -> 404 recusa genérica (Padrao_IDOR), sem o 777 da Gnileb e sem nomear a empresa; empresa inventada vira Não entendi, não alerta
- [x] Competência `AAAA-MM` validada por regex + existência; janela máx. 24 meses com `# escada:` explicando o teto
      EVIDÊNCIA: _RE_COMP + `c in disponiveis`; MAX_MESES=24 com `# escada:` (ia_perguntas.py topo); prova seção 4
- [x] Textos livres (cliente, fornecedor) até 80 caracteres, só como parâmetro `?` ou comparação em Python; zero f-string com valor do filtro em SQL (Revisao_Vulnerabilidades: "Todo SQL usa parâmetros")
      PROVA: `grep -nE "execute\(f[\"']" ia_perguntas.py` vazio
      EVIDÊNCIA: _texto corta em 80, comparação em Python (_norm + `in`), nunca SQL; `grep -nE "execute\(f[\"']" ia_perguntas.py` rc=1; prova 3 e 9
- [x] Executor reusa `dre_engine` (`calcular_dre_mensal`, `calcular_dre_detalhada`, `analisar_receita_clientes`, `analisar_despesas_fornecedores`, `classificar_conta`) e `_resumo_endividamento_*` de `app.py` (Escada degrau 2)
      EVIDÊNCIA: ia_perguntas importa calcular_dre_mensal, calcular_dre_detalhada (folha), analisar_receita_clientes, analisar_despesas_fornecedores; zero SQL próprio de lançamento (classificar_conta entra via calcular_dre_detalhada); endividamento via app._resumo_endividamento_*; prova seção 1 confere ROB contra calcular_dre_mensal
- [x] Folha = `CPV_FOLHA + DADM_FOLHA + CPV_PROLAB + DADM_PROLAB + CPV_ENCARG + DADM_ENCARG`
      EVIDÊNCIA: GRUPOS_FOLHA com os 6 grupos; _folha soma os subtotais de calcular_dre_detalhada; prova semeia os 6 grupos: ago = -(6000+1000+100+200+300+400) = -8000, sinal da DRE
- [x] `despesa_fornecedor` responde com o rótulo "despesa de competência, não pagamento" (decisão 6)
      EVIDÊNCIA: aviso 'Despesa de competência (quando a nota foi lançada), não pagamento.'; prova seção 1
- [x] Tabela máx. 10 linhas + "Outros" + link "ver tudo" para a tela do módulo
      EVIDÊNCIA: _top (MAX_LINHAS=10 + 'Outros (n)'); ver_tudo por url_for do módulo; prova seção 1: 12 clientes -> 11 linhas, Outros = 3000
- [x] Frase "Entendi" montada do filtro VALIDADO
      EVIDÊNCIA: executar monta de f (LINHAS, NOME_EMPRESA, mes_label); prova: 'Entendi: Receita Operacional Bruta de MKB, em ago/2026.'
- [x] `POST /ia/perguntar`: `@login_required`, CSRF (o `fetch` do `base.html` já manda `X-CSRF-Token`), 300 caracteres, 409 sem chave
      EVIDÊNCIA: app.py:2276 @login_required; CSRF pelo before_request (prova: sem token 400); 300 caracteres (5000 -> 400); sem chave 409
- [x] Limite 20 por usuário a cada 10 min, 429 com mensagem "Muitas perguntas seguidas. Tente de novo em N min." (Mapa_de_Conceitos: "rate limit em endpoint de IA")
      EVIDÊNCIA: ia_perguntas.consumir (deque por usuário, trava, `# escada:` memória por processo); prova seção 8: 21ª -> 429 com a mensagem; outro usuário passa; janela de 600 s
- [x] Log `IA_PERGUNTA` com usuário, intenção, provedor, ms; SEM texto da pergunta (Padrao_Logging_Estruturado: "Conteúdo de mensagem privada do usuário" nunca)
      EVIDÊNCIA: app.ia_perguntar registrar IA_PERGUNTA (user_id, ip, provedor, intencao, tipo, ms); prova seção 7: texto da pergunta fora do log; recusa vira ACESSO_NEGADO_IDOR
- [x] `provas/prova_ia_perguntar.py` verde: as 8 intenções, escopo de empresa, campo extra, período gigante, pergunta de 5000 caracteres, IA fora do ar, JSON cercado de texto
      EVIDÊNCIA: rc=0, 0 FALHA; provas antigas e prova_ia_config verdes (rc=0 nas 7)

## Fase 4: Modo Analisar

- [x] Servidor recalcula; não aceita números do corpo da requisição (Padrao_Mass_Assignment)
      EVIDÊNCIA: app.ia_analisar só chama _ia_ler_pergunta (lê só `pergunta`); ia_perguntas.analisar chama responder() e monta o pacote do resultado recalculado; prova seção 2: linhas/total/valor do corpo (999999, 123456, 777777) não chegam à IA
- [x] Pacote para a IA só com rótulo, competência e valor; sem `historico`, `documento`, NF, linha de razão (decisão 1)
      PROVA: dublê captura o payload e a prova procura essas chaves
      EVIDÊNCIA: ia_perguntas.pacote_analise (itens só rotulo+valor; cliente/fornecedor viram 'Cliente n'); prova seção 1: sem historico, documento, DOC0, 'VL. NF', número da NF, razao, conta_cod, nome de cliente nem nome citado na pergunta
- [x] Prompt: "use só os números fornecidos", até 6 frases, português
      EVIDÊNCIA: PROMPT_ANALISE: 'Use SOMENTE os números', 'Não invente número', 'no máximo 6 frases', 'português do Brasil'; prova seção 3
- [x] Texto volta puro; front usa `textContent` (Mapa_de_Conceitos: "nunca `| safe` em output de LLM")
      PROVA: `grep -rnE "\| *safe|innerHTML" templates/ia.html static/ia.js` vazio
      METADE BACKEND: `resp['analise']` é string pura, espaços colapsados, até 1500 (prova seção 3). METADE FRONT: grep em templates/ia.html e static/ia.js roda no gate da Fase 5, e só então este item vira [x].
      EVIDÊNCIA FRONT (Fase 5): grep `| *safe|innerHTML` em templates/ia.html e static/ia.js só acha o comentário da linha 3 do ia.js, que proíbe innerHTML; todo texto entra por textContent (el(), clonar())
- [x] Balde de limite compartilhado com Perguntar
      EVIDÊNCIA: as duas rotas passam por _ia_ler_pergunta -> ia_perguntas.consumir(_ia_quem()); prova seção 6: 19 perguntar + 1 analisar = 20 ok, a 21ª (analisar) 429
- [x] `provas/prova_ia_analisar.py` verde
      EVIDÊNCIA: rc=0, PROVA VERDE

## Fase 5: Telas

### Marca de IA
- [x] Todo elemento de IA (pílula, caixa do dashboard, botão, frase Entendi, texto do Analisar) usa `ph-sparkle` e tokens `--roxo*` (Padrao_Marca_IA: "Nunca usar laranja, azul ou cor da empresa em botão/bloco/badge de IA")
      PROIBIDO: `ph-robot`, `ph-magic-wand`, `ph-star`, emoji
      EVIDÊNCIA: pílula (dashboard.html, ícone ph-sparkle, cor var(--roxo)), caixa .bloco-ia, .btn-ia, .tag-ia na frase Entendi e na análise; grep ph-robot|ph-magic-wand|ph-star em templates/ rc=1. Conferência visual pendente com o Fábio
- [x] `.bloco-ia`: `background: linear-gradient(135deg, var(--roxo-pastel-1), var(--roxo-pastel-2)); border: 1px solid var(--roxo-borda)` no claro; no escuro, `var(--card)` com borda `var(--roxo-claro)` (a nota não define escuro, decisão registrada aqui)
      EVIDÊNCIA: style.css bloco PERGUNTE À IA: --ia-fundo = gradiente pastel-1/pastel-2 no claro e var(--card2) no escuro; borda --ia-borda (roxo-borda no claro, roxo-claro no escuro)
- [x] `.btn-ia`: fundo `var(--roxo)`, hover `var(--roxo-escuro)`, `:disabled` `var(--roxo-claro)` + `cursor: wait`
      EVIDÊNCIA: style.css .btn-ia background var(--roxo), :hover var(--roxo-escuro), :disabled var(--roxo-claro) + cursor wait
- [x] `.tag-ia`: `<span class="tag-ia"><i class="ph ph-sparkle" aria-hidden="true"></i> IA</span>` antes da frase Entendi e do texto do Analisar (Padrao_Marca_IA: "Resultado gerado por IA marcado com `.tag-ia`")
      EVIDÊNCIA: ia.html moldes Resultado e Vazio com <span class="tag-ia"><i class="ph ph-sparkle" aria-hidden="true"></i> IA</span>; análise com tag 'Análise da IA'
- [x] Botão com `aria-label` descritivo e ícone `aria-hidden="true"`
      EVIDÊNCIA: ia.html e dashboard.html: aria-label="Perguntar à inteligência artificial", ícones aria-hidden
- [x] Texto descritivo junto do botão: "A IA lê sua pergunta e diz ao FinHub o que buscar. Os números vêm do FinHub." (Sempre_Marcar_IA: "A IA vai ler X e te entregar Y")
      EVIDÊNCIA: ia.html e dashboard.html: 'A IA lê sua pergunta e diz ao FinHub o que buscar. Os números vêm do FinHub.'
- [x] Tela `/config/ia`: corpo neutro, tag IA roxa no título (Sempre_Marcar_IA, exceção única)
      EVIDÊNCIA: config_ia.html: cards .ia-config-card em var(--card2), botões .btn-neutro/.btn-acao; só a .tag-ia do título é roxa (print de 2026-10-05 22:5x)

### Toggle tipo 2
- [x] `.ia-fonte{display:inline-flex;align-items:stretch;border:1px solid var(--border);border-radius:7px;overflow:hidden}`; `.ia-fonte button.on` com fundo sólido (`var(--roxo)` na tela de IA, `var(--accent)` na config) e texto branco (Padrao_Toggle_Tipos tipo 2)
      EVIDÊNCIA: style.css .ia-fonte inline-flex/stretch/borda/7px/overflow hidden; .on sólido var(--roxo) na tela de IA e var(--ia-neutro-on) (primary no claro) na config, texto var(--roxo-contraste). Desvio: na config o ativo é --primary e não --accent, porque branco sobre --accent dava 4,3:1 (conferir-telas)
- [x] Wrapper `role="radiogroup"` + `aria-label`; botões `type="button"`; ícone Phosphor em cada opção
      PROIBIDO: sublinhado de aba, verde, `<select>`
      EVIDÊNCIA: grep role=radiogroup: 1 em ia.html, 1 em config_ia.html; botões type=button role=radio com aria-checked; ícone ph em cada opção

### Formulário, botão, card
- [x] Campos e botão com `height:40px; box-sizing:border-box`; label 13px 600 sem uppercase (Padrao_Formulario)
      EVIDÊNCIA: medido no navegador: campo, botão, toggle, inputs e botões da config = 40px; label 13px 600 none
- [x] Botão principal ancorado à direita pelo CSS do container (`margin-left:auto` na classe, nunca em `style=`) (Acao_Primaria_a_Direita)
      EVIDÊNCIA: style.css .ia-form .campo-acao{margin-left:auto}; .ia-config-rodape e .ia-config-acoes justify-content flex-end (corrigido após print: mensagem longa empurrava o Testar); grep style= float/margin nas telas novas rc=1
- [x] Cards com `display:flex; flex-direction:column`, cabeçalho `space-between`, sem hover mudando `background` (Padrao_Box_Card)
      EVIDÊNCIA: style.css .ia-card, .ia-config-card flex column; .ia-card-cab e .ia-config-cab space-between; grep hover com background em ia- rc=1
- [x] Nenhum `<select>` nas telas novas: `grep -n "<select" templates/ia.html templates/config_ia.html` vazio (Sem_Select_Nativo)
      EVIDÊNCIA: grep <select em ia.html e config_ia.html rc=1
- [x] Nenhum `style=` nem hex nas telas novas: `grep -nE 'style="|#[0-9a-fA-F]{3,6}' templates/ia.html templates/config_ia.html` vazio (Sistema_de_Estilos)
      EVIDÊNCIA: grep style=|<style|#hex em ia.html e config_ia.html rc=1

### Loading, vazio, tabela
- [x] Loading inline no container do resultado, spinner com borda `var(--roxo)`, texto no gerúndio; mais de 10 s mostra `.loading-sub` com segundos (Padrao_Loading_Estado)
      PROIBIDO: "Carregando...", "Aguarde...", "Processando..."
      EVIDÊNCIA: molde iaMoldeLoading em #iaResultado: spinner border-top var(--roxo), texto 'Lendo sua pergunta...' > 'Somando os lançamentos...' > 'Escrevendo a análise dos totais...', .loading-sub com segundos a partir de 10 s (ia.js)
- [x] Botão `disabled` durante a chamada; `finally` reabilita (Padrao_Loading_Estado regras 6 e 7)
      EVIDÊNCIA: ia.js enviar(): botao.disabled = true; .finally reabilita e limpa o relógio; grep -c finally ia.js = 2. Texto do botão não muda: Padrao_Loading_Estado proíbe loading dentro do botão
- [x] Resultado vazio: `.vz` com `ph-funnel-x`, título "Nenhum Resultado", sub "Nenhum lançamento atende à pergunta." (Padrao_Estado_Vazio)
      EVIDÊNCIA: molde iaMoldeVazio: .vz com ph-funnel-x, 'Nenhum Resultado', sub com ponto; medido no navegador: 'Nenhum Resultado | Não há lançamentos importados nesse período.'
- [x] Tabela de resultado: título dentro do card, contagem no cabeçalho ("7 clientes"), valores `tabular-nums`, até 10 linhas (Padrao_Cabecalho_da_Tabela; Padrao_Tabela regra 1 não dispara)
      EVIDÊNCIA: título e contagem no cabeçalho do card ('12 clientes, 10 maiores'), th uppercase 11.5/700, .ia-num tabular-nums, até 10 + Outros + Total (medido: 12 linhas no tbody)
- [x] Número único no modo Perguntar não vira grade de KPI (Listagens_sem_KPI)
      EVIDÊNCIA: tipo numero vira um bloco só (.ia-numero), sem grade de KPI

### Telas e entrada
- [x] Dict novo em `itens` de `templates/dashboard.html` (endpoint `ia_tela`, ícone `ph-sparkle`, rótulo `pergunte à IA`)
      EVIDÊNCIA: dashboard.html: endpoint ia_tela, ícone ph-sparkle, label 'pergunte à IA'
- [x] Caixa no topo do dashboard, `.bloco-ia`, `GET /ia?q=`
      EVIDÊNCIA: dashboard.html: form GET url_for('ia_tela') .bloco-ia acima do filtro de período; no navegador a pergunta foi para /ia?q=... e rodou sozinha
- [x] Link para `/config/ia` em Cadastro, só para admin
      EVIDÊNCIA: cadastro.html: card Configuração da IA (a rota /cadastro já é @admin_required)
- [x] Exemplos clicáveis: "quanto a MKB faturou em agosto?", "salários de julho contra agosto", "despesa com o fornecedor X neste ano", "qual o saldo do endividamento tributário?"
      EVIDÊNCIA: ia.html: os 4 exemplos do plano como .ia-exemplo; ia.js preenche e envia

### Língua e conferência
- [x] Zero travessão nos arquivos novos: `grep -rn "—" templates/ia.html templates/config_ia.html static/ia.js ia_config.py ia_perguntas.py` vazio (Sem_Travessao)
      EVIDÊNCIA: grep — em ia_config.py ia_perguntas.py ia.html config_ia.html ia.js rc=1
- [x] Acentuação completa em todo texto visível; identificadores sem acento (Portugues_BR_Acentuacao); leitura tela por tela registrada no LOG (Revisao_Professor_Pasquale, fallback sem script)
      EVIDÊNCIA: grep -w de palavras sem acento nos arquivos novos rc=1; mojibake rc=1; file = UTF-8; leitura tela por tela registrada no LOG (pasquale.py não existe na vault: fallback da nota)
- [x] Vocabulário: `grep -rniE "processando|aguarde|carregando|vale ressaltar|em suma" templates/ia.html templates/config_ia.html static/ia.js` vazio (Padrao_Texto_e_Linguagem)
      EVIDÊNCIA: grep processando|aguarde|carregando|vale ressaltar|em suma|outrossim|prezado nos arquivos novos rc=1
- [ ] `conferir-telas` em `/ia`, `/config/ia` e `/`, computador e celular, claro e escuro: zero erro

## Fase 6: Entrega

- [ ] Provas novas e antigas verdes (saída colada no LOG)
- [ ] Teste real no Mac: 1 pergunta OpenAI + 1 NVIDIA conferidas contra a tela do módulo
- [ ] `graphify update .`
- [ ] Um commit por fase no `master`; push
- [ ] `curl -s https://dre.zoaria.com.br/health` com o carimbo do último commit
- [ ] `curl -s -o /dev/null -w "%{http_code}" https://dre.zoaria.com.br/static/ia.js` = 200
- [ ] Aviso ao Fábio: salvar a chave NVIDIA em `/config/ia` na produção
- [ ] LOG `fase=6 acao=entrega resultado=ok`

---

## Itens fora do escopo

Ver PLANO_FASEADO, seção "Fora de escopo (cortado pela escada)".
