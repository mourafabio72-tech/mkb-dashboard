/* ia.js: Pergunte à IA (/ia) e Configuração da IA (/config/ia).
   Regra de saída (Mapa_de_Conceitos, AI Security): texto vindo da IA ou do
   servidor entra SEMPRE por textContent. Nada de innerHTML neste arquivo.
   O token CSRF entra sozinho no fetch pelo patch do base.html. */
(function () {
  'use strict';

  function el(tag, cls, texto) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (texto !== undefined && texto !== null) e.textContent = texto;
    return e;
  }
  function clonar(id) {
    return document.getElementById(id).content.firstElementChild.cloneNode(true);
  }
  function limpar(no) { while (no.firstChild) no.removeChild(no.firstChild); }
  function brl(fmt) { return 'R$ ' + fmt; }

  /* ── Toggle tipo 2 (radiogroup) ─────────────────────────────────────── */
  // radiogroup ARIA: só a opção marcada entra no Tab; setas trocam a escolha
  function ligarToggle(grupo, aoMudar) {
    var botoes = Array.prototype.slice.call(grupo.querySelectorAll('button'));
    function escolher(b, focar) {
      botoes.forEach(function (x) {
        var on = x === b;
        x.classList.toggle('on', on);
        x.setAttribute('aria-checked', on ? 'true' : 'false');
        x.tabIndex = on ? 0 : -1;
      });
      if (focar) b.focus();
      aoMudar(b);
    }
    botoes.forEach(function (b, i) {
      b.tabIndex = b.classList.contains('on') ? 0 : -1;
      b.addEventListener('click', function () { escolher(b, false); });
      b.addEventListener('keydown', function (e) {
        var d = (e.key === 'ArrowRight' || e.key === 'ArrowDown') ? 1 :
                (e.key === 'ArrowLeft' || e.key === 'ArrowUp') ? -1 : 0;
        if (!d) return;
        e.preventDefault();
        escolher(botoes[(i + d + botoes.length) % botoes.length], true);
      });
    });
  }

  /* ══ Tela /ia ═══════════════════════════════════════════════════════════ */
  var form = document.getElementById('iaForm');
  if (form) {
    var campo = document.getElementById('iaPergunta');
    var botao = document.getElementById('iaEnviar');
    var area = document.getElementById('iaResultado');
    var contador = document.getElementById('iaContador');
    var avisoAnalisar = document.getElementById('iaAvisoAnalisar');
    var modo = 'perguntar';
    var ocupado = false;

    ligarToggle(document.getElementById('iaModo'), function (b) {
      modo = b.dataset.modo;
      avisoAnalisar.hidden = modo !== 'analisar';
    });

    function contar() {
      var n = campo.value.length;
      contador.textContent = n > 250 ? n + ' de 300 caracteres' : '';
    }
    campo.addEventListener('input', contar);

    document.querySelectorAll('.ia-exemplo').forEach(function (b) {
      b.addEventListener('click', function () {
        if (ocupado) return;   // não troca a pergunta enquanto a anterior responde
        campo.value = b.textContent.trim();
        contar();
        enviar();
      });
    });

    function mostrarErro(msg) {
      limpar(area);
      var caixa = el('div', 'ia-erro');
      var ic = el('i', 'ph ph-warning-circle');
      ic.setAttribute('aria-hidden', 'true');
      caixa.appendChild(ic);
      caixa.appendChild(el('span', null, msg));
      area.appendChild(caixa);
    }

    function tabela(colunas, linhas, total) {
      var wrap = el('div', 'ia-tabela-wrap');
      var t = el('table', 'ia-tabela');
      var thead = el('thead');
      var trh = el('tr');
      colunas.forEach(function (c, i) {
        var th = el('th', i === colunas.length - 1 ? 'ia-num' : null, c);
        th.setAttribute('scope', 'col');
        trh.appendChild(th);
      });
      thead.appendChild(trh);
      t.appendChild(thead);
      var tb = el('tbody');
      linhas.forEach(function (l) {
        var tr = el('tr', l.outros ? 'ia-outros' : null);
        tr.appendChild(el('td', null, l.rotulo));
        tr.appendChild(el('td', 'ia-num', brl(l.valor_fmt)));
        tb.appendChild(tr);
      });
      if (total) {
        var tt = el('tr', 'ia-total');
        tt.appendChild(el('td', null, 'Total'));
        tt.appendChild(el('td', 'ia-num', brl(total)));
        tb.appendChild(tt);
      }
      t.appendChild(tb);
      wrap.appendChild(t);
      return wrap;
    }

    function renderizar(r) {
      limpar(area);
      if (r.tipo === 'nao_entendi') { area.appendChild(clonar('iaMoldeNaoEntendi')); return; }
      if (r.tipo === 'vazio') {
        var v = clonar('iaMoldeVazio');
        v.querySelector('[data-entendi]').textContent = r.entendi || '';
        if (r.mensagem) v.querySelector('.vz-sub').textContent = r.mensagem;
        area.appendChild(v);
        return;
      }
      var c = clonar('iaMoldeResultado');
      c.querySelector('[data-entendi]').textContent = r.entendi || '';
      var corpo = c.querySelector('[data-corpo]');
      if (r.tipo === 'numero') {
        corpo.appendChild(el('div', 'ia-numero-rotulo', r.rotulo || ''));
        corpo.appendChild(el('div', 'ia-numero', brl(r.valor_fmt)));
      } else if (r.tipo === 'tabela') {
        c.querySelector('[data-contagem]').textContent = r.contagem_rotulo || '';
        corpo.appendChild(tabela(r.colunas || ['Item', 'Valor'], r.linhas || [], r.total_fmt));
      } else if (r.tipo === 'comparativo') {
        var linhas = (r.linhas || []).slice();
        var pct = r.variacao_pct === null || r.variacao_pct === undefined ? '' :
          ' (' + String(r.variacao_pct).replace('.', ',') + '%)';
        linhas.push({ rotulo: 'Variação' + pct, valor_fmt: r.variacao_fmt });
        corpo.appendChild(el('div', 'ia-numero-rotulo', r.rotulo || ''));
        corpo.appendChild(tabela(['Mês', 'Valor'], linhas, null));
      }
      if (r.aviso) {
        var av = c.querySelector('[data-aviso]');
        av.textContent = r.aviso;
        av.hidden = false;
      }
      if (r.analise) {
        c.querySelector('[data-analise-texto]').textContent = r.analise;
        c.querySelector('[data-analise]').hidden = false;
      }
      if (r.ver_tudo) {
        c.querySelector('[data-ver-tudo]').setAttribute('href', r.ver_tudo);
        c.querySelector('[data-rodape]').hidden = false;
      }
      area.appendChild(c);
    }

    var ESPERA_MAX = 75000;   // Analisar faz duas chamadas de até 30 s cada
    function enviar() {
      var pergunta = campo.value.trim();
      if (!pergunta) { campo.focus(); return; }
      if (ocupado) return;
      if (area.dataset.semChave) { limpar(area); area.appendChild(clonar('iaMoldeSemChave')); return; }
      ocupado = true;
      botao.disabled = true;

      limpar(area);
      var load = clonar('iaMoldeLoading');
      var txt = load.querySelector('.loading-text');
      var sub = load.querySelector('.loading-sub');
      area.appendChild(load);
      var t0 = Date.now();
      var fases = modo === 'analisar'
        ? ['Lendo sua pergunta...', 'Somando os lançamentos...', 'Escrevendo a análise dos totais...']
        : ['Lendo sua pergunta...', 'Somando os lançamentos...'];
      var relogio = setInterval(function () {
        var s = Math.floor((Date.now() - t0) / 1000);
        txt.textContent = fases[Math.min(fases.length - 1, Math.floor(s / 3))];
        if (s >= 10) {
          sub.hidden = false;
          sub.textContent = s + ' segundos. Pergunta longa ou modo Analisar pode levar até um minuto.';
        }
      }, 500);
      var ctrl = window.AbortController ? new AbortController() : null;
      var corte = ctrl ? setTimeout(function () { ctrl.abort(); }, ESPERA_MAX) : null;

      fetch(modo === 'analisar' ? '/ia/analisar' : '/ia/perguntar', {
        method: 'POST',
        signal: ctrl ? ctrl.signal : undefined,
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ pergunta: pergunta })
      }).then(function (resp) {
        return resp.json().then(function (j) { return { status: resp.status, j: j }; },
          function () { return { status: resp.status, j: null }; });
      }).then(function (x) {
        if (!x.j) {
          mostrarErro(x.status === 400 ? 'A página ficou velha. Recarregue e pergunte de novo.' :
                      x.status >= 500 ? 'O FinHub não respondeu agora. Tente de novo em instantes.' :
                      'Sua sessão expirou. Recarregue a página e entre de novo.');
          return;
        }
        if (x.status === 409) { limpar(area); area.appendChild(clonar('iaMoldeSemChave')); return; }
        if (x.status !== 200) { mostrarErro(x.j.erro || 'Não consegui responder agora. Tente de novo.'); return; }
        renderizar(x.j);
      }).catch(function (e) {
        mostrarErro(e && e.name === 'AbortError'
          ? 'A resposta passou de um minuto. Tente de novo, ou faça uma pergunta mais curta.'
          : 'Sem conexão com o FinHub. Confira a internet e tente de novo.');
      }).finally(function () {
        clearInterval(relogio);
        if (corte) clearTimeout(corte);
        ocupado = false;
        botao.disabled = false;
      });
    }

    form.addEventListener('submit', function (e) { e.preventDefault(); enviar(); });
    contar();
    if (campo.value.trim()) enviar();   // veio da caixa do dashboard (/ia?q=...)
    else area.appendChild(clonar('iaMoldeInicial'));
  }

  /* ══ Tela /config/ia ════════════════════════════════════════════════════ */
  var cfg = document.getElementById('iaConfig');
  if (cfg) {
    var ativo = cfg.querySelector('[data-ia-ativo]');
    ligarToggle(document.getElementById('iaAtivo'), function (b) {
      ativo.value = b.dataset.provedor;
    });
    cfg.querySelectorAll('[data-testar]').forEach(function (b) {
      b.addEventListener('click', function () {
        var prov = b.dataset.testar;
        var msg = cfg.querySelector('[data-teste-msg="' + prov + '"]');
        b.disabled = true;
        msg.className = 'ia-config-teste';
        limpar(msg);
        var gira = el('i', 'ph ph-spinner-gap');
        gira.setAttribute('aria-hidden', 'true');
        msg.appendChild(gira);
        msg.appendChild(document.createTextNode('Testando a conexão com a ' + b.dataset.nome + '...'));
        fetch('/config/ia/testar', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ provedor: prov })
        }).then(function (r) { return r.json(); })
          .then(function (j) {
            msg.className = 'ia-config-teste ' + (j.ok ? 'ok' : 'erro');
            msg.textContent = j.mensagem || '';
          })
          .catch(function () {
            msg.className = 'ia-config-teste erro';
            msg.textContent = 'Sem resposta do FinHub. Recarregue a página e teste de novo.';
          })
          .finally(function () { b.disabled = false; });
      });
    });
  }
})();
