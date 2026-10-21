---
tipo: checklist
projeto: FinHub, trabalho Orçamento
gerado_em: 2026-10-20
---

# CHECKLIST: Orçamento (Orçado x Realizado)

```
Token de cor: os do FinHub (--primary, --accent, --card, --border, --text, --muted), em static/style.css
Cor de marca: Sage & Creme do FinHub (nunca escrita em template novo)
Tema: ambos, com o alternador que o FinHub já tem
Acesso: SSO do Hub + sessão local; admin importa, leitura só vê; empresa por empresas_permitidas()
PROVA de cor: grep -rniE "#[0-9a-f]{3,6}\b" templates/orcamento*.html volta vazio
```

Só marcar `[x]` com evidência apontável (arquivo:linha ou saída de prova).

## Fase 0
- [x] D1 a D4 respondidos e plano aprovado, linha no LOG (LOG 2026-10-20 plano_aprovado: 1a, 2b, 3a, 4a; reaprovado com 2c, D5 e D6 na linha seguinte)

## Fase 1: base e leitor
- [x] tabelas `orcamento`, `centros_custo`, `orcamento_lotes` criadas no boot, sem quebrar banco existente (prova sobe `criar_schema` duas vezes)
  EVIDENCIA: schema.sql:297-334 (CREATE TABLE IF NOT EXISTS das 3, UNIQUE empresa+competência+conta+centro em :320, índice empresa+competência); entram pelo criar_schema que já roda o schema.sql no boot. provas/prova_orcamento_leitor.py passo 1: criar_schema duas vezes no mesmo banco, as 3 tabelas existem, a UNIQUE barra a chave repetida e aceita a mesma chave em outra empresa
- [x] SQL só com `?` e tupla. PROIBIDO `execute(f"`. PROVA: `grep -n 'execute(f' orcamento_*.py` vazio (Pagina_Web_SQLite)
  EVIDENCIA: `grep -n 'execute(f' orcamento_*.py` vazio. O leitor não fala com o banco: a gravação entra na Fase 2, e o grep se refaz lá
- [x] colunas gravadas por whitelist fixa no código. PROIBIDO montar INSERT com os cabeçalhos da planilha. PROVA: `grep -n "join(.*columns" orcamento_*.py` vazio (Padrao_Mass_Assignment)
  EVIDENCIA: grep vazio. orcamento_parser.py:27 COLUNAS fixa os campos por aba e só eles são lidos (_cabecalho :163 acha a coluna pelo nome; coluna fora da lista é ignorada, prova passo 2 com DEBITO, CREDITO e ANO presentes e ignorados)
- [x] conta sem espaço no fim, centro sem ponto, sinal crédito menos débito (decisão LASTRO, medida em 2026-10-20)
  EVIDENCIA: orcamento_parser.py:74 normalizar_conta, :78 normalizar_centro (float inteiro vira o número sem '.0') (CTT e DADOS); sinal mantido como vem (o relatório já traz crédito menos débito: dedução negativa na amostra real). Prova passo 2: '3.1.1.01.01.001   ' e '01.02.069.11' viram a chave certa, -87,57 fica negativo. Mutação sem o replace do ponto: prova cai (exit 1), revertida
- [x] linha com conta ou centro vazio, mês fora de 1 a 12 ou valor não numérico vira erro com número da linha (Padrao_Validacao_de_Input)
  EVIDENCIA: orcamento_parser.py:243 conta vazia, :247 centro vazio, :249 centro fora da CTT, :122 _mes (extenso, inteiro de 1 a 12 ou texto só com dígitos), :100 _valor (formato numérico por regex, Decimal finito, até 9.999.999.999), :258 tipo desconhecido; :146 _iterar transforma erro do openpyxl no meio da leitura em ValueError com a aba; :218 reset_dimensions (a tag dimension não corta linhas); erros juntos até MAX_ERROS (:47) com o total contado. Prova passo 3: 7 linhas ruins = ErroOrcamento total 7, cada uma com 'DADOS, linha N'. Mais: ano fora de 2000 a 2100, texto e bool recusados; .exe renomeado recusado por conferir_xlsx (:86), chamado também dentro do ler_orcamento
