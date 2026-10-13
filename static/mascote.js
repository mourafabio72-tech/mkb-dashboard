/* mascote.js: o "Oi!" do robô do Pergunte à IA (2026-10-13).
   Uma vez por sessão do navegador; some sozinho em 9 s. Sem sessionStorage
   (aba anônima, bloqueio), ele só cumprimenta toda vez: nada quebra. */
(function () {
  'use strict';
  var saudacao = document.querySelector('[data-ia-saudacao]');
  if (!saudacao) { return; }
  var CHAVE = 'finhub-ia-saudou';
  var saudou = false;
  try { saudou = sessionStorage.getItem(CHAVE) === '1'; } catch (e) { saudou = false; }
  if (saudou) { return; }
  setTimeout(function () { saudacao.hidden = false; }, 1200);
  setTimeout(function () { saudacao.hidden = true; }, 9000);
  try { sessionStorage.setItem(CHAVE, '1'); } catch (e) { /* sem armazenamento, segue */ }
})();
