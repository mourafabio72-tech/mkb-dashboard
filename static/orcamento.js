/* Importar orçamento (Fase 2). Dois passos: Conferir arquivo (prévia, não grava) e
   Gravar orçamento (manda o mesmo arquivo de novo e substitui o ano). Texto vindo do
   servidor entra só por textContent. Loading na área de resultado, nunca no botão. */
(function () {
  var raiz = document.getElementById('orcImportar');
  if (!raiz) return;
  var $ = function (id) { return document.getElementById(id); };
  var empresa = $('orcEmpresa'), ano = $('orcAno'), entrada = $('orcArquivo'), drop = $('orcDrop');
  var botao = $('orcLer'), msg = $('orcMsg'), area = $('orcResultado');
  var arquivo = null, ocupado = false;
  var reais = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
  var inteiro = new Intl.NumberFormat('pt-BR');

  function el(tag, classe, texto) {
    var n = document.createElement(tag);
    if (classe) n.className = classe;
    if (texto !== undefined) n.textContent = texto;
    return n;
  }

  function aviso(alvo, texto, tipo) {
    alvo.textContent = texto || '';
    alvo.className = 'im-msg' + (tipo ? ' ' + tipo : '');
  }

  function anoValido() { return /^[0-9]{4}$/.test(ano.value) && +ano.value >= 2000 && +ano.value <= 2100; }

  function atualizar() { botao.disabled = ocupado || !(arquivo && empresa.value && anoValido()); }

  function escolherArquivo(f) {
    if (f && !/\.xlsx$/i.test(f.name)) {  // o accept do input não vale para o arrasto
      escolherArquivo(null);
      aviso(msg, 'O arquivo precisa ser uma planilha .xlsx (o Rel_OrcRel salvo do Excel).', 'erro');
      return;
    }
    arquivo = f || null;
    var icone = $('orcIcone');
    if (arquivo) {
      $('orcArq').textContent = arquivo.name + ' (' + (arquivo.size / 1048576).toFixed(1).replace('.', ',') + ' MB)';
      $('orcDropTxt').textContent = 'Arquivo selecionado:';
      icone.className = 'ph ph-check-circle';
      drop.classList.add('loaded');
    } else {
      $('orcArq').textContent = '';
      $('orcDropTxt').textContent = 'Clique ou arraste o Rel_OrcRel aqui';
      icone.className = 'ph ph-file-arrow-up';
      drop.classList.remove('loaded');
      entrada.value = '';
    }
    drop.classList.remove('over');
    area.replaceChildren();
    aviso(msg, '');
    atualizar();
  }

  function carregando(texto) {
    var caixa = el('div', 'loading-inline');
    caixa.appendChild(el('div', 'spinner-circle'));
    caixa.appendChild(el('div', 'loading-text', texto));
    area.replaceChildren(caixa);
  }

  function enviar(url) {
    var dados = new FormData();
    dados.append('empresa', empresa.value);
    dados.append('ano', ano.value);
    dados.append('arquivo', arquivo);
    return fetch(url, { method: 'POST', body: dados }).then(function (r) {
      return r.json().catch(function () { return { erro: 'Resposta inesperada do servidor (' + r.status + ').' }; });
    });
  }

  function mostrarPrevia(p) {
    var modelo = $('orcPreviaModelo').content.cloneNode(true);
    var campo = function (nome) { return modelo.querySelector('[data-campo="' + nome + '"]'); };
    campo('empresa').textContent = p.empresa;
    campo('ano').textContent = p.ano;
    campo('linhas').textContent = inteiro.format(p.linhas);
    campo('centros').textContent = inteiro.format(p.centros);
    campo('total').textContent = reais.format(p.total);
    if (p.linhas_substituidas > 0) {
      var substituir = campo('substituir');
      substituir.textContent = 'Já existem ' + inteiro.format(p.linhas_substituidas) + ' linhas de ' + p.ano +
        ' gravadas para ' + p.empresa + '. Ao gravar, elas saem e entram as deste arquivo.';
      substituir.hidden = false;
    }
    p.meses.forEach(function (m) {
      var tr = el('tr');
      tr.appendChild(el('td', '', m.mes));
      tr.appendChild(el('td', 'num' + (m.total < 0 ? ' neg' : ''), reais.format(m.total)));
      campo('meses').appendChild(tr);
    });
    if (p.qtd_contas_sem_linha > 0) {
      campo('qtd-contas').textContent = inteiro.format(p.qtd_contas_sem_linha);
      p.contas_sem_linha.forEach(function (c) { campo('contas').appendChild(el('li', '', c.conta + ': ' + reais.format(c.total))); });
      if (p.qtd_contas_sem_linha > p.contas_sem_linha.length) campo('contas').appendChild(el('li', 'orc-mais', 'e mais ' + (p.qtd_contas_sem_linha - p.contas_sem_linha.length)));
      campo('bloco-contas').hidden = false;
    }
    if (p.qtd_centros_novos > 0) {
      campo('qtd-centros').textContent = inteiro.format(p.qtd_centros_novos);
      p.centros_novos.forEach(function (c) { campo('centros-novos').appendChild(el('li', '', c)); });
      if (p.qtd_centros_novos > p.centros_novos.length) campo('centros-novos').appendChild(el('li', 'orc-mais', 'e mais ' + (p.qtd_centros_novos - p.centros_novos.length)));
      campo('bloco-centros').hidden = false;
    }
    area.replaceChildren(modelo);
    $('orcCancelar').addEventListener('click', function () { escolherArquivo(null); });
    $('orcGravar').addEventListener('click', gravar);
  }

  function travar(sim) {
    ocupado = sim;
    [empresa, ano, entrada].forEach(function (c) { c.disabled = sim; });
    raiz.classList.toggle('ocupado', sim);
    atualizar();
  }

  function conferir() {
    if (botao.disabled) return;
    travar(true);
    aviso(msg, '');
    carregando('Lendo o orçamento de ' + ano.value + '...');
    enviar(raiz.dataset.urlPrevia).then(function (j) {
      if (j.ok) { mostrarPrevia(j.previa); aviso(msg, 'Arquivo conferido. Revise abaixo e grave.', 'ok'); }
      else { area.replaceChildren(); aviso(msg, j.erro || 'Não foi possível ler o arquivo.', 'erro'); }
    }).catch(function () {
      area.replaceChildren();
      aviso(msg, 'Sem conexão com o servidor. Tente de novo.', 'erro');
    }).finally(function () { travar(false); });
  }

  function gravar() {
    var gravarBt = $('orcGravar'), cancelar = $('orcCancelar'), msgGravar = $('orcMsgGravar');
    gravarBt.disabled = true; cancelar.disabled = true;
    travar(true);
    aviso(msgGravar, '');
    var previa = area.firstElementChild;
    var espera = el('div', 'loading-inline');
    espera.appendChild(el('div', 'spinner-circle'));
    espera.appendChild(el('div', 'loading-text', 'Gravando o orçamento de ' + ano.value + '...'));
    previa.appendChild(espera);
    enviar(raiz.dataset.urlConfirmar).then(function (j) {
      espera.remove();
      if (j.ok) {
        var texto = 'Orçamento de ' + j.ano + ' da ' + j.empresa + ' gravado: ' + inteiro.format(j.linhas) + ' linhas' +
          (j.substituidas ? ', no lugar de ' + inteiro.format(j.substituidas) + '.' : '.');
        escolherArquivo(null);
        aviso(msg, texto, 'ok');
      } else {
        aviso(msgGravar, j.erro || 'Não foi possível gravar.', 'erro');
        gravarBt.disabled = false; cancelar.disabled = false;
      }
    }).catch(function () {
      espera.remove();
      aviso(msgGravar, 'Sem conexão com o servidor. Nada foi gravado.', 'erro');
      gravarBt.disabled = false; cancelar.disabled = false;
    }).finally(function () { travar(false); });
  }

  entrada.addEventListener('change', function () { escolherArquivo(entrada.files[0]); });
  drop.addEventListener('dragover', function (e) { e.preventDefault(); drop.classList.add('over'); });
  drop.addEventListener('dragleave', function (e) { e.preventDefault(); drop.classList.remove('over'); });
  drop.addEventListener('drop', function (e) {
    e.preventDefault();
    if (ocupado) return;
    var f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (f) escolherArquivo(f);
  });
  empresa.addEventListener('change', function () { area.replaceChildren(); aviso(msg, ''); atualizar(); });
  ano.addEventListener('input', function () { area.replaceChildren(); aviso(msg, ''); atualizar(); });
  botao.addEventListener('click', conferir);
  atualizar();
})();