- [x] `provas/prova_orcamento_leitor.py` verde, planilha sintética gerada na prova (Escada: uma checagem executável)
  EVIDENCIA: `uv run --python 3.12 --with-requirements requirements.txt python provas/prova_orcamento_leitor.py` = 43 ok, 'tudo ok', exit 0 (inclui os 13 casos dos furos achados pelo verificador e o limite de valor e o centro inválido na CTT). Planilha gerada no tempdir da prova com dados inventados
- [x] leitor no Rel_OrcRel real dá 45.335 linhas de orçado
  EVIDENCIA: `python orcamento_parser.py ~/Downloads/Rel_OrcRel_2026.xlsx 2026` = linhas_orcado 45335, chaves_orcado 45335 (nenhuma chave repetida), 394 centros, 12 meses, chaves_realizado 32486, em ~2 s. Só contagens na saída

## Fase 2: importar
- [x] rota com `@login_required` + `@admin_required`, nessa ordem, como `/ingest` (app.py)
  EVIDENCIA: orcamento_rotas.py:152-154, :159-161 e :176-178 (as 3 rotas, nessa ordem); blueprint em app.py:4026. Prova passos 1: anônimo e perfil leitura = 302 na tela e no POST, nada gravado. Verificador de ataque: usuário do hub com leitura ou gestor = 403 e 0 linhas
- [x] form com `<input type="hidden" name="csrf_token">`; fetch com `X-CSRF-Token`. PROVA: POST sem token dá 400 (CSRF_Cookies_Headers)
  EVIDENCIA: a tela não tem form: os dois POST saem por fetch (static/orcamento.js, enviar), e o patch de fetch do base.html:16-27 põe o X-CSRF-Token em todo POST same-origin; a checagem é a global do app.py (_csrf_protect). Prova passo 2: sem token = 400, token errado = 400; verificador: token não ASCII = 400 sem 500. DESVIO DECLARADO: sem campo hidden csrf_token porque não há form
- [x] `MAX_CONTENT_LENGTH` definido; arquivo começa com `50 4B 03 04` ou é recusado; nome trocado por `uuid.uuid4().hex`, fora de `static/`, apagado no `finally` (Padrao_Validacao_de_Input)
  EVIDENCIA: limite por pedido no blueprint (orcamento_rotas.py:62-70: sem Content-Length = 411, acima de 30 MB = 413, e request.max_content_length para o Werkzeug cortar na leitura), sem mexer no MAX_CONTENT_LENGTH global, que cortaria os uploads antigos do /ingest; leitura com teto (:96); magic bytes e zip bomb por conferir_xlsx (:100); temporário por mkstemp (nome sorteado, 0600, no tmp do sistema, fora de static/) em :103, apagado no finally (:112). Prova: 31 MB = 413, chunked sem tamanho = 411, .exe renomeado = 400, nenhum orc_ sobrando no tmp. DESVIO DECLARADO: mkstemp no lugar de uuid4().hex (mesmo efeito, com permissão só do dono)
- [x] empresa do POST validada contra `empresas_permitidas()`; fora do escopo dá 404 (Padrao_IDOR)
  EVIDENCIA: orcamento_rotas.py:74 _empresa_do_pedido (chave em EMPRESAS e em empresas_permitidas(), senão 404 e ACESSO_NEGADO_IDOR em :79); toda consulta e gravação usa o empresa_id que sai dali. Prova passo 3: xyz e vazio = 404 com o evento no log; passo 5: outra empresa intacta
- [x] `request.form.get(...)`, nunca `request.form["x"]`. PROVA: `grep -n 'request.form\["' app.py` não cresce
  EVIDENCIA: orcamento_rotas.py:76 e :85 com request.form.get; `grep -n 'request.form\["' orcamento_rotas.py` vazio; o app.py ganhou só as 3 linhas do registro do blueprint (git diff)
- [x] evento de log `ORCAMENTO_IMPORTADO` com usuário, empresa, ano, linhas e total; sem conteúdo de linha (Padrao_Logging_Estruturado)
  EVIDENCIA: orcamento_rotas.py:44 log_evento (JSON com timestamp, level, event, user_id, ip, path, method, request_id), :214 ORCAMENTO_IMPORTADO com empresa, ano, lote, linhas, substituídas, centros e total; ORCAMENTO_IMPORTACAO_FALHOU só com a classe do erro. Prova passo 6: 4 eventos com os campos fixos e request_id diferente por pedido, sem conta, centro nem descrição no log. Ressalva do verificador: o ip é o remote_addr, que atrás do Traefik tende a ser o do proxy (o resto do FinHub não loga ip nenhum)
