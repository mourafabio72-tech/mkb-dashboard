/* Orçado x Realizado (Fases 4, 6 e 7). Linhas da DRE: /orcamento/arvore, em árvore e por mês, e a conta
   analítica abre os lançamentos do razão num modal (/orcamento/lancamentos). Serviço, coordenador, filial
   e centro: /orcamento/dimensao, com Receita, Custo e despesa, MC e MC % (orçado e realizado) e a variação
   da MC, numa tabela com o menu sanduíche (Padrao_Tabela); clicar numa linha abre a DRE só dela. O botão
   Filtro abre o painel lateral com o período e os filtros, que valem para todas as aberturas.
   Filtro, ordem e exportação da tabela rodam no navegador, sobre o que está visível. Texto só por textContent. */
(function () {
  var tela = document.getElementById('orcTela');
  if (!tela) return;
  var $ = function (id) { return document.getElementById(id); };
  var reais = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  var pctFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var COLUNAS = [
    { chave: 'rotulo', titulo: 'Serviço', num: false },
    { chave: 'rec_o', grupo: 'Receita', titulo: 'Orçado', num: true },
    { chave: 'rec_r', grupo: 'Receita', titulo: 'Realizado', num: true },
    { chave: 'cd_o', grupo: 'Custo e despesa', titulo: 'Orçado', num: true },
    { chave: 'cd_r', grupo: 'Custo e despesa', titulo: 'Realizado', num: true },
    { chave: 'mc_o', grupo: 'MC', titulo: 'Orçado', num: true },
    { chave: 'mc_r', grupo: 'MC', titulo: 'Realizado', num: true },
    { chave: 'mcp_o', grupo: 'MC %', titulo: 'Orçado', num: true, pct: true },
    { chave: 'mcp_r', grupo: 'MC %', titulo: 'Realizado', num: true, pct: true },
    { chave: 'variacao', titulo: 'Variação da MC', num: true }
  ];
  var PREF = 'orcamento_dimensao';
  // escada: colunas escondidas guardadas no navegador (localStorage); o FinHub não tem tabela de
  // preferência por usuário. Subir para o banco quando outra tela do FinHub precisar de preferência.
  var escondidas = lerPref();
  var PREF_VISAO = 'orcamento_visao';
  var linhas = [], totalDim = null, ordem = null, ocupado = false, estado = { modo: 'evolucao', abrir: 'linha', visao: 'tabela' };
  try { if (localStorage.getItem(PREF_VISAO) === 'painel') estado.visao = 'painel'; } catch (e) { /* sem armazenamento */ }
  var rotuloAtual = '', dash = null;  // empresa e período da última consulta; dados do dashboard para redesenhar
  var arv = null, abertos = {}, filtroArv = '', consultado = null;  // parâmetros da última consulta

  function el(tag, classe, texto) {
    var n = document.createElement(tag);
    if (classe) n.className = classe;
    if (texto !== undefined && texto !== null) n.textContent = texto;
    return n;
  }
  function semAcento(t) { return String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function lerPref() { try { return JSON.parse(localStorage.getItem(PREF) || '[]'); } catch (e) { return []; } }
  function gravarPref() { try { localStorage.setItem(PREF, JSON.stringify(escondidas)); } catch (e) { /* sem armazenamento */ } }
  function hoje() {
    var d = new Date(), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }
  function nome(c) { return c.grupo ? c.grupo + ' ' + c.titulo.toLowerCase() : c.titulo; }
  function texto(col, l) {
    var v = l[col.chave];
    if (col.chave === 'rotulo') return v;
    if (v === null || v === undefined) return col.pct && l.mc_r !== null ? 'sem receita' : 'sem dado';
    if (col.pct) return pctFmt.format(v) + '%';
    // sinal antes do R$, como nos cards; segue o ÷ 1.000 e os centavos da faixa de opções
    return (num(v).charAt(0) === '-' ? '-R$ ' + num(v).slice(1) : 'R$ ' + num(v)) + (fmtPref.mil ? ' mil' : '');
  }

  /* ── seletores tipo 1 e tipo 2 (Padrao_Toggle_Tipos) ── */
  function marcar(id, valor) {
    $(id).querySelectorAll('button').forEach(function (x) {
      x.classList.toggle('on', x.dataset.valor === valor);
      x.setAttribute('aria-checked', x.dataset.valor === valor ? 'true' : 'false');
    });
  }
  function grupo(id, chave, aoMudar) {
    $(id).addEventListener('keydown', function (e) {  // radiogroup: setas trocam a opção
      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].indexOf(e.key) === -1) return;
      var bs = Array.prototype.slice.call($(id).querySelectorAll('button')), i = bs.indexOf(document.activeElement);
      if (i === -1) return;
      e.preventDefault();
      var prox = bs[(i + (e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? bs.length - 1 : 1)) % bs.length];
      prox.focus();
      prox.click();
    });
    $(id).addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b || ocupado || b.dataset.valor === estado[chave]) return;
      marcar(id, b.dataset.valor);
      estado[chave] = b.dataset.valor;
      if (aoMudar) aoMudar();
    });
  }
  grupo('orcModo', 'modo', function () { if (arv && estado.abrir === 'linha') desenharArvore(); });
  grupo('orcAbrir', 'abrir', function () { consultar(); });
  // Fase 8: Tabela ou Dashboard, com os mesmos filtros; a escolha fica no navegador
  function aplicarVisao() {
    marcar('orcVisao', estado.visao);
    document.querySelectorAll('.orc-so-tabela').forEach(function (n) { n.hidden = estado.visao === 'painel'; });
  }
  grupo('orcVisao', 'visao', function () {
    try { localStorage.setItem(PREF_VISAO, estado.visao); } catch (e) { /* sem armazenamento */ }
    aplicarVisao();
    consultar();
  });
  aplicarVisao();

  /* ── campos do painel de filtros ── */
  var CAMPOS = [['servico', 'Serviço'], ['coordenador', 'Coordenador'], ['filial', 'Filial'], ['centro', 'Centro'],
                ['conta', 'Conta'], ['descricao', 'Descrição']];
  var NO_PAINEL = ['de', 'ate'].concat(CAMPOS.map(function (c) { return c[0]; }));
  function sb(nomeCampo) { return document.querySelector('.selectbusca[data-name="' + nomeCampo + '"]'); }
  // grava o valor do SelectBusca sem abrir a lista (drilldown, chip e Limpar)
  function definir(nomeCampo, valor, rotulo) {
    var caixa = sb(nomeCampo);
    $('orc_' + nomeCampo).value = valor;
    if (!caixa) return;
    var opt = caixa.querySelector('.sb-opt[data-value="' + CSS.escape(valor) + '"]');
    caixa.querySelector('.sb-label').textContent = opt ? opt.textContent : (rotulo || valor);
    caixa.classList.toggle('tem-valor', !!valor);
    caixa.querySelectorAll('.sb-opt').forEach(function (o) { o.setAttribute('aria-selected', o === opt ? 'true' : 'false'); });
  }
  function rotuloDe(nomeCampo) { var caixa = sb(nomeCampo); return caixa ? caixa.querySelector('.sb-label').textContent : $('orc_' + nomeCampo).value.trim(); }
  function fotografar() {
    var f = {};
    NO_PAINEL.forEach(function (c) { f[c] = [$('orc_' + c).value, rotuloDe(c)]; });
    return f;
  }
  function restaurar(f) { NO_PAINEL.forEach(function (c) { definir(c, f[c][0], f[c][1]); }); }

  // um chip por filtro aplicado, com o x que tira só aquele; o período fica sempre à vista
  function chips() {
    var box = $('orcAtivos'), n = 0, de = +$('orc_de').value, ate = +$('orc_ate').value;
    box.replaceChildren();
    var per = el('span', 'orc-ativo orc-ativo-fixo');
    per.appendChild(el('i', 'ph ph-calendar-blank'));
    per.appendChild(el('span', '', (de === ate ? NOMES_MES[de] : NOMES_MES[de] + ' a ' + NOMES_MES[ate]) + '/' + $('orc_ano').value));
    box.appendChild(per);
    CAMPOS.forEach(function (c) {
      if (!$('orc_' + c[0]).value.trim()) return;
      n++;
      var chip = el('span', 'orc-ativo'), x = el('button', 'orc-ativo-x');
      chip.appendChild(el('span', 'orc-ativo-lbl', c[1]));
      chip.appendChild(el('span', '', rotuloDe(c[0])));
      x.type = 'button';
      x.setAttribute('aria-label', 'Tirar o filtro ' + c[1].toLowerCase());
      x.appendChild(el('i', 'ph ph-x'));
      x.addEventListener('click', function () { if (ocupado) return; definir(c[0], ''); consultar(); });
      chip.appendChild(x);
      box.appendChild(chip);
    });
    $('orcFiltroQtd').textContent = n ? String(n) : '';
    $('orcFiltroQtd').hidden = !n;
  }

  /* ── consulta ── */
  function parametros() {
    var p = new URLSearchParams();
    ['empresa', 'ano'].concat(NO_PAINEL).forEach(function (c) {
      var v = $('orc_' + c).value.trim();
      if (v) p.set(c, v);
    });
    if (estado.abrir !== 'linha') p.set('abrir_por', estado.abrir);
    return p;
  }

  function travar(sim) {
    ocupado = sim;
    $('orcConsultar').disabled = sim;
    tela.classList.toggle('ocupado', sim);
  }

  function consultar() {
    if (ocupado) return;
    $('orcAvisos').replaceChildren();
    if (+$('orc_de').value > +$('orc_ate').value) { aviso('O mês inicial vem depois do final. Ajuste o período no Filtro.', 'erro'); return; }
    chips();
    travar(true);
    $('orcTabelaWrap').hidden = true;
    $('orcArvoreWrap').hidden = true;
    $('orcDash').hidden = true;
    $('orcVazio').hidden = true;
    $('orcKpis').hidden = true;
    $('orcCarregando').hidden = false;
    var naArvore = estado.abrir === 'linha', noPainel = estado.visao === 'painel';
    consultado = parametros();
    var url = noPainel ? tela.dataset.urlPainel : (naArvore ? tela.dataset.urlArvore : tela.dataset.urlDimensao);
    fetch(url + '?' + parametros().toString()).then(function (r) {
      return r.json().catch(function () { return { erro: 'Não foi possível buscar agora. Tente de novo.' }; });
    }).then(function (j) {
      if (!j.ok) { aviso(j.erro || 'Não foi possível calcular.', 'erro'); return; }
      rotuloAtual = j.dados.rotulo_empresa + ' · ' + j.dados.rotulo_periodo;
      if (noPainel) desenharPainel(j.dados);
      else if (naArvore) receberArvore(j.dados); else desenharDimensao(j.dados);
    }).catch(function () {
      aviso('Sem conexão. Tente de novo.', 'erro');
    }).finally(function () {
      $('orcCarregando').hidden = true;
      travar(false);
    });
  }

  function aviso(msg, tipo) {
    $('orcAvisos').appendChild(el('p', 'orc-aviso' + (tipo ? ' ' + tipo : ''), msg));
  }

  function mesesPorExtenso(lista) {
    return lista.map(function (c) { return NOMES_MES[+c.slice(5, 7)] + '/' + c.slice(0, 4); }).join(', ');
  }

  function avisosComuns(d) {
    $('orcAte').textContent = d.realizado_ate ? 'Realizado disponível até ' + d.realizado_ate + '.' : '';
    if (d.sem_orcamento) aviso('Não há orçamento importado para ' + d.rotulo_empresa + ' em ' + d.ano + '. O orçado aparece zerado.');
    Object.keys(d.sem_razao_por_empresa || {}).forEach(function (sigla) {
      aviso('Sem razão importado da ' + sigla + ' em ' + mesesPorExtenso(d.sem_razao_por_empresa[sigla]) +
            '. O realizado desse período fica incompleto.');
    });
    if (d.empresa === 'consolidado' && d.eliminado_equivalencia) {
      aviso('Consolidado: equivalência patrimonial da Gnileb eliminada (' + reais.format(Math.abs(d.eliminado_equivalencia)) +
            ' em Outros Resultados), igual à DRE consolidada.');
    }
  }

  function kpis(t, base, mesesSem) {
    var semDado = t.realizado === null;  // nenhum mês do período tem razão: não é zero nem igual ao orçado
    var valores = semDado ? {
      orcado: [reais.format(t.orcado), base],
      realizado: ['sem dado', 'período sem razão importado'],
      variacao: ['sem dado', 'falta o realizado'],
      pct: ['sem dado', 'falta o realizado']
    } : {
      orcado: [reais.format(t.orcado), base],
      realizado: [reais.format(t.realizado), mesesSem ? 'período com mês sem razão' : base],
      variacao: [reais.format(t.variacao), t.variacao > 0 ? 'melhor que o orçado' : (t.variacao < 0 ? 'pior que o orçado' : 'igual ao orçado')],
      pct: [t.pct === null ? 'sem orçado' : pctFmt.format(t.pct) + '%', 'realizado sobre o orçado']
    };
    Object.keys(valores).forEach(function (k) {
      var card = document.querySelector('[data-kpi="' + k + '"]');
      card.querySelector('.val').textContent = valores[k][0];
      card.querySelector('.disc').textContent = valores[k][1];
      if (k === 'variacao') {
        card.classList.toggle('pos', !semDado && t.variacao > 0);
        card.classList.toggle('neg', !semDado && t.variacao < 0);
      }
    });
  }

  /* ── Fase 7: abertura por serviço, coordenador, filial ou centro ── */
  function plano(l) {
    return { rotulo: l.rotulo, chave: l.chave, rec_o: l.receita[0], rec_r: l.receita[1], cd_o: l.custo_despesa[0],
             cd_r: l.custo_despesa[1], mc_o: l.mc[0], mc_r: l.mc[1], mcp_o: l.mc_pct[0], mcp_r: l.mc_pct[1], variacao: l.variacao };
  }

  function desenharDimensao(d) {
    avisosComuns(d);
    if (d.empresa !== 'mkb') aviso('O razão da Gnileb não tem centro de custo: o realizado dela aparece em Sem centro de custo.');
    if (d.meses_considerados.length && d.meses_considerados.length < d.competencias.length) {
      aviso('O orçado considera só os meses com razão (' + mesesPorExtenso(d.meses_considerados) + '), para comparar o mesmo período.');
    }
    if (estado.modo === 'evolucao') aviso('A evolução mês a mês vale para Linhas da DRE; nesta abertura, o valor é a soma do período.');
    var t = d.total;
    kpis({ orcado: t.mc[0], realizado: t.mc[1], variacao: t.variacao || 0,
           pct: t.mc[0] && t.mc[1] !== null ? Math.round(t.mc[1] / t.mc[0] * 1000) / 10 : null },
         'Margem de contribuição', d.meses_sem_realizado.length);
    totalDim = plano(t);
    totalDim.rotulo = 'Total';
    linhas = d.linhas.map(function (l, i) { var x = plano(l); x._i = i; return x; });
    ordem = null;
    COLUNAS[0].titulo = d.dimensao;
    $('orcCab').querySelector('.th-titulos th[data-col="rotulo"]').textContent = d.dimensao;
    $('orcCab').querySelector('[data-th-filtro="rotulo"]').setAttribute('aria-label', 'Filtrar ' + d.dimensao.toLowerCase());
    $('orcTitulo').textContent = d.rotulo_empresa + ' · ' + d.rotulo_periodo + (fmtPref.mil ? ' · em R$ mil' : '');
    $('orcKpis').hidden = false;
    if (!linhas.length) { $('orcVazio').hidden = false; return; }
    $('orcTabelaWrap').hidden = false;
    corpo();
  }

  // drilldown: a linha vira filtro e a tela abre a DRE em árvore só dela (grupo e conta)
  function abrirNaDre(l) {
    if (ocupado || !l.chave) return;
    definir(l.campo || estado.abrir, l.chave, l.rotulo);
    estado.abrir = 'linha';
    marcar('orcAbrir', 'linha');
    estado.visao = 'tabela';
    try { localStorage.setItem(PREF_VISAO, 'tabela'); } catch (e) { /* sem armazenamento */ }
    aplicarVisao();
    consultar();
  }

  /* ── tabela ── */
  function montarCabecalho() {
    var g = el('tr', 'th-grupos'), t = el('tr', 'th-titulos'), f = el('tr', 'th-filtro');
    for (var i = 0; i < COLUNAS.length;) {  // uma célula por sequência de colunas do mesmo grupo
      var c = COLUNAS[i], n = 1;
      while (c.grupo && COLUNAS[i + n] && COLUNAS[i + n].grupo === c.grupo) n++;
      var th = el('th', 'th-grupo', c.grupo || '');
      th.colSpan = n;
      th.dataset.grupo = c.grupo || c.chave;
      g.appendChild(th);
      i += n;
    }
    COLUNAS.forEach(function (c) {
      var th = el('th', c.num ? 'num' : '', c.titulo), thf = el('th'), inp = el('input');
      th.dataset.col = thf.dataset.col = c.chave;
      if (c.grupo) th.title = nome(c);
      if (c.chave === 'variacao') th.title = 'MC realizada menos MC orçada: positivo é melhor que o orçado';
      t.appendChild(th);
      inp.type = 'text';
      inp.placeholder = 'filtrar';
      inp.dataset.thFiltro = c.chave;
      inp.setAttribute('aria-label', 'Filtrar ' + nome(c).toLowerCase());
      thf.appendChild(inp);
      f.appendChild(thf);
    });
    f.hidden = true;
    $('orcCab').replaceChildren(g, t, f);
  }
  montarCabecalho();

  function filtros() {
    var f = {};
    document.querySelectorAll('[data-th-filtro]').forEach(function (i) { if (i.value.trim()) f[i.dataset.thFiltro] = semAcento(i.value.trim()); });
    return f;
  }

  function visiveis() {
    var f = filtros(), lista = linhas.filter(function (l) {
      return Object.keys(f).every(function (k) {
        var col = COLUNAS.filter(function (c) { return c.chave === k; })[0];
        var cru = col.num && l[col.chave] !== null ? ' ' + String(l[col.chave]) + ' ' + String(l[col.chave]).replace('.', ',') : '';
        return semAcento(texto(col, l) + cru).indexOf(f[k]) !== -1;  // acha "1234" e "1.234,56"
      });
    });
    if (ordem && ordem.length) {  // várias regras: a primeira manda, as outras desempatam
      lista = lista.slice().sort(function (a, b) {
        for (var n = 0; n < ordem.length; n++) {
          var o = ordem[n], x = a[o.chave], y = b[o.chave], r;
          if (x === null || y === null) r = x === y ? 0 : (x === null ? -1 : 1);
          else r = typeof x === 'string' ? x.localeCompare(y, 'pt-BR') : x - y;
          if (r) return o.desc ? -r : r;
        }
        return a._i - b._i;
      });
    }
    return lista;
  }

  function linhaTabela(l, total) {
    var tr = el('tr', total ? 'orc-total' : '');
    COLUNAS.forEach(function (c) {
      var td = el('td', c.num ? 'num' : '');
      if (c.chave === 'rotulo' && !total && l.chave) {
        var b = el('button', 'orc-drill', l.rotulo);
        b.type = 'button';
        b.title = 'Abrir a DRE só de ' + l.rotulo;
        b.addEventListener('click', function () { abrirNaDre(l); });
        td.appendChild(b);
      } else td.textContent = texto(c, l);
      if (c.chave === 'variacao' && l.variacao) td.classList.add(l.variacao > 0 ? 'pos' : 'neg');
      td.hidden = escondidas.indexOf(c.chave) !== -1;
      tr.appendChild(td);
    });
    return tr;
  }

  function corpo() {
    var tb = $('orcCorpo'), lista = visiveis(), filtrando = Object.keys(filtros()).length;
    tb.replaceChildren();
    lista.forEach(function (l) { tb.appendChild(linhaTabela(l)); });
    if (!lista.length) {
      var tr = el('tr', 'tabela-vazia'), td = el('td', '', 'Nenhuma linha com esse filtro.');
      td.colSpan = COLUNAS.length;
      tr.appendChild(td);
      tb.appendChild(tr);
    }
    // com filtro por coluna, o total da base continua o do recorte inteiro: o rodapé some para não enganar
    $('orcRodape').replaceChildren();
    if (totalDim && !filtrando) $('orcRodape').appendChild(linhaTabela(totalDim, true));
    document.querySelectorAll('#orcCab .th-grupos th').forEach(function (th) {
      var n = COLUNAS.filter(function (c) { return (c.grupo || c.chave) === th.dataset.grupo && escondidas.indexOf(c.chave) === -1; }).length;
      th.hidden = !n;
      if (n) th.colSpan = n;
    });
    document.querySelectorAll('#orcTabela th[data-col]').forEach(function (th) {
      th.hidden = escondidas.indexOf(th.dataset.col) !== -1;
      if (!th.parentNode.classList.contains('th-titulos')) return;
      var pos = (ordem || []).map(function (o) { return o.chave; }).indexOf(th.dataset.col), o = (ordem || [])[pos];
      th.classList.toggle('ord-asc', !!o && !o.desc);
      th.classList.toggle('ord-desc', !!o && o.desc);
      th.dataset.ordem = ordem && ordem.length > 1 && o ? String(pos + 1) : '';
    });
    $('orcContagem').textContent = filtrando ? lista.length + ' de ' + linhas.length + ' linhas'
                                             : linhas.length + (linhas.length === 1 ? ' linha' : ' linhas');
  }

  /* ── menu sanduíche e popups ── */
  var menu = $('orcMenu'), btn = $('orcMenuBtn');
  function fecharTudo() {
    menu.classList.remove('aberto');
    btn.setAttribute('aria-expanded', 'false');
    document.querySelectorAll('.ta-popup.aberto').forEach(function (p) { p.classList.remove('aberto'); });
  }
  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    var abrir = !menu.classList.contains('aberto');
    fecharTudo();
    if (abrir) { menu.classList.add('aberto'); btn.setAttribute('aria-expanded', 'true'); }
  });
  document.addEventListener('click', function (e) { if (!e.target.closest('.ta-menu-wrapper')) fecharTudo(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') fecharTudo(); });
  document.querySelectorAll('.ta-fechar').forEach(function (b) { b.addEventListener('click', fecharTudo); });

  menu.addEventListener('click', function (e) {
    var item = e.target.closest('[data-acao]');
    if (!item) return;
    var acao = item.dataset.acao;
    fecharTudo();
    if (acao === 'filtro') alternarFiltro(item);
    else if (acao === 'ordenar') abrirOrdenar();
    else if (acao === 'colunas') abrirColunas();
    else if (acao === 'csv') exportarCsv();
    else if (acao === 'excel') exportarExcel();
  });

  function alternarFiltro(item) {
    var linhaFiltro = document.querySelector('#orcTabela .th-filtro'), abrir = linhaFiltro.hidden;
    linhaFiltro.hidden = !abrir;
    item.classList.toggle('ativo', abrir);
    if (!abrir) document.querySelectorAll('[data-th-filtro]').forEach(function (i) { i.value = ''; });  // fechar limpa
    else linhaFiltro.querySelector('input').focus();
    corpo();
  }
  document.querySelectorAll('[data-th-filtro]').forEach(function (i) { i.addEventListener('input', corpo); });

  // clique ordena por uma coluna; Shift + clique acrescenta a coluna como ordem seguinte (Padrao_Tabela)
  function regra(chave) { return (ordem || []).filter(function (o) { return o.chave === chave; })[0]; }
  function ordenarPor(chave, desc, somar) {
    if (!chave) ordem = null;
    else if (somar && ordem) {
      var r = regra(chave);
      if (r) r.desc = desc; else ordem.push({ chave: chave, desc: desc });
    } else ordem = [{ chave: chave, desc: desc }];
    corpo();
  }
  document.querySelectorAll('#orcTabela .th-titulos th').forEach(function (th) {
    th.tabIndex = 0;
    var ir = function (e) { var r = regra(th.dataset.col); ordenarPor(th.dataset.col, !!r && !r.desc, e.shiftKey); };
    th.addEventListener('click', ir);
    th.addEventListener('keydown', function (e) { if (e.key === 'Enter') ir(e); });
  });

  function abrirOrdenar() {
    var c = $('orcOrdenarCorpo');
    c.replaceChildren();
    COLUNAS.forEach(function (col) {
      var linha = el('div', 'ta-ordem-linha');
      linha.appendChild(el('span', '', nome(col)));
      [['Crescente', false, 'ph-sort-ascending'], ['Decrescente', true, 'ph-sort-descending']].forEach(function (o) {
        var r = regra(col.chave), b = el('button', 'ta-ordem-btn' + (r && r.desc === o[1] ? ' on' : ''));
        b.type = 'button';
        b.appendChild(el('i', 'ph ' + o[2]));
        b.appendChild(document.createTextNode(' ' + o[0]));
        b.title = 'Clique troca a ordem; com Shift, acrescenta como ordem seguinte';
        b.addEventListener('click', function (e) { ordenarPor(col.chave, o[1], e.shiftKey); abrirOrdenar(); });
        linha.appendChild(b);
      });
      c.appendChild(linha);
    });
    $('orcPopOrdenar').classList.add('aberto');
  }
  $('orcOrdemOriginal').addEventListener('click', function () { ordenarPor(null); abrirOrdenar(); });

  function abrirColunas() {
    var c = $('orcColunasCorpo');
    c.replaceChildren();
    COLUNAS.slice(1).forEach(function (col) {
      var rot = el('label', 'ta-coluna'), caixa = el('input');
      caixa.type = 'checkbox';
      caixa.checked = escondidas.indexOf(col.chave) === -1;
      caixa.addEventListener('change', function () {
        escondidas = escondidas.filter(function (k) { return k !== col.chave; });
        if (!caixa.checked) escondidas.push(col.chave);
        gravarPref();
        corpo();
      });
      rot.appendChild(caixa);
      rot.appendChild(document.createTextNode(' ' + nome(col)));
      c.appendChild(rot);
    });
    $('orcPopColunas').classList.add('aberto');
  }

  /* ── exportação: só as linhas e colunas visíveis ── */
  function tabelaVisivel() {
    var cols = COLUNAS.filter(function (c) { return escondidas.indexOf(c.chave) === -1; });
    var lista = visiveis().concat(totalDim && !Object.keys(filtros()).length ? [totalDim] : []);
    return {
      cab: cols.map(nome),
      linhas: lista.map(function (l) { return cols.map(function (c) { return l[c.chave]; }); })
    };
  }
  function baixar(blob, arquivo) {
    var a = el('a');
    a.href = URL.createObjectURL(blob);
    a.download = arquivo;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }
  // CSV com ; e BOM para o Excel brasileiro; texto que começa com = + - @ vira texto (sem fórmula)
  function baixarCsv(cab, lista, arquivo) {
    var campo = function (v) {
      if (v === null || v === undefined) return '';
      if (typeof v === 'number') return String(v).replace('.', ',');
      var s = String(v);
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
      return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    var txt = [cab].concat(lista).map(function (l) { return l.map(campo).join(';'); }).join('\r\n');
    baixar(new Blob(['﻿' + txt], { type: 'text/csv;charset=utf-8' }), arquivo);
  }
  function exportarCsv() {
    var t = tabelaVisivel();
    baixarCsv(t.cab, t.linhas, PREF + '_' + hoje() + '.csv');
  }
  function exportarExcel() {
    var t = tabelaVisivel();
    fetch(tela.dataset.urlExportar, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome: PREF + '_' + hoje(), cabecalho: t.cab, linhas: t.linhas })
    }).then(function (r) {
      if (!r.ok) throw new Error();
      return r.blob();
    }).then(function (b) { baixar(b, PREF + '_' + hoje() + '.xlsx'); })
      .catch(function () { aviso('Não foi possível gerar o Excel. Tente o CSV.', 'erro'); });
  }

  /* ── painel lateral e modal (Padrao_Modal_Nao_Fecha_Sozinho: só o X, Fechar e Aplicar fecham;
        Padrao_Transicao_Simetrica: entram e saem pelo mesmo caminho, em 200 ms) ── */
  var voltaFoco = null, fotoPainel = null;
  function abrirCamada(caixa, fundo) {
    voltaFoco = document.activeElement;
    fundo.hidden = false;
    caixa.hidden = false;
    void caixa.offsetWidth;  // a transição parte do estado fechado
    fundo.classList.add('aberto');
    caixa.classList.add('aberto');
    document.body.classList.add('drawer-aberto');
    var primeiro = caixa.querySelector('.orc-x');
    if (primeiro) primeiro.focus();
  }
  // lista do SelectBusca no fim do painel: rola o corpo até ela aparecer inteira, sem passar por trás do rodapé
  $('orcDrawer').addEventListener('click', function (e) {
    var bt = e.target.closest('.sb-display');
    if (!bt) return;
    setTimeout(function () {
      var lista = bt.parentNode.querySelector('.sb-panel');
      if (bt.parentNode.classList.contains('open') && lista) lista.scrollIntoView({ block: 'nearest' });
    }, 0);
  });
  function fecharCamada(caixa, fundo) {
    fundo.classList.remove('aberto');
    caixa.classList.remove('aberto');
    document.body.classList.remove('drawer-aberto');
    setTimeout(function () { if (!caixa.classList.contains('aberto')) { fundo.hidden = true; caixa.hidden = true; } }, 200);
    if (voltaFoco && voltaFoco.focus) voltaFoco.focus();
  }
  function painelAberto() { return $('orcDrawer').classList.contains('aberto'); }
  $('orcAbrirFiltro').addEventListener('click', function () {
    if (ocupado) return;
    fotoPainel = fotografar();
    $('orcDrawerMsg').textContent = '';
    abrirCamada($('orcDrawer'), $('orcDrawerFundo'));
  });
  // o X desfaz o que não foi aplicado; Aplicar consulta com o que está no painel
  function fecharPainel() {
    if (fotoPainel) restaurar(fotoPainel);
    fecharCamada($('orcDrawer'), $('orcDrawerFundo'));
  }
  $('orcAplicar').addEventListener('click', function () {
    var conta = $('orc_conta').value.trim();
    if (conta && !/^[0-9][0-9.]{0,39}$/.test(conta)) { $('orcDrawerMsg').textContent = 'Conta contábil: use só números e pontos, como 3.1.1.'; $('orc_conta').focus(); return; }
    if (+$('orc_de').value > +$('orc_ate').value) { $('orcDrawerMsg').textContent = 'O mês inicial vem depois do final.'; return; }
    fotoPainel = null;
    fecharCamada($('orcDrawer'), $('orcDrawerFundo'));
    consultar();
  });
  $('orcLimpar').addEventListener('click', function () {
    CAMPOS.forEach(function (c) { definir(c[0], ''); });
    $('orcDrawerMsg').textContent = '';
  });
  ['orc_conta', 'orc_descricao'].forEach(function (id) {
    $(id).addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); $('orcAplicar').click(); } });
  });
  document.querySelectorAll('[data-fechar]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.dataset.fechar === 'orcDrawer') fecharPainel();
      else fecharCamada($('orcLanc'), $('orcLancFundo'));
    });
  });
  // foco preso na camada aberta: Tab no último volta ao primeiro
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab') return;
    var caixa = $('orcLanc').classList.contains('aberto') ? $('orcLanc') : (painelAberto() ? $('orcDrawer') : null);
    if (!caixa) return;
    var f = Array.prototype.filter.call(caixa.querySelectorAll('button, input:not([type=hidden])'),
                                        function (x) { return !x.disabled && x.offsetParent !== null; });
    if (!f.length) return;
    var i = f.indexOf(document.activeElement);
    if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && (i === -1 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); }
  });

  /* ── lançamentos da conta analítica ── */
  var lanc = null, pedidoLanc = 0;  // só a resposta do último pedido desenha
  function dataBr(d) { var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || ''); return m ? m[3] + '/' + m[2] + '/' + m[1] : (d || ''); }
  function abrirLancamentos(l) {
    lanc = null;
    $('orcLancTit').textContent = l.codigo + ' · ' + l.rotulo;
    $('orcLancSub').textContent = rotuloAtual;
    $('orcLancCorpo').replaceChildren();
    $('orcLancRodape').replaceChildren();
    $('orcLancAviso').hidden = true;
    $('orcLancCarregando').hidden = false;
    $('orcLancCsv').disabled = true;
    abrirCamada($('orcLanc'), $('orcLancFundo'));
    var p = new URLSearchParams(consultado.toString()), meu = ++pedidoLanc;  // a empresa e o período da árvore na tela
    p.set('conta_lanc', l.codigo);
    fetch(tela.dataset.urlLancamentos + '?' + p.toString()).then(function (r) {
      return r.json().catch(function () { return { erro: 'Não foi possível buscar agora. Tente de novo.' }; });
    }).then(function (j) {
      if (meu !== pedidoLanc) return;
      if (!j.ok) { avisoLanc(j.erro || 'Não foi possível buscar os lançamentos.'); return; }
      desenharLancamentos(j.dados);
    }).catch(function () {
      if (meu === pedidoLanc) avisoLanc('Sem conexão. Tente de novo.');
    }).finally(function () { if (meu === pedidoLanc) $('orcLancCarregando').hidden = true; });
  }
  function avisoLanc(msg) { $('orcLancAviso').textContent = msg; $('orcLancAviso').hidden = false; }
  function desenharLancamentos(d) {
    lanc = d;
    var tb = $('orcLancCorpo');
    d.linhas.forEach(function (x) {
      var tr = el('tr');
      [x.empresa, dataBr(x.data), x.documento, x.historico, x.centro].forEach(function (v) { tr.appendChild(el('td', '', v)); });
      tr.lastChild.previousSibling.className = 'orc-hist';
      tr.appendChild(el('td', 'num', reais.format(x.valor)));
      tb.appendChild(tr);
    });
    if (!d.linhas.length) {
      var vazio = el('tr', 'tabela-vazia'), td = el('td', '', 'Nenhum lançamento desta conta no período e nos filtros.');
      td.colSpan = 6;
      vazio.appendChild(td);
      tb.appendChild(vazio);
    }
    var tot = el('tr', 'orc-total'), rot = el('td', '', 'Total · ' + d.quantidade + (d.quantidade === 1 ? ' lançamento' : ' lançamentos'));
    rot.colSpan = 5;
    tot.appendChild(rot);
    tot.appendChild(el('td', 'num', reais.format(d.total)));
    $('orcLancRodape').appendChild(tot);
    if (d.cortado) avisoLanc('Mostrando os primeiros ' + d.limite.toLocaleString('pt-BR') + ' de ' + d.quantidade.toLocaleString('pt-BR') +
                             ' lançamentos. O total soma todos; o CSV traz os mostrados.');
    $('orcLancCsv').disabled = !d.linhas.length;
  }
  $('orcLancCsv').addEventListener('click', function () {
    if (!lanc) return;
    baixarCsv(['Empresa', 'Data', 'Documento', 'Histórico', 'Centro', 'Valor'],
              lanc.linhas.map(function (x) { return [x.empresa, dataBr(x.data), x.documento, x.historico, x.centro, x.valor]; }),
              'orcamento_lancamentos_' + lanc.conta + '_' + hoje() + '.csv');
  });

  /* ── Fase 6: DRE em árvore, por mês ── */
  var PREF_FMT = 'orcamento_formato';
  var fmtPref = (function () { try { return JSON.parse(localStorage.getItem(PREF_FMT) || '{}'); } catch (e) { return {}; } })();
  $('orcMil').checked = !!fmtPref.mil;
  $('orcCent').checked = !!fmtPref.cent;
  ['orcMil', 'orcCent'].forEach(function (id) {
    $(id).addEventListener('change', function () {
      fmtPref = { mil: $('orcMil').checked, cent: $('orcCent').checked };
      try { localStorage.setItem(PREF_FMT, JSON.stringify(fmtPref)); } catch (e) { /* sem armazenamento */ }
      if (arv && estado.abrir === 'linha') desenharArvore();
      else if (linhas.length) corpo();
    });
  });
  function num(v) {
    if (v === null || v === undefined) return '';
    var casas = fmtPref.cent ? 2 : 0, x = fmtPref.mil ? v / 1000 : v, f = Math.pow(10, casas);
    x = Math.round(x * f) / f || 0;  // || 0 troca o -0 por 0
    return x.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  }
  var NOMES_MES = ['', 'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];

  function receberArvore(d) {
    arv = d;
    abertos = {};
    d.linhas.forEach(function (l) { if (l.nivel <= 1) abertos[l.id] = true; });  // abre até o grupo do 5º nível
    avisosComuns(d);
    var t = d.total.acumulado, oc = d.total.orcado_comparavel, r = t[1];
    // variação e % contra o orçado dos meses com razão, para mês sem razão não virar desvio
    kpis({ orcado: t[0], realizado: r, variacao: r === null ? null : Math.round((r - oc) * 100) / 100,
           pct: oc && r !== null ? Math.round(r / oc * 1000) / 10 : null }, 'Resultado do período', d.meses_sem_realizado.length);
    $('orcKpis').hidden = false;
    if (d.linhas.length <= 1) { $('orcVazio').hidden = false; return; }
    desenharArvore();
  }

  // meses, Média e Acumulado que a pessoa ocultou pelo menu Colunas; guardado no navegador
  var PREF_ARV = 'orcamento_arv_ocultas', ocultasArv = (function () { try { return JSON.parse(localStorage.getItem(PREF_ARV) || '[]'); } catch (e) { return []; } })();
  function colunas() {
    var todas = todasColunas(), vis = todas.filter(function (c) { return ocultasArv.indexOf(c.rot) === -1; });
    return vis.length ? vis : todas.slice(-1);  // nunca some tudo: sobra o Acumulado
  }
  function abrirColunasArv() {
    var c = $('orcArvColunasCorpo');
    c.replaceChildren();
    todasColunas().forEach(function (col) {
      var rot = el('label', 'ta-coluna'), caixa = el('input');
      caixa.type = 'checkbox';
      caixa.checked = ocultasArv.indexOf(col.rot) === -1;
      caixa.addEventListener('change', function () {
        ocultasArv = ocultasArv.filter(function (k) { return k !== col.rot; });
        if (!caixa.checked) ocultasArv.push(col.rot);
        try { localStorage.setItem(PREF_ARV, JSON.stringify(ocultasArv)); } catch (e) { /* sem armazenamento */ }
        desenharArvore();
      });
      rot.appendChild(caixa);
      rot.appendChild(document.createTextNode(' ' + col.rot));
      c.appendChild(rot);
    });
    $('orcArvPopColunas').classList.add('aberto');
  }
  $('orcArvTodas').addEventListener('click', function () {
    ocultasArv = [];
    try { localStorage.removeItem(PREF_ARV); } catch (e) { /* sem armazenamento */ }
    if (arv) { desenharArvore(); abrirColunasArv(); }
  });
  function todasColunas() {
    var cols = [];
    if (estado.modo === 'evolucao') {
      arv.competencias.forEach(function (c, i) { cols.push({ rot: NOMES_MES[+c.slice(5, 7)] + '/' + c.slice(0, 4), pega: function (l) { return l.meses[i]; } }); });
      cols.push({ rot: 'Média', pega: function (l) { return l.media; }, cmp: function (l) { return l.media_orcado_comparavel; }, extra: true });
    }
    cols.push({ rot: estado.modo === 'evolucao' ? 'Acumulado' : 'Período', pega: function (l) { return l.acumulado; },
                cmp: function (l) { return l.orcado_comparavel; }, extra: estado.modo === 'evolucao' });
    return cols;
  }

  function visivelNaArvore(l, porId) {
    if (filtroArv) return true;
    var p = l.pai;
    while (p) {
      if (!abertos[p]) return false;
      p = porId[p] ? porId[p].pai : null;
    }
    return true;
  }

  function linhasArvore() {
    var porId = {};
    arv.linhas.forEach(function (l) { porId[l.id] = l; });
    if (!filtroArv) return arv.linhas.filter(function (l) { return visivelNaArvore(l, porId); });
    var manter = {}, casou = {};  // com filtro: a linha que casa, os pais dela e as linhas dentro dela
    arv.linhas.forEach(function (l) {
      if (semAcento(l.codigo + ' ' + l.rotulo).indexOf(filtroArv) === -1) return;
      casou[l.id] = true;
      for (var x = l; x; x = porId[x.pai]) manter[x.id] = true;
    });
    arv.linhas.forEach(function (l) {
      for (var x = porId[l.pai]; x; x = porId[x.pai]) if (casou[x.id] && x.id !== 'TOTAL') { manter[l.id] = true; break; }
    });
    return arv.linhas.filter(function (l) { return manter[l.id]; });
  }

  function celula(par, extra, orcCmp) {
    var td = el('td', 'arv-cel' + (extra ? ' arv-extra' : ''));
    if (!par) return td;
    var orc = par[0], real = par[1], topo = el('div', 'arv-par');
    var ref = (orcCmp === undefined || orcCmp === null) ? orc : orcCmp;  // acumulado e média: só meses com razão
    topo.appendChild(el('span', 'arv-orc', num(orc)));
    topo.appendChild(el('span', 'arv-real', real === null ? 'sem dado' : num(real)));
    td.appendChild(topo);
    if (orcCmp !== undefined && orcCmp !== null && orcCmp !== orc) td.title = 'Variação contra o orçado só dos meses com razão (' + num(orcCmp) + ')';
    if (real !== null && (ref || real)) {
      var dif = real - ref, base = el('div', 'arv-var ' + (dif > 0 ? 'pos' : dif < 0 ? 'neg' : 'zero'));
      base.appendChild(el('i', 'ph ' + (dif >= 0 ? 'ph-trend-up' : 'ph-trend-down')));
      base.appendChild(el('span', '', (dif > 0 ? '+' : '') + num(dif)));
      base.appendChild(el('span', 'arv-pct', ref ? (dif >= 0 ? '+' : '') + pctFmt.format(dif / Math.abs(ref) * 100) + '%' : ''));
      td.appendChild(base);
    }
    return td;
  }

  function desenharArvore() {
    if (!arv) return;
    var cols = colunas(), cab = $('orcArvCab'), corpoArv = $('orcArvCorpo');
    $('orcArvTitulo').textContent = arv.rotulo_empresa + ' · ' + arv.rotulo_periodo + (fmtPref.mil ? ' · em R$ mil' : ' · R$');
    var tr1 = el('tr'), tr2 = el('tr', 'arv-sub-cab');
    var th0 = el('th', 'arv-nome', 'Grupo ou conta');
    th0.rowSpan = 2;
    tr1.appendChild(th0);
    cols.forEach(function (c) {
      var th = el('th', 'arv-mes' + (c.extra ? ' arv-extra' : ''), c.rot);
      tr1.appendChild(th);
      var sub = el('th', 'arv-mes-sub' + (c.extra ? ' arv-extra' : ''));
      sub.appendChild(el('span', 'arv-orc', 'Orçado'));
      sub.appendChild(el('span', 'arv-real', 'Realizado'));
      tr2.appendChild(sub);
    });
    var linhaFiltro = el('tr', 'th-filtro');
    var thF = el('th', 'arv-nome'), inp = el('input');
    inp.type = 'text'; inp.placeholder = 'filtrar'; inp.value = filtroArv ? $('orcArvFiltroTexto').value : '';
    inp.setAttribute('aria-label', 'Filtrar grupo ou conta');
    inp.addEventListener('input', function () {
      $('orcArvFiltroTexto').value = inp.value;
      filtroArv = semAcento(inp.value.trim());
      desenharCorpo();
      contagem();
    });
    thF.appendChild(inp);
    linhaFiltro.appendChild(thF);
    cols.forEach(function () { linhaFiltro.appendChild(el('th')); });
    linhaFiltro.hidden = !arvFiltroAberto;
    cab.replaceChildren(tr1, tr2, linhaFiltro);
    function desenharCorpo() {
      corpoArv.replaceChildren();
      var porId = {};
      arv.linhas.forEach(function (l) { porId[l.id] = l; });
      linhasArvore().forEach(function (l) {
        var tr = el('tr', 'arv-n' + l.nivel), td = el('td', 'arv-nome');
        var temFilhos = arv.linhas.some(function (x) { return x.pai === l.id; });
        if (temFilhos && l.nivel > 0) {
          var b = el('button', 'arv-abre');
          b.type = 'button';
          b.setAttribute('aria-expanded', abertos[l.id] || filtroArv ? 'true' : 'false');
          b.setAttribute('aria-label', (abertos[l.id] ? 'Recolher ' : 'Abrir ') + l.rotulo);
          b.appendChild(el('i', 'ph ' + (abertos[l.id] || filtroArv ? 'ph-caret-down' : 'ph-caret-right')));
          b.addEventListener('click', function () { abertos[l.id] = !abertos[l.id]; desenharCorpo(); contagem(); });
          td.appendChild(b);
        } else if (l.nivel > 0) td.appendChild(el('span', 'arv-folha'));
        if (l.nivel === 3 && l.codigo) {  // conta analítica: abre os lançamentos do razão
          var bc = el('button', 'arv-rotulo arv-conta', l.codigo + ' · ' + l.rotulo);
          bc.type = 'button';
          bc.setAttribute('aria-label', 'Ver os lançamentos de ' + l.codigo + ' · ' + l.rotulo);
          bc.addEventListener('click', function () { abrirLancamentos(l); });
          td.appendChild(bc);
        } else td.appendChild(el('span', 'arv-rotulo', (l.codigo ? l.codigo + ' · ' : '') + l.rotulo));
        td.title = (l.codigo ? l.codigo + ' · ' : '') + l.rotulo;
        tr.appendChild(td);
        cols.forEach(function (c) { tr.appendChild(celula(c.pega(l), c.extra, c.cmp ? c.cmp(l) : undefined)); });
        corpoArv.appendChild(tr);
      });
    }
    desenharCorpo();
    contagem();
    $('orcArvoreWrap').hidden = false;
  }

  function contagem() {
    var n = linhasArvore().length;
    $('orcArvContagem').textContent = filtroArv ? n + ' de ' + arv.linhas.length + ' linhas' : '';  // sem filtro, a contagem some
  }

  var arvFiltroAberto = false;
  var menuArv = $('orcArvMenu'), btnArv = $('orcArvMenuBtn');
  btnArv.addEventListener('click', function (e) {
    e.stopPropagation();
    var abrir = !menuArv.classList.contains('aberto');
    fecharTudo();
    if (abrir) { menuArv.classList.add('aberto'); btnArv.setAttribute('aria-expanded', 'true'); }
  });
  document.addEventListener('click', function (e) { if (!e.target.closest('.ta-menu-wrapper')) { menuArv.classList.remove('aberto'); btnArv.setAttribute('aria-expanded', 'false'); } });
  menuArv.addEventListener('click', function (e) {
    var item = e.target.closest('[data-acao]');
    if (!item || !arv) return;
    menuArv.classList.remove('aberto');
    btnArv.setAttribute('aria-expanded', 'false');
    var acao = item.dataset.acao;
    if (acao === 'filtro') {
      arvFiltroAberto = !arvFiltroAberto;
      item.classList.toggle('ativo', arvFiltroAberto);
      if (!arvFiltroAberto) { filtroArv = ''; $('orcArvFiltroTexto').value = ''; }  // fechar limpa
      desenharArvore();
      if (arvFiltroAberto) $('orcArvCab').querySelector('.th-filtro input').focus();
    } else if (acao === 'expandir') { arv.linhas.forEach(function (l) { abertos[l.id] = true; }); desenharArvore(); }
    else if (acao === 'recolher') { abertos = {}; arv.linhas.forEach(function (l) { if (l.nivel === 0) abertos[l.id] = true; }); desenharArvore(); }
    else if (acao === 'colunas') abrirColunasArv();
    else if (acao === 'csv' || acao === 'excel') exportarArvore(acao);
  });

  function exportarArvore(tipo) {
    var cols = colunas(), cab = ['Nível', 'Código', 'Grupo ou conta'];
    cols.forEach(function (c) { cab.push(c.rot + ' orçado', c.rot + ' realizado', c.rot + ' variação'); });
    var linhasExp = linhasArvore().map(function (l) {
      var r = [l.nivel, l.codigo, l.rotulo];
      cols.forEach(function (c) {
        var p = c.pega(l) || [null, null];
        r.push(p[0], p[1], p[1] === null || p[0] === null ? null : Math.round((p[1] - p[0]) * 100) / 100);
      });
      return r;
    });
    var arquivo = 'orcamento_arvore_' + hoje();
    if (tipo === 'csv') { baixarCsv(cab, linhasExp, arquivo + '.csv'); return; }
    fetch(tela.dataset.urlExportar, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome: arquivo, cabecalho: cab, linhas: linhasExp })
    }).then(function (r) { if (!r.ok) throw new Error(); return r.blob(); })
      .then(function (b) { baixar(b, arquivo + '.xlsx'); })
      .catch(function () { aviso('Não foi possível gerar o Excel. Tente o CSV, ou exporte menos meses.', 'erro'); });
  }

  /* ── Fase 8: dashboard (D10: SVG desenhado aqui, sem biblioteca). Realizado em barra cheia, orçado em traço
        de meta: a forma separa as séries além da cor (a paleta Sage & Creme é de croma baixo de propósito).
        Tooltip dentro do próprio SVG, por atributo, e alvo com foco de teclado. ── */
  var SVGNS = 'http://www.w3.org/2000/svg';
  function sv(tag, attrs, classe, texto) {
    var n = document.createElementNS(SVGNS, tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (classe) n.setAttribute('class', classe);
    if (texto !== undefined) n.textContent = texto;
    return n;
  }
  function curto(v) {
    var a = Math.abs(v), s = v < 0 ? '-' : '';
    if (a >= 1e6) return s + 'R$ ' + (a / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi';
    if (a >= 1e3) return s + 'R$ ' + Math.round(a / 1e3).toLocaleString('pt-BR') + ' mil';
    return s + 'R$ ' + Math.round(a).toLocaleString('pt-BR');
  }
  function sinal(v) { return (v > 0 ? '+' : '') + reais.format(v); }
  function passo(bruto) {  // 1, 2 ou 5 vezes potência de 10
    var p = Math.pow(10, Math.floor(Math.log10(bruto || 1))), r = bruto / p;
    return (r <= 1 ? 1 : r <= 2 ? 2 : r <= 5 ? 5 : 10) * p;
  }
  function dica(svg, W) {
    var g = sv('g', {}, 'orc-g-tip'), caixa = sv('rect', { rx: 6 });
    g.appendChild(caixa);
    g.setAttribute('visibility', 'hidden');
    svg.appendChild(g);
    return {
      mostrar: function (x, y, linhasTxt) {
        while (g.childNodes.length > 1) g.removeChild(g.lastChild);
        var larg = Math.min(W - 8, 16 + 6.8 * Math.max.apply(null, linhasTxt.map(function (t) { return t.length; }))), alt = 10 + 17 * linhasTxt.length;
        var px = Math.max(4, Math.min(W - larg - 4, x - larg / 2)), py = Math.max(4, y - alt - 10);
        caixa.setAttribute('x', px); caixa.setAttribute('y', py); caixa.setAttribute('width', larg); caixa.setAttribute('height', alt);
        linhasTxt.forEach(function (t, i) { g.appendChild(sv('text', { x: px + 8, y: py + 19 + 17 * i }, i ? '' : 'orc-g-tip-tit', t)); });
        g.setAttribute('visibility', 'visible');
        g.parentNode.appendChild(g);  // por cima das barras
      },
      esconder: function () { g.setAttribute('visibility', 'hidden'); }
    };
  }
  function alvo(no, rotulo, aoMostrar, tip, aoClicar) {
    no.setAttribute('tabindex', '0');
    no.setAttribute('aria-label', rotulo);
    ['mouseenter', 'focus'].forEach(function (ev) { no.addEventListener(ev, aoMostrar); });
    ['mouseleave', 'blur'].forEach(function (ev) { no.addEventListener(ev, tip.esconder); });
    if (aoClicar) {
      no.setAttribute('role', 'button');
      no.classList.add('orc-g-clica');
      no.addEventListener('click', aoClicar);
      no.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); aoClicar(); } });
    }
  }

  // barra com raio de 4px só na ponta de dados; a base, no zero, fica reta
  function barraV(x, base, ponta, w) {
    var r = Math.min(4, w / 2, Math.abs(base - ponta)), d = ponta < base ? 1 : -1;
    return sv('path', { d: 'M' + x + ' ' + base + 'V' + (ponta + d * r) + 'Q' + x + ' ' + ponta + ' ' + (x + r) + ' ' + ponta +
                           'H' + (x + w - r) + 'Q' + (x + w) + ' ' + ponta + ' ' + (x + w) + ' ' + (ponta + d * r) + 'V' + base + 'Z' });
  }
  function barraH(base, ponta, y, h) {
    var r = Math.min(4, h / 2, Math.abs(ponta - base)), d = ponta > base ? -1 : 1;
    return sv('path', { d: 'M' + base + ' ' + y + 'H' + (ponta + d * r) + 'Q' + ponta + ' ' + y + ' ' + ponta + ' ' + (y + r) +
                           'V' + (y + h - r) + 'Q' + ponta + ' ' + (y + h) + ' ' + (ponta + d * r) + ' ' + (y + h) + 'H' + base + 'Z' });
  }
  function largura(host) { host.replaceChildren(); return Math.max(260, host.clientWidth || 600); }  // mede sem o SVG antigo segurando a célula
  function graficoMensal(host, comps, serie, nome) {
    var W = largura(host), H = 250, L = 70, R = 10, T = 14, B = 30;
    var vals = [0];
    serie.forEach(function (p) { vals.push(p[0]); if (p[1] !== null) vals.push(p[1]); });
    var st = passo((Math.max.apply(null, vals) - Math.min.apply(null, vals)) / 4 || 2500);
    var lo = Math.floor(Math.min.apply(null, vals) / st) * st, hi = Math.ceil(Math.max.apply(null, vals) / st) * st || st;
    var y = function (v) { return T + (hi - v) / (hi - lo) * (H - T - B); };
    var svg = sv('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': nome + ', orçado e realizado por mês' });
    for (var v = lo; v <= hi + st / 2; v += st) {
      svg.appendChild(sv('line', { x1: L, x2: W - R, y1: y(v), y2: y(v) }, Math.abs(v) < st / 2 ? 'orc-g-zero' : 'orc-g-grade'));
      svg.appendChild(sv('text', { x: L - 8, y: y(v) + 4, 'text-anchor': 'end' }, 'orc-g-eixo', curto(Math.abs(v) < st / 2 ? 0 : v)));
    }
    var tip, banda = (W - L - R) / comps.length, larg = Math.min(24, banda * 0.5), pula = banda < 34 ? 2 : 1;
    var colunas = [];
    comps.forEach(function (c, i) {
      var cx = L + banda * (i + 0.5), o = serie[i][0], r = serie[i][1], col = sv('g', {}, 'orc-g-col');
      col.appendChild(sv('rect', { x: cx - banda / 2, y: T, width: banda, height: H - T - B }, 'orc-g-fundo'));
      if (r !== null) {
        var b = barraV(cx - larg / 2, y(0), Math.abs(y(r) - y(0)) < 1 ? y(0) - 1 : y(r), larg);
        b.setAttribute('class', 'orc-g-real');
        col.appendChild(b);
      } else col.appendChild(sv('text', { x: cx, y: y(0) - 6, 'text-anchor': 'middle' }, 'orc-g-nd', banda < 56 ? 's/d' : 'sem dado'));
      col.appendChild(sv('line', { x1: cx - larg * 0.75, x2: cx + larg * 0.75, y1: y(o), y2: y(o) }, 'orc-g-orc'));
      if (i % pula === 0) col.appendChild(sv('text', { x: cx, y: H - 10, 'text-anchor': 'middle' }, 'orc-g-eixo', NOMES_MES[+c.slice(5, 7)]));
      svg.appendChild(col);
      colunas.push([col, cx, o, r, c]);
    });
    tip = dica(svg, W);
    colunas.forEach(function (x) {
      var mes = NOMES_MES[+x[4].slice(5, 7)] + '/' + x[4].slice(0, 4);
      var txt = [mes, 'Orçado ' + reais.format(x[2]), 'Realizado ' + (x[3] === null ? 'sem dado' : reais.format(x[3]))];
      if (x[3] !== null) txt.push('Variação ' + sinal(Math.round((x[3] - x[2]) * 100) / 100));
      alvo(x[0], nome + ' ' + txt.join(', '), function () { tip.mostrar(x[1], y(Math.max(x[2], x[3] || 0, 0)), txt); }, tip);
    });
    host.replaceChildren(svg);
  }

  function graficoDesvios(host, itens, aoClicar, vazio, nome) {
    if (!itens.length) { host.replaceChildren(el('p', 'orc-g-vazio', vazio)); return; }
    var W = largura(host), estreito = W < 560, linha = estreito ? 44 : 32, H = Math.max(96, itens.length * linha + 8);  // cabe o tooltip
    var rotW = estreito ? W * 0.46 : Math.min(260, W * 0.42), valW = estreito ? 70 : 92, x0 = rotW + 10, x1 = W - valW, meio = (x0 + x1) / 2;
    var max = Math.max.apply(null, itens.map(function (d) { return Math.abs(d.valor); })) || 1;
    var svg = sv('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': nome });
    svg.appendChild(sv('line', { x1: meio, x2: meio, y1: 0, y2: H }, 'orc-g-zero'));
    var tip, linhasG = [];
    itens.forEach(function (d, i) {
      var cy = 4 + i * linha + linha / 2, w = Math.max(2, Math.abs(d.valor) / max * (x1 - x0) / 2 - 2), g = sv('g', {}, 'orc-g-col');
      var cabe = Math.floor(rotW / 6.6), corta = function (t) { return t.length > cabe ? t.slice(0, cabe - 1) + '…' : t; };
      g.appendChild(sv('rect', { x: 0, y: cy - linha / 2, width: W, height: linha }, 'orc-g-fundo'));
      if (estreito && d.codigo !== undefined) {  // celular: código numa linha, nome na outra
        g.appendChild(sv('text', { x: rotW, y: cy - 3, 'text-anchor': 'end' }, 'orc-g-rot', corta(d.codigo)));
        g.appendChild(sv('text', { x: rotW, y: cy + 12, 'text-anchor': 'end' }, 'orc-g-eixo', corta(d.nome)));
      } else g.appendChild(sv('text', { x: rotW, y: cy + 4, 'text-anchor': 'end' }, 'orc-g-rot', corta(d.rotulo)));
      var bh = barraH(meio + (d.valor >= 0 ? 1 : -1), meio + (d.valor >= 0 ? 1 + w : -1 - w), cy - 8, 16);
      bh.setAttribute('class', d.valor >= 0 ? 'orc-g-pos' : 'orc-g-neg');
      g.appendChild(bh);
      g.appendChild(sv('text', { x: W - 4, y: cy + 4, 'text-anchor': 'end' }, 'orc-g-val', (d.valor > 0 ? '+' : '') + curto(d.valor)));
      svg.appendChild(g);
      linhasG.push([g, cy, d]);
    });
    tip = dica(svg, W);
    linhasG.forEach(function (x) {
      var d = x[2], txt = [d.rotulo.slice(0, 48), 'Orçado ' + reais.format(d.orcado), 'Realizado ' + reais.format(d.realizado), 'Desvio ' + sinal(d.valor)];
      alvo(x[0], txt.join(', '), function () { tip.mostrar(meio, x[1] - 4, txt); }, tip, function () { aoClicar(d); });
    });
    host.replaceChildren(svg);
  }

  var KPIS_DASH = [['receita', 'receita líquida'], ['custo_despesa', 'custo e despesa'], ['mc', 'margem de contribuição'],
                   ['mc_pct', 'MC %'], ['resultado', 'resultado']];
  function desenharPainel(d) {
    dash = d;
    avisosComuns(d);
    if (d.meses_considerados.length && d.meses_considerados.length < d.competencias.length) {
      aviso('Os indicadores comparam com o orçado só dos meses com razão (' + mesesPorExtenso(d.meses_considerados) +
            '). O orçado do período inteiro é ' + reais.format(d.orcado_periodo) + ' de resultado.');
    }
    var box = $('orcDashKpis');
    box.replaceChildren();
    KPIS_DASH.forEach(function (k) {
      var i = d.indicadores[k[0]], pct = k[0] === 'mc_pct', card = el('div', 'min-kpi' + (k[0] === 'mc' ? ' min-kpi-hl' : ''));
      var fmt = function (v) { return v === null ? 'sem dado' : (pct ? pctFmt.format(v) + '%' : reais.format(v)); };
      card.appendChild(el('span', 'min-kpi-label', k[1]));
      card.appendChild(el('span', 'min-kpi-value', fmt(i.realizado)));
      card.appendChild(el('span', 'min-kpi-sub', 'orçado ' + fmt(i.orcado)));
      var vr = el('span', 'min-kpi-var orc-dk-var');
      if (i.variacao === null) vr.textContent = 'sem realizado';
      else {
        vr.classList.add(i.variacao > 0 ? 'pos' : i.variacao < 0 ? 'neg' : 'zero');
        vr.appendChild(el('i', 'ph ' + (i.variacao >= 0 ? 'ph-trend-up' : 'ph-trend-down')));
        vr.appendChild(el('span', '', ' ' + (pct ? (i.variacao > 0 ? '+' : '') + pctFmt.format(i.variacao) + ' p.p.' : sinal(i.variacao)) +
                                     (i.variacao > 0 ? ' melhor' : i.variacao < 0 ? ' pior' : '')));
      }
      card.appendChild(vr);
      box.appendChild(card);
    });
    var ind = d.indicadores, nada = ['receita', 'custo_despesa', 'resultado'].every(function (k) { return !ind[k].orcado && !ind[k].realizado; }) && !d.orcado_periodo;
    if (nada) { $('orcVazio').hidden = false; return; }  // mesmo estado vazio da tabela
    $('orcDash').hidden = false;
    redesenharPainel();
  }
  function redesenharPainel() {
    if (!dash || $('orcDash').hidden) return;
    graficoMensal($('orcGrafResultado'), dash.competencias, dash.mensal.resultado, 'Resultado');
    graficoMensal($('orcGrafMc'), dash.competencias, dash.mensal.mc, 'Margem de contribuição');
    graficoDesvios($('orcGrafCentro'), dash.desvios_centro.map(function (x) {
      return { rotulo: x.rotulo, valor: x.variacao, orcado: x.orcado, realizado: x.realizado, chave: x.chave };
    }), function (x) { abrirNaDre({ chave: x.chave, rotulo: x.rotulo, campo: 'centro' }); },
       'Nenhum centro com desvio. Amplie o período ou tire um filtro.', 'Maiores desvios por centro de custo');
    graficoDesvios($('orcGrafConta'), dash.desvios_conta.map(function (x) {
      return { rotulo: x.codigo + ' · ' + x.rotulo, valor: x.variacao, orcado: x.orcado, realizado: x.realizado, codigo: x.codigo, nome: x.rotulo };
    }), function (x) { abrirLancamentos({ codigo: x.codigo, rotulo: x.nome }); },
       'Nenhuma conta com desvio. Amplie o período ou tire um filtro.', 'Maiores desvios por conta');
    // corte declarado: com mais de 10, diz quantos existem
    [['orcGrafCentro', dash.desvios_centro.length, dash.total_desvios_centro, 'centros'], ['orcGrafConta', dash.desvios_conta.length, dash.total_desvios_conta, 'contas']]
      .forEach(function (c) {
        var aviso10 = $(c[0]).parentNode.querySelector('.orc-g-corte');
        aviso10.textContent = c[2] > c[1] ? 'Mostrando os ' + c[1] + ' maiores de ' + c[2] + ' ' + c[3] + ' com desvio.' : '';
      });
  }
  var esperaRedesenho = null;
  window.addEventListener('resize', function () { clearTimeout(esperaRedesenho); esperaRedesenho = setTimeout(redesenharPainel, 150); });

  $('orcConsultar').addEventListener('click', consultar);
  consultar();
})();
