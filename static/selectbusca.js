/* SelectBusca (Componente_SelectBusca): substitui a caixa de seleção nativa nas telas novas.
   Marcação: div.selectbusca[data-name] > input[type=hidden] + button.sb-display(.sb-label) +
   div.sb-panel(input.sb-search + div.sb-opt[data-value]). Ao escolher, grava o hidden e
   dispara "change" nele. Fecha no clique fora e no Esc. Texto só por textContent. */
(function () {
  function semAcento(t) {
    return (t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  function fechar(sb) {
    sb.classList.remove('open');
    var bt = sb.querySelector('.sb-display');
    if (bt) bt.setAttribute('aria-expanded', 'false');
  }

  function iniciar(sb) {
    if (sb.dataset.sbPronto) return;
    sb.dataset.sbPronto = '1';
    var hidden = sb.querySelector('input[type=hidden]');
    var display = sb.querySelector('.sb-display');
    var label = sb.querySelector('.sb-label');
    var busca = sb.querySelector('.sb-search');
    var opcoes = function () { return Array.prototype.slice.call(sb.querySelectorAll('.sb-opt')); };

    function escolher(opt) {
      hidden.value = opt.dataset.value;
      label.textContent = opt.textContent;
      sb.classList.add('tem-valor');
      opcoes().forEach(function (o) { o.setAttribute('aria-selected', o === opt ? 'true' : 'false'); });
      fechar(sb);
      display.focus();
      hidden.dispatchEvent(new Event('change', { bubbles: true }));
    }

    display.setAttribute('aria-expanded', 'false');
    display.addEventListener('click', function () {
      var abrir = !sb.classList.contains('open');
      document.querySelectorAll('.selectbusca.open').forEach(fechar);
      if (abrir) {
        sb.classList.add('open');
        display.setAttribute('aria-expanded', 'true');
        if (busca) { busca.value = ''; busca.dispatchEvent(new Event('input')); busca.focus(); }
      }
    });
    if (busca) {
      busca.addEventListener('input', function () {
        var q = semAcento(busca.value);
        opcoes().forEach(function (o) { o.hidden = q !== '' && semAcento(o.textContent).indexOf(q) === -1; });
      });
      busca.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          var primeira = opcoes().filter(function (o) { return !o.hidden; })[0];
          if (primeira) escolher(primeira);
        }
      });
    }
    opcoes().forEach(function (o) {
      o.tabIndex = 0;
      o.addEventListener('click', function () { escolher(o); });
      o.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); escolher(o); } });
    });
    var inicial = opcoes().filter(function (o) { return o.dataset.value === hidden.value && hidden.value !== ''; })[0];
    if (inicial) { label.textContent = inicial.textContent; sb.classList.add('tem-valor'); }
  }

  document.addEventListener('click', function (e) {
    document.querySelectorAll('.selectbusca.open').forEach(function (sb) { if (!sb.contains(e.target)) fechar(sb); });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.querySelectorAll('.selectbusca.open').forEach(function (sb) {
      fechar(sb);
      var bt = sb.querySelector('.sb-display');
      if (bt) bt.focus();
    });
  });

  window.SelectBusca = { iniciar: iniciar };
  document.querySelectorAll('.selectbusca').forEach(iniciar);
})();