- [x] prévia antes de gravar; confirmar substitui o ano numa transação; reimportar não duplica
  EVIDENCIA: /previa não grava (prova passo 4: 0 linhas e 0 lotes depois); /confirmar com BEGIN IMMEDIATE (:189), DELETE do ano (:190), lote, orçado e centros, commit ou rollback inteiro. Prova passo 5: reimportar = 4 linhas, 4 substituídas, outro ano intacto; mutação sem o DELETE derruba a prova (2 FALHA), revertida. Verificador: falha forçada no meio (trigger) = 500 genérico e banco intacto; 6 importações simultâneas = 0 duplicata
- [x] upload: `<label for="..." class="im-drop">`, input fora da tela, ícones `ph-file-arrow-up` e `ph-check-circle`, `<span class="im-msg">` ANTES do botão, botão `disabled` até ter arquivo (Padrao_Upload_Arquivo)
  EVIDENCIA: templates/orcamento_importar.html:42 label.im-drop, :47 input.im-inp (orcamento.css, left -9999px), static/orcamento.js:41 e :46 trocam ph-check-circle e ph-file-arrow-up, html:51 im-msg antes do botão :52 (disabled), orcamento.js:28 habilita só com arquivo, empresa e ano. Arrastar arquivo que não é .xlsx avisa e não habilita (achado do verificador, corrigido; roteiro no Chrome com PDF). Conferência no Chrome em 1366, 375 e escuro: botão à direita, mensagem à esquerda
- [x] mensagem por classe `.im-msg.ok` / `.im-msg.erro`; PROIBIDO `style.color` e `alert(`. PROVA: `grep -rn "alert(\|confirm(\|prompt(" templates/orcamento* static/orcamento*` vazio (Sem_Popup_Nativo)
  EVIDENCIA: static/orcamento.css:39-40 .im-msg.ok/.erro; orcamento.js troca só className (função aviso); grep de alert/confirm/prompt e de style.color nos arquivos novos vazio
- [x] loading com texto no gerúndio ("Lendo o orçamento de 2026..."); PROIBIDO "Carregando...", "Aguarde...", "Processando..." (Padrao_Loading_Estado)
  EVIDENCIA: static/orcamento.js:121 'Lendo o orçamento de <ano>...' e :139 'Gravando o orçamento de <ano>...' em .loading-inline com .spinner-circle 44px (orcamento.css), na área de resultado e não no botão; botões e campos travados durante a espera e destravados no finally; grep dos textos genéricos vazio
- [x] SelectBusca: `<div class="selectbusca" data-name="...">` + `input type="hidden"` + `.sb-display` + `.sb-panel` com `.sb-search`; JS em `static/selectbusca.js`. PROIBIDO `<select`. PROVA: `grep -rn "<select" templates/orcamento*` vazio (Componente_SelectBusca)
  EVIDENCIA: templates/orcamento_importar.html:21-28 (div.selectbusca data-name, hidden, sb-display, sb-panel, sb-search, sb-opt); static/selectbusca.js (filtro sem acento, Enter escolhe a primeira, Esc e clique fora fecham, change no hidden, textContent); grep de <select em templates/orcamento* e static/selectbusca.js vazio. DESVIOS DECLARADOS: sb-display é button (foco de teclado e aria-expanded) e não div; JS e CSS carregados pela tela e não pelo base.html, porque só as telas do módulo usam (quando outra tela usar, sobe para o base)
- [x] bateria de tela zerada no template novo: `<style`, `style="`, hex, emoji, travessão, `unpkg.com` (Verificacoes_Mecanicas_de_Tela)
  EVIDENCIA: greps vazios em templates/orcamento*.html, static/orcamento* e static/selectbusca.js (hex, style, <style, emoji, travessão, select, popup, loading genérico); unpkg vazio; prova passo 7 repete os greps; verificador de conformidade: toda classe usada tem regra (só ph-* vêm do Phosphor por CDN, herança). conferir-telas: 0 erro em /orcamento/importar e /cadastro
- [x] `provas/prova_orcamento_importar.py` verde
  EVIDENCIA: 52 ok, 'tudo ok', exit 0; as 12 provas de provas/ verdes

