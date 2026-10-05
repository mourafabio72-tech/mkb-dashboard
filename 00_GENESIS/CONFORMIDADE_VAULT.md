# CONFORMIDADE_VAULT

Projeto: `FinHub (_deploy_mkb)`, trabalho "Pergunte à IA"
Criado em: `2026-10-05`

Uma linha por REGRA da vault. `Status` só vira `ok` com a saída real do comando colada em `Evidência`,
ou com `conferência visual feita em <data>, tela <qual>`. **Fase de tela não fecha com linha pendente.**

Arquivos novos deste trabalho (alvo dos comandos): `ia_config.py`, `ia_perguntas.py`,
`templates/ia.html`, `templates/config_ia.html`, `static/ia.js`, trechos novos de `app.py` e `static/style.css`.

## Decisões cravadas na abertura

```
Token de cor: tokens do FinHub (--primary, --accent, --card, --border, --text, --muted); IA em --roxo*
Arquivo do token: static/style.css
Valor inicial IA: --roxo #7C3AED (família de Padrao_Marca_IA)
Tema: claro e escuro, com alternador (já existe)
Estilo de toggle escolhido: duas opções (tipo 2)
PROIBIDO: hex em qualquer template
```

## Matriz

| Nota | Regra literal | Proibido | Onde aplica | Prova | Evidência | Status |
|---|---|---|---|---|---|---|
| Mapa_de_Conceitos (AI Security) | "sempre system prompt separado do user input" | pergunta concatenada no prompt de sistema | `ia_perguntas.py` | `grep -n "role.*system" ia_perguntas.py` mostra conteúdo constante; prova inspeciona o payload | | pendente |
| Mapa_de_Conceitos (AI Security) | "nunca `\| safe` em output de LLM" | `{{ resposta \| safe }}`, `innerHTML = texto` | `ia.html`, `ia.js` | `grep -rnE "\| *safe\|innerHTML" templates/ia.html static/ia.js` vazio | | pendente |
| Mapa_de_Conceitos (AI Security) | "nunca concatenar output de LLM em SQL" | `execute(f"...{filtro[...]}")` | `ia_perguntas.py` | `grep -nE "execute\(f[\"']\|\.format\(" ia_perguntas.py` vazio | | pendente |
| Mapa_de_Conceitos (AI Security) | "rate limit em endpoint de IA" | `/ia/perguntar` sem limite | rotas `/ia/*` | prova: 21ª chamada em 10 min leva 429 | | pendente |
| Mapa_de_Conceitos (A10) | "Whitelist de domínios em requisição HTTP do servidor" | campo de URL do provedor na tela | `ia_config.py`, `config_ia.html` | `grep -n "url" templates/config_ia.html` sem input de URL | | pendente |
| Vazamento_de_Chaves | "NUNCA no código-fonte, NUNCA no template, NUNCA no JS do front-end" | chave em `value=` do input | `/config/ia` | prova: HTML não contém a chave semeada; `grep -rnE "sk-[A-Za-z0-9]{20,}\|nvapi-[A-Za-z0-9]{10,}" .` vazio | | pendente |
| Revisao_Vulnerabilidades | "Nenhuma chave de API pode chegar ao navegador" | JSON de `/config/ia` com chave inteira | rotas config | prova: resposta JSON só com `sk-...ab12` | | pendente |
| Padrao_Validacao_de_Input | "Toda string crua passa por validação tipada antes de tocar regra de negócio" | filtro da IA usado sem checar tipo | `ia_perguntas.validar` | prova: data inválida, período de 10 anos, 5000 caracteres levam 400 ou corte, nunca 500 | | pendente |
| Padrao_Mass_Assignment | "Tudo que veio no body e nao esta na whitelist eh ignorado" | `**filtro`, `setattr` com chave da IA | `ia_perguntas.py` | `grep -nE "\*\*filtro\|setattr\(" ia_perguntas.py` vazio; prova com `empresa_id` extra | | pendente |
| Padrao_IDOR | validar direito ao recurso ANTES de devolver dado | empresa vinda do filtro sem checar `empresas_permitidas()` | `/ia/perguntar`, `/ia/analisar` | prova: sessão MKB pergunta GNILEB e recebe recusa | | pendente |
| Padrao_Logging_Estruturado | "Senha, token e PII NUNCA entram em log" | log da pergunta, da resposta, do header | rotas `/ia/*`, `ia_config.py` | `grep -nE "log.*(pergunta\|resposta\|key\|Authorization)" app.py ia_config.py ia_perguntas.py` vazio | | pendente |
| CSRF_Cookies_Headers | "validado em todo POST/PUT/PATCH/DELETE" | rota `/ia/*` em `CSRF_ISENTAS` | rotas novas | prova: POST sem token leva 400 | | pendente |
| Padrao_Dependencias_Lockfile | "Versao de dependencia eh pinada" | `httpx` sem versão | `requirements.txt` | `grep -n "^httpx==" requirements.txt` acha 1 linha | | pendente |
| Principios | "Toda rota que muda dado ou mostra dado privado exige login" | rota `/ia` sem `@login_required` | rotas novas | prova: sem sessão leva 302 para o login | | pendente |
| Painel_Desenvolvedor | chaves de API no grupo Desenvolvedor | (decisão do dono: fica com admin) | `/config/ia` | `grep -n -A3 "config/ia" app.py` mostra `@admin_required` | | pendente |
| Padrao_Marca_IA | "ícone Phosphor `ph-sparkle` e paleta roxa exclusiva (`#7C3AED` família)" | `ph-robot`, `ph-magic-wand`, botão de IA oliva | telas novas, pílula, caixa | `grep -rnE "ph-robot\|ph-magic-wand\|ph-star" templates/` vazio; CONFERENCIA_VISUAL | | pendente |
| Padrao_Marca_IA | "Resultado gerado por IA marcado com `.tag-ia`" | frase Entendi ou texto do Analisar sem tag | `ia.html`, `ia.js` | `grep -c "tag-ia" templates/ia.html static/ia.js` > 0; CONFERENCIA_VISUAL | | pendente |
| Sempre_Marcar_IA | texto descritivo "A IA vai ler X e te entregar Y" | botão "Gerar com IA" sozinho | `ia.html`, caixa do dashboard | CONFERENCIA_VISUAL | | pendente |
| Padrao_Toggle_Tipos | tipo 2: `button.on` com fundo sólido, `role="radiogroup"`, ícone em cada opção | sublinhado, verde, `<select>` | Perguntar/Analisar, OpenAI/NVIDIA | `grep -c 'role="radiogroup"' templates/ia.html templates/config_ia.html` >= 1 cada; CONFERENCIA_VISUAL | | pendente |
| Padrao_Formulario | controles com `height:40px`, label 13px 600 sem uppercase | 36px, 38px, label uppercase | caixa de pergunta, config | no navegador `getComputedStyle(campo).height === '40px'` | | pendente |
| Acao_Primaria_a_Direita | "A âncora mora no CSS do container, nunca em `style=` no botão" | `style="margin-left:auto"`, `float:right` | botões Perguntar, Salvar, Testar | `grep -nE 'style="[^"]*(float\|margin-left)' templates/ia.html templates/config_ia.html` vazio; CONFERENCIA_VISUAL | | pendente |
| Padrao_Box_Card | card `display:flex;flex-direction:column`; "NUNCA mudar `background` no hover" | `.x:hover{background:...}` | cards novos | `grep -nE "ia-[a-z-]*:hover[^{]*\{[^}]*background" static/style.css` vazio | | pendente |
| Padrao_Loading_Estado | spinner com texto específico no gerúndio, `finally` limpa | "Carregando...", "Processando...", loading sem finally | `ia.js` | `grep -niE "carregando\|aguarde\|processando" static/ia.js` vazio; `grep -c "finally" static/ia.js` >= 1 | | pendente |
| Padrao_Estado_Vazio | `.vz` com ícone, "Nenhum Resultado" + sub com ponto | cabeçalho de tabela sem linha | resultado vazio | prova de front + CONFERENCIA_VISUAL | | pendente |
| Padrao_Tabela | regra 1: tabela com mais de 10 linhas ganha o menu | tabela de resultado com mais de 10 linhas sem menu | resultado tipo tabela | prova: executor nunca devolve mais de 11 linhas (10 + Outros) | | pendente |
| Sem_Select_Nativo | "nunca `<select>` nativo" | `<select>` | telas novas | `grep -n "<select" templates/ia.html templates/config_ia.html` vazio | | pendente |
| Sistema_de_Estilos | "Nenhuma tela escreve CSS inline ou `<style>` próprio" | `style="`, `<style>`, hex em template | telas novas | `grep -nE 'style="\|<style\|#[0-9a-fA-F]{3,6}' templates/ia.html templates/config_ia.html` vazio | | pendente |
| Icones_Phosphor | "Nada de emoji em UI"; tamanho via CSS | emoji, `style="font-size` em `<i>` | telas novas | `grep -n 'style="font-size' templates/ia.html templates/config_ia.html` vazio; CONFERENCIA_VISUAL | | pendente |
| Sem_Travessao | "Nunca usar o caractere travessão" | `—` | arquivos novos | `grep -rn "—" ia_config.py ia_perguntas.py templates/ia.html templates/config_ia.html static/ia.js` vazio | | pendente |
| Portugues_BR_Acentuacao | acentuação completa em todo texto visível | "Relatorio", "Configuracao", "Nao" em tela | telas novas, mensagens de erro | leitura tela por tela + `grep -nwE "Nao\|Configuracao\|Relatorio\|Analise" templates/ia.html templates/config_ia.html static/ia.js` vazio | | pendente |
| Padrao_Texto_e_Linguagem | verbo + objeto no botão; erro diz o que fazer | "OK", "Erro 500", "Submissão" | telas novas | CONFERENCIA_VISUAL | | pendente |
| Padrao_CLAUDE_MD_Projeto | projeto DEVE ter CLAUDE.md com o bloco da vault no topo | projeto sem CLAUDE.md | raiz | `head -5 CLAUDE.md` mostra o título e o aviso da vault | `# FinHub (MKB-Dashboard)` + `> Antes de TUDO: existe uma **vault Obsidian** em /Users/fabiomoura/ObsidianJovi/` (2026-10-05) | ok |
