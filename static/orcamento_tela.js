/* Orçado x Realizado (Fases 4 e 6). Linhas da DRE: /orcamento/arvore, em árvore e por mês.
   Outras aberturas: /orcamento/dados, que desenha indicadores, avisos e a
   tabela com o menu sanduíche (Padrao_Tabela): Filtro por coluna, Ordenar, Colunas, Exportar CSV,
   Exportar Excel. A tabela vem inteira (algumas centenas de linhas no máximo), então filtro,
   ordem e exportação rodam no navegador e só sobre o que está visível. Texto só por textContent. */
(function () {
  var tela = document.getElementById('orcTela');
  if (!tela) return;
  var $ = function (id) { return document.getElementById(id); };
  var reais = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  var pctFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var COLUNAS = [
    { chave: 'rotulo', titulo: 'Linha da DRE', num: false },
    { chave: 'orcado', titulo: 'Orçado', num: true },
    { chave: 'realizado', titulo: 'Realizado', num: true },
    { chave: 'variacao', titulo: 'Variação', num: true },
    { chave: 'pct', titulo: '% realizado', num: true }
  ];
  var PREF = 'orcamento_tabela';
  // escada: colunas escondidas guardadas no navegador (localStorage); o FinHub não tem tabela de
  // preferência por usuário. Subir para o banco quando outra tela do FinHub precisar de preferência.
  var escondidas = lerPref();
  var linhas = [], ordem = null, ocupado = false, estado = { modo: 'evolucao', abrir: 'linha' };
  var arv = null, abertos = {}, filtroArv = '';

  function el(tag, classe, texto) {
    var n = document.createElement(tag);
    if (classe) n.className = classe;
    if (texto !== undefined && texto !== null) n.textContent = texto;
    return n;
  }
  function semAcento(t) { return String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }
  function lerPref() { try { return JSON.parse(localStorage.getItem(PREF) || '[]'); } catch (e) { return []; } }
  function gravarPref() { try { localStorage.setItem(PREF, JSON.stringify(escondidas)); } catch (e) { /* sem armazenamento */ } }
  function hoje() {
    var d = new Date(), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  }
  function texto(col, l) {
    if (col.chave === 'rotulo') return l.rotulo;
    if (col.chave === 'pct') return l.pct === null ? 'sem orçado' : pctFmt.format(l.pct) + '%';
    return 'R$ ' + num(l[col.chave]) + (fmtPref.mil ? ' mil' : '');  // segue o ÷ 1.000 e os centavos da faixa de opções
  }

  /* ── seletores tipo 1 e tipo 2 (Padrao_Toggle_Tipos) ── */
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
      if (!b || ocupado) return;
      $(id).querySelectorAll('button').forEach(function (x) {
        x.classList.toggle('on', x === b);
        x.setAttribute('aria-checked', x === b ? 'true' : 'false');
      });
      estado[chave] = b.dataset.valor;
      if (aoMudar) aoMudar();
    });
  }
  grupo('orcModo', 'modo', function () { if (arv && estado.abrir === 'linha') desenharArvore(); });
  grupo('orcAbrir', 'abrir', function () { $('orcLinhaGrupo').hidden = estado.abrir === 'linha'; });

  /* ── consulta ── */
  function parametros() {
    var p = new URLSearchParams();
    ['empresa', 'ano', 'de', 'ate', 'servico', 'coordenador', 'filial', 'centro'].forEach(function (c) {
      var v = $('orc_' + c).value;
      if (v) p.set(c, v);
    });
    p.set('mes', $('orc_ate').value);
    p.set('abrir_por', estado.abrir);
    if (estado.abrir !== 'linha' && $('orc_linha').value) p.set('linha', $('orc_linha').value);
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
    if (+$('orc_de').value > +$('orc_ate').value) { aviso('O mês inicial vem depois do final.', 'erro'); return; }
    travar(true);
    $('orcTabelaWrap').hidden = true;
    $('orcArvoreWrap').hidden = true;
    $('orcVazio').hidden = true;
    $('orcKpis').hidden = true;
    $('orcCarregando').hidden = false;
    var naArvore = estado.abrir === 'linha';
    fetch((naArvore ? tela.dataset.urlArvore : tela.dataset.urlDados) + '?' + parametros().toString()).then(function (r) {
      return r.json().catch(function () { return { erro: 'Resposta inesperada do servidor (' + r.status + ').' }; });
    }).then(function (j) {
      if (!j.ok) { aviso(j.erro || 'Não foi possível calcular.', 'erro'); return; }
      if (naArvore) receberArvore(j.dados); else desenhar(j.dados);
    }).catch(function () {
      aviso('Sem conexão com o servidor. Tente de novo.', 'erro');
    }).finally(function () {
      $('orcCarregando').hidden = true;
      travar(false);
    });
  }

  function aviso(msg, tipo) {
    $('orcAvisos').appendChild(el('p', 'orc-aviso' + (tipo ? ' ' + tipo : ''), msg));
  }

  function mesesPorExtenso(lista) {
    var nomes = ['', 'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
    return lista.map(function (c) { return nomes[+c.slice(5, 7)] + '/' + c.slice(0, 4); }).join(', ');
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

  function desenhar(d) {
    avisosComuns(d);
    if (d.abrir_por !== 'linha' && d.empresa !== 'mkb') {
      aviso('O razão da Gnileb não tem centro de custo: o realizado dela aparece em Sem centro de custo.');
    }
    if (estado.modo === 'evolucao') aviso('A evolução mês a mês vale para Linhas da DRE; nesta abertura, o valor é a soma do período.');
    var semLinha = d.linhas.some(function (l) { return l.id === 'SEM_LINHA'; });
    kpis(d.total, d.linha_dre ? rotuloLinha(d.linha_dre) : (semLinha ? 'Resultado, com as contas sem linha' : 'Resultado líquido'),
         d.meses_sem_realizado.length);
    // linha da DRE zerada no orçado e no realizado sai da grade; subtotal fica, para a DRE ler inteira
    linhas = d.linhas.filter(function (l) { return l.orcado || l.realizado || (l.tipo && l.tipo.indexOf('grupo') !== 0); })
      .map(function (l, i) { l._i = i; return l; });
    ordem = null;
    $('orcThRotulo').textContent = d.dimensao;
    COLUNAS[0].titulo = d.dimensao;
    var recorte = d.linha_dre ? ' · ' + (rotuloLinha(d.linha_dre) || d.linha_dre) : '';
    $('orcTitulo').textContent = d.rotulo_empresa + ' · ' + d.rotulo_mes + recorte;
    $('orcKpis').hidden = false;
    if (!linhas.length || (!d.total.orcado && !d.total.realizado)) {
      $('orcVazio').hidden = false;
      return;
    }
    $('orcTabelaWrap').hidden = false;
    corpo();
  }

  function rotuloLinha(id) {
    var opt = document.querySelector('.selectbusca[data-name="linha"] .sb-opt[data-value="' + CSS.escape(id) + '"]');
    return opt ? opt.textContent : '';
  }

  function kpis(t, base, mesesSem) {
    var valores = {
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
        card.classList.toggle('pos', t.variacao > 0);
        card.classList.toggle('neg', t.variacao < 0);
      }
    });
  }

  /* ── tabela ── */
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

  function corpo() {
    var tb = $('orcCorpo'), lista = visiveis();
    tb.replaceChildren();
    lista.forEach(function (l) {
      var tr = el('tr', l.tipo && l.tipo !== 'grupo' && l.tipo !== 'grupo_pos' ? 'orc-sub ' + l.tipo : '');
      COLUNAS.forEach(function (c) {
        var td = el('td', c.num ? 'num' : '', texto(c, l));
        if (c.chave === 'variacao' && l.variacao) td.classList.add(l.variacao > 0 ? 'pos' : 'neg');
        td.hidden = escondidas.indexOf(c.chave) !== -1;
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    });
    if (!lista.length) {
      var tr = el('tr', 'tabela-vazia'), td = el('td', '', 'Nenhuma linha com esse filtro.');
      td.colSpan = COLUNAS.length;
      tr.appendChild(td);
      tb.appendChild(tr);
    }
    document.querySelectorAll('#orcTabela th[data-col]').forEach(function (th) {
      th.hidden = escondidas.indexOf(th.dataset.col) !== -1;
      if (!th.parentNode.classList.contains('th-titulos')) return;
      var pos = (ordem || []).map(function (o) { return o.chave; }).indexOf(th.dataset.col), o = (ordem || [])[pos];
      th.classList.toggle('ord-asc', !!o && !o.desc);
      th.classList.toggle('ord-desc', !!o && o.desc);
      th.dataset.ordem = ordem && ordem.length > 1 && o ? String(pos + 1) : '';
    });
    var filtrando = Object.keys(filtros()).length;
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
      linha.appendChild(el('span', '', col.titulo));
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
      rot.appendChild(document.createTextNode(' ' + col.titulo));
      c.appendChild(rot);
    });
    $('orcPopColunas').classList.add('aberto');
  }

  /* ── exportação: só as linhas e colunas visíveis ── */
  function tabelaVisivel() {
    var cols = COLUNAS.filter(function (c) { return escondidas.indexOf(c.chave) === -1; });
    return {
      cab: cols.map(function (c) { return c.titulo; }),
      linhas: visiveis().map(function (l) {
        return cols.map(function (c) { return c.chave === 'rotulo' ? l.rotulo : l[c.chave]; });
      })
    };
  }
  function baixar(blob, nome) {
    var a = el('a');
    a.href = URL.createObjectURL(blob);
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }
  function exportarCsv() {
    var t = tabelaVisivel(), campo = function (v) {
      if (v === null || v === undefined) return '';
      if (typeof v === 'number') return String(v).replace('.', ',');
      var s = String(v);
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
      return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
    };
    var texto = [t.cab].concat(t.linhas).map(function (l) { return l.map(campo).join(';'); }).join('\r\n');
    baixar(new Blob(['﻿' + texto], { type: 'text/csv;charset=utf-8' }), PREF + '_' + hoje() + '.csv');
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
    var t = d.total.acumulado, oc = d.total.orcado_comparavel, r = t[1] === null ? 0 : t[1];
    // variação e % contra o orçado dos meses com razão, para mês sem razão não virar desvio
    kpis({ orcado: t[0], realizado: r, variacao: Math.round((r - oc) * 100) / 100,
           pct: oc ? Math.round(r / oc * 1000) / 10 : null }, 'Resultado do período', d.meses_sem_realizado.length);
    $('orcKpis').hidden = false;
    if (d.linhas.length <= 1) { $('orcVazio').hidden = false; return; }
    desenharArvore();
  }

  function colunas() {
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
        td.appendChild(el('span', 'arv-rotulo', (l.codigo ? l.codigo + ' · ' : '') + l.rotulo));
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
    var nome = 'orcamento_arvore_' + hoje();
    if (tipo === 'csv') {
      var campo = function (v) {
        if (v === null || v === undefined) return '';
        if (typeof v === 'number') return String(v).replace('.', ',');
        var s = String(v);
        if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
        return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
      };
      var txt = [cab].concat(linhasExp).map(function (l) { return l.map(campo).join(';'); }).join('\r\n');
      baixar(new Blob(['\ufeff' + txt], { type: 'text/csv;charset=utf-8' }), nome + '.csv');
      return;
    }
    fetch(tela.dataset.urlExportar, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome: nome, cabecalho: cab, linhas: linhasExp })
    }).then(function (r) { if (!r.ok) throw new Error(); return r.blob(); })
      .then(function (b) { baixar(b, nome + '.xlsx'); })
      .catch(function () { aviso('Não foi possível gerar o Excel. Tente o CSV, ou exporte menos meses.', 'erro'); });
  }

  $('orcConsultar').addEventListener('click', consultar);
  consultar();
})();