## Fase 3: cálculo
- [x] realizado lido da `razao` por empresa, competência, conta 3/4 e `replace(centro_custo,'.','')`; nunca da `v_lancamentos`
  EVIDENCIA: orcamento_engine.py:129-132 (razao, contas 3 e 4 depois do trim, centro com trim e sem ponto, sem centro = ''), e o orçado pela mesma regra em :125-128; nenhuma leitura da v_lancamentos. Mutação sem o replace: prova cai (3 FALHA). Dado real: 29.395 de 29.398 células iguais ao REALIZADO do Rel_OrcRel (as 3 são retroativo de julho)
- [x] linhas pela `classificar_conta` do `dre_engine` (reuso, sem motor novo de classificação) (Escada degrau 2)
  EVIDENCIA: orcamento_engine.py:41 linha_da_conta usa classificar_conta e o mesmo agrupamento de calcular_dre_gerencial; :170 subtotais pelo _aplicar_calc_ger do dre_engine. Cruzamento real, versionado: `provas/conferir_orcamento_real.py ... --razao-gnileb ...` chama o motor e a calcular_todas_empresas_gerencial: 231 células, 0 diferenças (7 meses, MKB, Gnileb e consolidado, 11 linhas)
- [x] mês sem razão marcado "sem realizado", não zero
  EVIDENCIA: orcamento_engine.py:153 meses_sem_realizado (no consolidado, basta faltar o razão de uma das empresas; sem_razao_por_empresa diz qual). Prova passo 4: março sem razão = ['2026-03'] no mês e no acumulado, com o orçado de março somado. A tela (Fase 4) mostra o aviso
- [x] Abrir por linha, serviço, coordenador, filial, centro; valor desconhecido dá 400
  EVIDENCIA: orcamento_engine.py:25 DIMENSOES e :59 ValueError para abertura fora da lista (a rota da Fase 4 converte ValueError em 400). Prova passos 2 e 6: as 5 aberturas somam o mesmo total; 16 parâmetros inválidos (empresa, ano, mês, modo, abertura, linha e filtros, inclusive lista e texto no lugar de dicionário) recusados com ValueError. Filtro com valor que não existe devolve total zero, coerente, e não é erro (link salvo com um centro que saiu do cadastro continua abrindo)
- [x] toda consulta tem `empresa_id = ?` (Padrao_IDOR)
  EVIDENCIA: as 4 consultas do motor (:114, :126, :130, :156) e a de centros (:75) filtram por empresa_id IN (?...), com os ids saídos da chave validada; a chave chega já conferida contra empresas_permitidas() na rota (Fase 4, prova da tela). DESVIO DECLARADO: o IN leva 1 ou 2 marcadores montados por f-string ({marcas} é só '?' ou '?,?'); valor nunca entra no texto do SQL; a prova lê a árvore do código e confere que as 4 f-strings de SQL só interpolam `marcas` e que `marcas` só nasce de '?' repetido (antes a checagem passava sem olhar o SQL, achado do verificador)
- [x] `provas/prova_orcamento_calculo.py` verde (totais batem em toda abertura; acumulado = soma dos meses)
  EVIDENCIA: 49 ok, exit 0, conta à mão no docstring (refeita pelo verificador); mutações da equivalência (4 FALHA) e do ponto (3 FALHA) revertidas; 9 casos dos furos do verificador
- [x] `provas/conferir_orcamento_real.py` com caminhos por argumento, sem dado no git
  EVIDENCIA: provas/conferir_orcamento_real.py com --orcrel, --ano, --empresa e --razao; banco em tempfile apagado no finally; saída só com contagem, mês, conta e centro. Rodado nos 7 razões reais da MKB e nos 8 da Gnileb: 29.398 células com 3 diferenças listadas (julho, centro 010120301) e DRE x motor com 231 células, 0 diferenças. Ressalva do verificador aceita: a comparação célula a célula repete a consulta do razão (prova a regra); quem prova o motor é o cruzamento com a DRE

## Fase 4: tela
- [x] card novo no hub do `dashboard.html` sem hex: cor por classe com token
  EVIDENCIA: templates/dashboard.html:15 item orcamento.tela com cor color-mix(in srgb, var(--accent) 80%, black) e letra branca (6,13:1 claro e 6,07:1 escuro, medido no cartão do Cadastro com a mesma cor); prova passo 6: o início traz o link /orcamento?competencia=. DESVIO DECLARADO: a lista do hub passa a cor por item (molde dos vizinhos), não por classe; o valor é token, sem hex
