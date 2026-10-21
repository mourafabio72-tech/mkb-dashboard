/* Orçado x Realizado (Fase 4). Consulta /orcamento/dados e desenha indicadores, avisos e a
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
  var linhas = [], ordem = null, ocupado = false, estado = { modo: 'mes', abrir: 'linha' };

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
  function texto(col, l) {
    if (col.chave === 'rotulo') return l.rotulo;
    if (col.chave === 'pct') return l.pct === null ? 'sem orçado' : pctFmt.format(l.pct) + '%';
    return reais.format(l[col.chave]);
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
  grupo('orcModo', 'modo');
  grupo('orcAbrir', 'abrir', function () { $('orcLinhaGrupo').hidden = estado.abrir === 'linha'; });

  /* ── consulta ── */
  function parametros() {
    var p = new URLSearchParams();
    ['empresa', 'ano', 'mes', 'servico', 'coordenador', 'filial', 'centro'].forEach(function (c) {
      var v = $('orc_' + c).value;
      if (v) p.set(c, v);
    });
    p.set('modo', estado.modo);
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
    travar(true);
    $('orcAvisos').replaceChildren();
    $('orcTabelaWrap').hidden = true;
    $('orcVazio').hidden = true;
    $('orcKpis').hidden = true;
    $('orcCarregando').hidden = false;
    fetch(tela.dataset.urlDados + '?' + parametros().toString()).then(function (r) {
      return r.json().catch(function () { return { erro: 'Resposta inesperada do servidor (' + r.status + ').' }; });
    }).then(function (j) {
      if (!j.ok) { aviso(j.erro || 'Não foi possível calcular.', 'erro'); return; }
      desenhar(j.dados);
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

  function desenhar(d) {
    if (d.sem_orcamento) aviso('Não há orçamento importado para ' + d.rotulo_empresa + ' em ' + d.ano + '. O orçado aparece zerado.');
    Object.keys(d.sem_razao_por_empresa || {}).forEach(function (sigla) {
      aviso('Sem razão importado da ' + sigla + ' em ' + mesesPorExtenso(d.sem_razao_por_empresa[sigla]) +
            '. O realizado desse período fica incompleto.');
    });
    if (d.empresa === 'consolidado' && d.eliminado_equivalencia) {
      aviso('Consolidado: equivalência patrimonial da Gnileb eliminada (' + reais.format(Math.abs(d.eliminado_equivalencia)) +
            ' em Outros Resultados), igual à DRE consolidada.');
    }
    if (d.abrir_por !== 'linha' && d.empresa !== 'mkb') {
      aviso('O razão da Gnileb não tem centro de custo: o realizado dela aparece em Sem centro de custo.');
    }
    kpis(d);
    // linha da DRE zerada no orçado e no realizado sai da grade; subtotal fica, para a DRE ler inteira
    linhas = d.linhas.filter(function (l) { return l.orcado || l.realizado || (l.tipo && l.tipo.indexOf('grupo') !== 0); })
      .map(function (l, i) { l._i = i; return l; });
    ordem = null;
    $('orcThRotulo').textContent = d.dimensao;
    COLUNAS[0].titulo = d.dimensao;
    var recorte = d.linha_dre ? ' · ' + (rotuloLinha(d.linha_dre) || d.linha_dre) : '';
    $('orcTitulo').textContent = d.rotulo_empresa + ' · ' + d.rotulo_mes + (d.modo === 'acumulado' ? ' (acumulado no ano)' : '') + recorte;
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

  function kpis(d) {
    var semLinha = d.linhas.some(function (l) { return l.id === 'SEM_LINHA'; });
    var t = d.total, base = d.linha_dre ? rotuloLinha(d.linha_dre) : (semLinha ? 'Resultado, com as contas sem linha' : 'Resultado líquido');
    var valores = {
      orcado: [reais.format(t.orcado), base],
      realizado: [reais.format(t.realizado), d.meses_sem_realizado.length ? 'período com mês sem razão' : base],
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

  $('orcConsultar').addEventListener('click', consultar);
  consultar();
})();
