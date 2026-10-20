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
- [ ] rota com `@login_required` + `@admin_required`, nessa ordem, como `/ingest` (app.py)
- [ ] form com `<input type="hidden" name="csrf_token">`; fetch com `X-CSRF-Token`. PROVA: POST sem token dá 400 (CSRF_Cookies_Headers)
- [ ] `MAX_CONTENT_LENGTH` definido; arquivo começa com `50 4B 03 04` ou é recusado; nome trocado por `uuid.uuid4().hex`, fora de `static/`, apagado no `finally` (Padrao_Validacao_de_Input)
- [ ] empresa do POST validada contra `empresas_permitidas()`; fora do escopo dá 404 (Padrao_IDOR)
- [ ] `request.form.get(...)`, nunca `request.form["x"]`. PROVA: `grep -n 'request.form\["' app.py` não cresce
- [ ] evento de log `ORCAMENTO_IMPORTADO` com usuário, empresa, ano, linhas e total; sem conteúdo de linha (Padrao_Logging_Estruturado)
- [ ] prévia antes de gravar; confirmar substitui o ano numa transação; reimportar não duplica
- [ ] upload: `<label for="..." class="im-drop">`, input fora da tela, ícones `ph-file-arrow-up` e `ph-check-circle`, `<span class="im-msg">` ANTES do botão, botão `disabled` até ter arquivo (Padrao_Upload_Arquivo)
- [ ] mensagem por classe `.im-msg.ok` / `.im-msg.erro`; PROIBIDO `style.color` e `alert(`. PROVA: `grep -rn "alert(\|confirm(\|prompt(" templates/orcamento* static/orcamento*` vazio (Sem_Popup_Nativo)
- [ ] loading com texto no gerúndio ("Lendo o orçamento de 2026..."); PROIBIDO "Carregando...", "Aguarde...", "Processando..." (Padrao_Loading_Estado)
- [ ] SelectBusca: `<div class="selectbusca" data-name="...">` + `input type="hidden"` + `.sb-display` + `.sb-panel` com `.sb-search`; JS em `static/selectbusca.js`. PROIBIDO `<select`. PROVA: `grep -rn "<select" templates/orcamento*` vazio (Componente_SelectBusca)
- [ ] bateria de tela zerada no template novo: `<style`, `style="`, hex, emoji, travessão, `unpkg.com` (Verificacoes_Mecanicas_de_Tela)
- [ ] `provas/prova_orcamento_importar.py` verde

## Fase 3: cálculo
- [ ] realizado lido da `razao` por empresa, competência, conta 3/4 e `replace(centro_custo,'.','')`; nunca da `v_lancamentos`
- [ ] linhas pela `classificar_conta` do `dre_engine` (reuso, sem motor novo de classificação) (Escada degrau 2)
- [ ] mês sem razão marcado "sem realizado", não zero
- [ ] Abrir por linha, serviço, coordenador, filial, centro; valor desconhecido dá 400
- [ ] toda consulta tem `empresa_id = ?` (Padrao_IDOR)
- [ ] `provas/prova_orcamento_calculo.py` verde (totais batem em toda abertura; acumulado = soma dos meses)
- [ ] `provas/conferir_orcamento_real.py` com caminhos por argumento, sem dado no git

## Fase 4: tela
- [ ] card novo no hub do `dashboard.html` sem hex: cor por classe com token
- [ ] KPIs `.mg-kpis` / `.mg-kpi` com `.ico > i.ph` + `.corpo > .lbl .val .disc`; `.val` com `font-variant-numeric: tabular-nums`; `.lbl` com `min-height: 25px`; variação boa e ruim por classe `pos` / `neg` (Padrao_KPI_Dashboard)
- [ ] barra `.fu-bar`, controles na mesma altura, Consultar `btn btn-primario` à direita com `align-self:flex-end` (Padrao_Barra_de_Filtros)
- [ ] Abrir por e No mês/Acumulado no estilo de D4: `<button type="button">`, estado `.on`, wrapper `role="radiogroup"` + `aria-label` (Padrao_Toggle_Tipos)
- [ ] título e menu `<i class="ph-bold ph-list icon">` na primeira faixa dentro do card; ordem: Filtro por coluna / Colunas / Exportar CSV / Exportar Excel; arquivo `<prefKey>_AAAA-MM-DD`; exporta só linhas visíveis. PROIBIDO `ph-dots-three` e `id="...Toolbar"` (Padrao_Tabela, Padrao_Cabecalho_da_Tabela)
- [ ] `.tabela-wrap` com `border-radius:12px` sem `overflow:hidden`; `.tabela-scroll` com `overflow-x:auto` (Padrao_Cabecalho_da_Tabela)
- [ ] filtro por coluna dentro do `<thead>`, `placeholder="filtrar"`, evento `input`, sem acento e sem caixa, nasce fechado (Padrao_Filtro_por_Coluna)
- [ ] ícones só `ph ph-*` / `ph-bold ph-*`, sem emoji (Icones_Phosphor)
- [ ] bateria de tela zerada; `conferir-telas` em computador e celular, claro e escuro
- [ ] `provas/prova_orcamento_tela.py`: usuário de uma empresa não lê a outra; número da tela = prova da Fase 3

## Fase 5: entrega
- [ ] comparador nos 8 meses reais da MKB; diferenças listadas por mês e centro
- [ ] Revisao_Vulnerabilidades: `grep -rEn "(senha|password|token|api_key|secret)\s*=\s*['\"]" --include="*.py"` só com `os.getenv`; `grep -rn "| safe" templates/orcamento*` vazio
- [ ] todas as provas de `provas/` verdes
- [ ] `CLAUDE.md` do projeto atualizado; `graphify update .`
- [ ] push no `master`; `/health` com `build` = HEAD
- [ ] Fábio importa o orçamento real e confere um mês
- [ ] ZIP em `z_Versoes/`; LOG `fase=5 acao=entrega resultado=ok`