- [x] KPIs `.mg-kpis` / `.mg-kpi` com `.ico > i.ph` + `.corpo > .lbl .val .disc`; `.val` com `font-variant-numeric: tabular-nums`; `.lbl` com `min-height: 25px`; variação boa e ruim por classe `pos` / `neg` (Padrao_KPI_Dashboard)
  EVIDENCIA: templates/orcamento.html (4 .mg-kpi em {% for %}: Orçado ph-target, Realizado ph-receipt, Variação ph-arrows-down-up, % realizado ph-percent, cada um .ico > i.ph + .corpo > .lbl .val .disc); static/orcamento.css:200 faixa de 3px por token, :209 .lbl min-height 25px, :213 .val tabular-nums; pos/neg pintam o card da Variação (orcamento_tela.js, kpis). Contraste medido no Chrome: valor e rótulo do card pos/neg 4,62:1 a 4,79:1 no claro e 7,17:1 a 9,14:1 no escuro. DESVIOS DECLARADOS: 4 indicadores (o plano pede 4) em 4 colunas a partir de 1300px e 2 abaixo (Chrome em 1100px: nenhum valor cortado), no lugar do 6/3/2 da nota; variantes da faixa com nome próprio (k-orcado, k-realizado, k-pct) no lugar de ac-*; medidas de celular da nota (val 18px, lbl 9,5px/23px, disc 10px/13px)
- [x] barra `.fu-bar`, controles na mesma altura, Consultar `btn btn-primario` à direita com `align-self:flex-end` (Padrao_Barra_de_Filtros)
  EVIDENCIA: static/orcamento.css:148-149 .fu-bar com --fu-h 38px aplicado ao SelectBusca, aos dois toggles e ao Consultar; Consultar com margin-left auto e align-self flex-end, à direita da primeira barra (print do Chrome em 1366px); segunda .fu-bar com Abrir por, Linha da DRE e os 4 filtros; rótulo .fu-lbl acima do campo (5,27:1 claro, 9,27:1 escuro). O botão é o .btn-primary do FinHub. Letra branca por palavra-chave (white) no botão sólido e no cartão do hub, como os vizinhos: não é hex, contraste medido. A regra do período (Mês atual e De/Até) não se aplica: a tela escolhe competência (ano e mês), não intervalo de datas; abre no último mês com razão ou no ?competencia= do hub
- [x] Abrir por e No mês/Acumulado no estilo de D4: `<button type="button">`, estado `.on`, wrapper `role="radiogroup"` + `aria-label` (Padrao_Toggle_Tipos)
  EVIDENCIA: templates/orcamento.html:50 #orcModo (tipo 2, ícone em cada opção, .on sólido em :186 do CSS) e :63 #orcAbrir (tipo 1, .on suave em :171), os dois role=radiogroup com aria-labelledby (equivalente ao aria-label) e cada botão role=radio aria-checked, com setas do teclado trocando a opção (Chrome: seta no último volta ao primeiro); rótulo do tipo 2 é 'Visão', não 'Período' (anti-padrão da barra); botão aceso 8,99:1 claro e 5,91:1 escuro. Estilo escolhido pelo Fábio (D4 = 4a)
- [x] título e menu `<i class="ph-bold ph-list icon">` na primeira faixa dentro do card; ordem: Filtro por coluna / Colunas / Exportar CSV / Exportar Excel; arquivo `<prefKey>_AAAA-MM-DD`; exporta só linhas visíveis. PROIBIDO `ph-dots-three` e `id="...Toolbar"` (Padrao_Tabela, Padrao_Cabecalho_da_Tabela)
  EVIDENCIA: templates/orcamento.html:113-118 menu dentro de .tabela-faixa do .tabela-wrap, na ordem Filtro por coluna, Ordenar, Colunas, Exportar CSV, Exportar Excel (Padrao_Tabela manda o Ordenar; o item do checklist o omitia); grep de ph-dots-three e Toolbar vazio; arquivo orcamento_tabela_AAAA-MM-DD (data local); CSV e Excel só das linhas e colunas visíveis (Chrome: filtro 'norte' = 1 de 4 linhas, CSV com 2 linhas, cabeçalho e a linha); Excel pelo POST /orcamento/exportar (prova: CSRF, fórmula neutralizada, limites, EXPORT_DADOS). Sem Linhas por página: a tabela não pagina. Ordenação multi-coluna: clique ordena, Shift + clique acrescenta a coluna como ordem seguinte, com o número da regra no cabeçalho (Chrome: 'ord-asc:1', 'ord-asc:2'). Filtro acha o texto formatado e o número cru ('2477' = 1 de 3). DESVIOS DECLARADOS: (a) preferência só das colunas escondidas, no localStorage (marcador escada em orcamento_tela.js:19), e ordem e filtro não persistem: o FinHub não tem /api/preferencia nem tabela de preferência por usuário; (b) sem data-busca nem busca global: a tabela tem 5 colunas e o filtro por coluna cobre; (c) a página reserva 96px à direita a partir de 1100px para o robô do mascote, então a barra de filtros não ocupa a largura toda nessa faixa
