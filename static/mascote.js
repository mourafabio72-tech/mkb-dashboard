/* mascote.js: o robô do Pergunte à IA e a janela de conversa (2026-10-13).
   O "Oi!" aparece uma vez por sessão do navegador e some sozinho em 9 s. Sem
   sessionStorage (aba anônima, bloqueio), ele só cumprimenta toda vez.
   A janela conversa pelo /ia/conversar (2026-10-14, o modelo do FinControl): a
   IA responde em texto, com o histórico desta página (nada fica gravado). O CSRF
   entra sozinho pelo patch de fetch do base.html.
   Regra de saída (a mesma do ia.js): texto vindo da IA ou do servidor entra
   SEMPRE por textContent. Nada de innerHTML neste arquivo. */
(function () {
  'use strict';

  var saudacao = document.querySelector('[data-ia-saudacao]');
  var janela = document.querySelector('[data-ia-janela]');

  function esconderSaudacao() { if (saudacao) { saudacao.hidden = true; } }
  if (saudacao) {
    var CHAVE = 'finhub-ia-saudou';
    var saudou = false;
    try { saudou = sessionStorage.getItem(CHAVE) === '1'; } catch (e) { saudou = false; }
    if (!saudou) {
      setTimeout(function () { saudacao.hidden = false; }, 1200);
      setTimeout(esconderSaudacao, 9000);
      try { sessionStorage.setItem(CHAVE, '1'); } catch (e) { /* sem armazenamento, segue */ }
    }
  }
  if (!janela) { return; }

  var conversa = janela.querySelector('[data-ia-conversa]');
  var form = janela.querySelector('[data-ia-form]');
  var texto = janela.querySelector('[data-ia-texto]');
  var enviar = janela.querySelector('[data-ia-enviar]');
  var sugestoes = janela.querySelector('[data-ia-sugestoes]');
  var roboDoCabecalho = janela.querySelector('.ia-janela-cab .rb');
  var ocupado = false;

  function el(tag, cls, conteudo) {
    var e = document.createElement(tag);
    if (cls) { e.className = cls; }
    if (conteudo !== undefined && conteudo !== null) { e.textContent = conteudo; }
    return e;
  }
  function icone(nome) {
    var i = el('i', 'ph ' + nome);
    i.setAttribute('aria-hidden', 'true');
    return i;
  }
  function brl(fmt) { return 'R$ ' + fmt; }
  function rolar() { conversa.scrollTop = conversa.scrollHeight; }

  /* A pergunta da pessoa, à direita. */
  function balaoPessoa(t) {
    conversa.appendChild(el('div', 'ia-msg ia-msg-pessoa', t));
    rolar();
  }
  /* A resposta, à esquerda, com a cabeça do robô ao lado. Devolve o balão,
     para o "Lendo sua pergunta..." ser trocado pela resposta no mesmo lugar. */
  function balaoIa() {
    var linha = el('div', 'ia-linha');
    if (roboDoCabecalho) { linha.appendChild(roboDoCabecalho.cloneNode(true)); }
    var b = el('div', 'ia-msg ia-msg-ia');
    linha.appendChild(b);
    conversa.appendChild(linha);
    rolar();
    return b;
  }
  function limpar(no) { while (no.firstChild) { no.removeChild(no.firstChild); } }

  /* A resposta da IA, em texto, linha a linha. */
  function escrever(b, texto) {
    limpar(b);
    String(texto).split('\n').forEach(function (linha, i) {
      if (i) { b.appendChild(document.createElement('br')); }
      b.appendChild(document.createTextNode(linha));
    });
  }

  function erro(b, msg) {
    limpar(b);
    b.classList.add('ia-msg-erro');
    b.appendChild(el('span', null, msg));
  }

  var historico = [];
  var ESPERA_MAX = 60000;
  function perguntar() {
    var pergunta = texto.value.trim();
    if (!pergunta || ocupado) { return; }
    ocupado = true;
    enviar.disabled = true;
    sugestoes.hidden = true;
    balaoPessoa(pergunta);
    texto.value = '';
    var b = balaoIa();
    b.classList.add('ia-msg-pensando');
    b.textContent = 'Lendo sua pergunta...';
    var ctrl = window.AbortController ? new AbortController() : null;
    var corte = ctrl ? setTimeout(function () { ctrl.abort(); }, ESPERA_MAX) : null;
    fetch('/ia/conversar', {
      method: 'POST',
      signal: ctrl ? ctrl.signal : undefined,
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ pergunta: pergunta, historico: historico })
    }).then(function (resp) {
      return resp.json().then(function (j) { return { status: resp.status, j: j }; },
        function () { return { status: resp.status, j: null }; });
    }).then(function (x) {
      b.classList.remove('ia-msg-pensando');
      if (!x.j) {
        erro(b, x.status === 400 ? 'A página ficou velha. Recarregue e pergunte de novo.' :
                x.status >= 500 ? 'O FinHub não respondeu agora. Tente de novo em instantes.' :
                'Sua sessão expirou. Recarregue a página e entre de novo.');
        return;
      }
      if (x.status === 409) { erro(b, 'A IA não está configurada. Peça a um administrador para salvar a chave em Configuração da IA.'); return; }
      if (x.status !== 200) { erro(b, x.j.erro || 'Não consegui responder agora. Tente de novo.'); return; }
      escrever(b, x.j.resposta);
      historico.push({ papel: 'usuario', texto: pergunta }, { papel: 'assistente', texto: x.j.resposta });
      historico = historico.slice(-4);
    }).catch(function (e) {
      b.classList.remove('ia-msg-pensando');
      erro(b, e && e.name === 'AbortError'
        ? 'A resposta demorou demais. Tente de novo, ou faça uma pergunta mais curta.'
        : 'Sem conexão com o FinHub. Confira a internet e tente de novo.');
    }).then(function () {
      if (corte) { clearTimeout(corte); }
      ocupado = false;
      enviar.disabled = false;
      rolar();
      texto.focus();
    });
  }

  function abrir(e) {
    if (e) { e.preventDefault(); }
    esconderSaudacao();
    janela.hidden = false;
    texto.focus();
  }
  function fechar() { janela.hidden = true; }

  document.querySelectorAll('[data-ia-abrir]').forEach(function (a) { a.addEventListener('click', abrir); });
  janela.querySelector('[data-ia-fechar]').addEventListener('click', fechar);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !janela.hidden) { fechar(); } });
  sugestoes.addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) { return; }
    texto.value = b.textContent;
    perguntar();
  });
  texto.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); perguntar(); }
  });
  form.addEventListener('submit', function (e) { e.preventDefault(); perguntar(); });
})();