- [x] `.tabela-wrap` com `border-radius:12px` sem `overflow:hidden`; `.tabela-scroll` com `overflow-x:auto` (Padrao_Cabecalho_da_Tabela)
  EVIDENCIA: static/orcamento.css:226 .tabela-wrap 12px sem overflow, :231 .tabela-scroll overflow-x auto com raio no rodapé; Chrome: popup Ordenar aberto inteiro por cima da tabela (print t2) e botão do menu recebendo o clique (elementFromPoint = botão nos 3 modos, depois de reservar a faixa do mascote)
- [x] filtro por coluna dentro do `<thead>`, `placeholder="filtrar"`, evento `input`, sem acento e sem caixa, nasce fechado (Padrao_Filtro_por_Coluna)
  EVIDENCIA: templates/orcamento.html:147 linha .th-filtro no thead, hidden, placeholder filtrar; orcamento_tela.js: evento input chama corpo(), semAcento na comparação, fechar limpa os campos, item do menu fica .ativo, contagem 'N de M linhas'. Chrome: 'norte' = 1 de 4; fechar = 4 linhas
- [x] ícones só `ph ph-*` / `ph-bold ph-*`, sem emoji (Icones_Phosphor)
  EVIDENCIA: grep de emoji vazio nos arquivos novos; todos os ícones ph ph-* ou ph-bold ph-*. Phosphor por CDN segue a herança declarada do base.html
- [x] bateria de tela zerada; `conferir-telas` em computador e celular, claro e escuro
  EVIDENCIA (zerada nos greps; conferir-telas com 0 erro e avisos só de herança, listados): greps vazios (hex, style, <style, select, emoji, travessão, popup, ph-dots-three, Toolbar, border-radius 6 ou 10). conferir-telas em /orcamento, /orcamento/importar e /cadastro: 0 erro; avisos restantes da navbar herdada (Início, nav-sub, divisor, sair) e o rótulo do card pos/neg, que o medidor lê errado por causa do color-mix (medido à parte no Chrome: 4,62:1 a 9,14:1). Roteiro Playwright em 1366, 375 e escuro: sem rolagem lateral, sem erro de JS (o único 404 é /favicon.ico, que o FinHub não tem)
- [x] `provas/prova_orcamento_tela.py`: usuário de uma empresa não lê a outra; número da tela = prova da Fase 3
  EVIDENCIA: 49 ok, exit 0: cliente do hub da MKB recebe 403/404 na Gnileb e 404 no consolidado, e a tela dele não oferece os dois; tela = motor em 6 combinações de parâmetro; 11 entradas tortas = 400/404; exportar com CSRF e limites; bateria de grep e cartão no hub

## Fase 5: entrega
- [ ] comparador nos 8 meses reais da MKB; diferenças listadas por mês e centro
- [ ] Revisao_Vulnerabilidades: `grep -rEn "(senha|password|token|api_key|secret)\s*=\s*['\"]" --include="*.py"` só com `os.getenv`; `grep -rn "| safe" templates/orcamento*` vazio
- [ ] todas as provas de `provas/` verdes
- [ ] `CLAUDE.md` do projeto atualizado; `graphify update .`
- [ ] push no `master`; `/health` com `build` = HEAD
- [ ] Fábio importa o orçamento real e confere um mês
- [ ] ZIP em `z_Versoes/`; LOG `fase=5 acao=entrega resultado=ok`
