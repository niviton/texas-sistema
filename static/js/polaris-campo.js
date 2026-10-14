/*
 * Peças comuns dos formulários de campo do Polaris (vistoria, checklist, termo):
 * fotos reduzidas no celular, assinatura com o dedo, etapas no celular e rascunho automático.
 * Uma correção aqui vale para todos.
 */
(function () {
  // Reduz a foto no próprio celular antes de enviar (upload bem mais rápido no 4G).
  // O nome leva _t<data da foto> para o carimbo saber se a foto veio da galeria.
  function reduzir(file, max) {
    max = max || 1600;
    return new Promise((resolve) => {
      const url = URL.createObjectURL(file), img = new Image();
      img.onload = () => {
        const r = Math.min(1, max / Math.max(img.width, img.height)), c = document.createElement('canvas');
        c.width = Math.round(img.width * r); c.height = Math.round(img.height * r);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob((b) => resolve(b ? new File([b], (file.name || 'foto').replace(/\.\w+$/, '') + '_t' + (file.lastModified || Date.now()) + '.jpg', { type: 'image/jpeg' }) : file), 'image/jpeg', 0.82);
      };
      img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
      img.src = url;
    });
  }

  // Troca os arquivos do campo pelas versões reduzidas. Navegador antigo: envia o original e o servidor reduz.
  async function trocarArquivos(input, files) {
    try {
      const dt = new DataTransfer();
      for (const f of (files || input.files)) dt.items.add(await reduzir(f));
      input.files = dt.files;
    } catch (e) { /* o servidor reduz */ }
    input.dispatchEvent(new CustomEvent('polaris-fotos', { bubbles: true }));
    return input.files;
  }

  // Assinatura com o dedo num <canvas>. Retorna { assinado, ajustar(), limpar(), dataURL() }.
  function assinatura(canvas, opcoes) {
    opcoes = opcoes || {};
    const ctx = canvas.getContext('2d');
    const estado = { assinado: false };
    let desenhando = false, ultimo = null, pendente = null;
    const avisar = () => canvas.dispatchEvent(new CustomEvent('polaris-assinatura', { bubbles: true }));
    function ajustar() {
      const dpr = window.devicePixelRatio || 1, r = canvas.getBoundingClientRect();
      if (!r.width) return;  // escondida (etapa fechada): desenha quando aparecer
      const antes = pendente || (estado.assinado ? canvas.toDataURL() : null);
      pendente = null;
      canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#0d1b2e'; ctx.fillStyle = '#0d1b2e';
      if (antes) {
        const im = new Image();
        im.onload = () => {
          const k = Math.min(r.width / im.width, r.height / im.height);
          const w = im.width * k, h = im.height * k;
          ctx.drawImage(im, (r.width - w) / 2, (r.height - h) / 2, w, h);
        };
        im.src = antes;
      }
    }
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    // Celular: tocar no quadro abre a assinatura em tela cheia, deitada.
    const telaCheia = opcoes.telaCheia !== undefined ? opcoes.telaCheia : window.matchMedia('(pointer: coarse)').matches;
    if (telaCheia) {
      const dica = canvas.parentElement && canvas.parentElement.querySelector('.sig-hint');
      if (dica && dica.lastChild && dica.lastChild.nodeType === 3) dica.lastChild.textContent = 'Toque para assinar';
      canvas.addEventListener('click', () => assinarDeitado(opcoes.titulo || 'Assinatura', (url) => {
        if (url) { estado.carregar(url); avisar(); } else { estado.limpar(); }
      }));
    }
    canvas.addEventListener('pointerdown', (e) => {
      if (telaCheia) return;
      e.preventDefault(); canvas.setPointerCapture(e.pointerId);
      desenhando = true; ultimo = pos(e);
      ctx.beginPath(); ctx.arc(ultimo.x, ultimo.y, 1.1, 0, Math.PI * 2); ctx.fill();
    });
    canvas.addEventListener('pointermove', (e) => {
      if (!desenhando) return;
      e.preventDefault();
      const p = pos(e);
      ctx.beginPath(); ctx.moveTo(ultimo.x, ultimo.y); ctx.lineTo(p.x, p.y); ctx.stroke(); ultimo = p;
      if (!estado.assinado) { estado.assinado = true; if (opcoes.aoAssinar) opcoes.aoAssinar(); }
    });
    ['pointerup', 'pointercancel', 'pointerleave'].forEach((ev) => canvas.addEventListener(ev, () => {
      if (desenhando && estado.assinado) avisar();
      desenhando = false;
    }));
    estado.limpar = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      estado.assinado = false;
      pendente = null;
      if (opcoes.aoLimpar) opcoes.aoLimpar();
      avisar();
    };
    // Recoloca uma assinatura guardada (rascunho).
    estado.carregar = (url) => {
      if (!url) return;
      pendente = url;
      estado.assinado = true;
      if (opcoes.aoAssinar) opcoes.aoAssinar();
      ajustar();
    };
    estado.ajustar = ajustar;
    estado.dataURL = () => canvas.toDataURL('image/png');
    window.addEventListener('resize', ajustar);
    ajustar();
    return estado;
  }

  // ------------------------------------------------------------------ Assinatura deitada (celular)
  // Tela cheia na horizontal. No Android a tela gira de verdade; no iPhone (que não deixa girar
  // por código) a área de assinatura aparece girada: a pessoa vira o celular e assina deitado.
  function assinarDeitado(titulo, aoTerminar) {
    const ov = document.createElement('div');
    ov.className = 'sigfs';
    ov.innerHTML = '<div class="sigfs-palco"><div class="sigfs-topo"><b></b><span>Vire o celular e assine com o dedo</span></div>'
      + '<div class="sigfs-area"><canvas></canvas><div class="sigfs-linha"></div></div>'
      + '<div class="sigfs-acoes"><button type="button" class="v-btn-sm" data-a="limpar">Limpar</button>'
      + '<button type="button" class="v-btn-sm" data-a="cancelar">Cancelar</button>'
      + '<button type="button" class="v-btn" data-a="ok">Confirmar assinatura</button></div></div>';
    ov.querySelector('b').textContent = titulo;
    document.body.appendChild(ov);
    document.documentElement.classList.add('sigfs-aberta');
    const palco = ov.querySelector('.sigfs-palco'), cv = ov.querySelector('canvas'), ctx = cv.getContext('2d');
    let girado = false, riscou = false, desenhando = false, ultimo = null;

    function montar() {
      const W = window.innerWidth, H = window.innerHeight;
      girado = H > W;  // ainda em pé: gira a área para assinar deitado
      palco.style.width = (girado ? H : W) + 'px';
      palco.style.height = (girado ? W : H) + 'px';
      palco.style.transform = girado ? 'translate(' + W + 'px, 0) rotate(90deg)' : 'none';
      const area = ov.querySelector('.sigfs-area');
      const dpr = window.devicePixelRatio || 1;
      const antes = riscou ? cv.toDataURL() : null;
      cv.width = Math.round(area.clientWidth * dpr); cv.height = Math.round(area.clientHeight * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineWidth = 3; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#0d1b2e'; ctx.fillStyle = '#0d1b2e';
      if (antes) { const im = new Image(); im.onload = () => ctx.drawImage(im, 0, 0, area.clientWidth, area.clientHeight); im.src = antes; }
    }
    // Ponto do dedo nas coordenadas da área (desfaz a rotação quando a área está girada).
    function ponto(e) {
      const r = cv.getBoundingClientRect();
      return girado ? { x: e.clientY - r.top, y: r.right - e.clientX } : { x: e.clientX - r.left, y: e.clientY - r.top };
    }
    cv.addEventListener('pointerdown', (e) => {
      e.preventDefault(); cv.setPointerCapture(e.pointerId);
      desenhando = true; ultimo = ponto(e); riscou = true;
      ctx.beginPath(); ctx.arc(ultimo.x, ultimo.y, 1.4, 0, Math.PI * 2); ctx.fill();
    });
    cv.addEventListener('pointermove', (e) => {
      if (!desenhando) return;
      e.preventDefault();
      const p = ponto(e);
      ctx.beginPath(); ctx.moveTo(ultimo.x, ultimo.y); ctx.lineTo(p.x, p.y); ctx.stroke(); ultimo = p;
    });
    ['pointerup', 'pointercancel'].forEach((ev) => cv.addEventListener(ev, () => { desenhando = false; }));

    function fechar(url) {
      window.removeEventListener('resize', montar);
      try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch (e) { /* sem suporte */ }
      if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
      document.documentElement.classList.remove('sigfs-aberta');
      ov.remove();
      if (url !== undefined) aoTerminar(url);
    }
    ov.addEventListener('click', (e) => {
      const a = e.target.dataset && e.target.dataset.a;
      if (a === 'limpar') { ctx.clearRect(0, 0, cv.width, cv.height); riscou = false; }
      if (a === 'cancelar') fechar();
      if (a === 'ok') fechar(riscou ? cv.toDataURL('image/png') : null);
    });
    window.addEventListener('resize', montar);
    montar();
    // Tenta deitar a tela de verdade (Android/Chrome); se não der, fica a área girada.
    const el = document.documentElement;
    if (el.requestFullscreen) {
      el.requestFullscreen({ navigationUI: 'hide' })
        .then(() => (screen.orientation && screen.orientation.lock ? screen.orientation.lock('landscape') : null))
        .catch(() => {})
        .finally(() => setTimeout(montar, 250));
    }
  }

  // ------------------------------------------------------------------ Etapas (celular)
  // Seções marcadas com data-etapa="N" (e data-etapa-nome) viram uma etapa por tela no celular,
  // com barra de progresso e Voltar / Próximo. No computador o formulário continua inteiro.
  let etapaAtiva = null;

  function etapas(form) {
    const mq = window.matchMedia('(max-width: 760px)');
    const secoes = [...form.querySelectorAll('[data-etapa]')];
    const nums = [...new Set(secoes.map((s) => +s.dataset.etapa))].sort((a, b) => a - b);
    if (nums.length < 2) return null;
    const nomes = nums.map((n) => (secoes.find((s) => +s.dataset.etapa === n && s.dataset.etapaNome) || {}).dataset?.etapaNome || '');
    const envio = form.querySelector('.submit-bar');
    const topo = document.createElement('div');
    topo.className = 'et-topo';
    topo.setAttribute('aria-live', 'polite');
    const nav = document.createElement('div');
    nav.className = 'et-nav';
    nav.innerHTML = '<button type="button" class="v-btn-sm et-voltar">Voltar</button><button type="button" class="v-btn et-prox">Próximo</button>';
    const ancora = secoes[0].closest('.insp-grid, .exec-grid') || secoes[0];
    ancora.parentNode.insertBefore(topo, ancora);
    if (envio) envio.parentNode.insertBefore(nav, envio);
    let atual = 0, ativo = false;

    function render() {
      secoes.forEach((s) => s.classList.toggle('et-oculta', ativo && +s.dataset.etapa !== nums[atual]));
      topo.classList.toggle('et-oculta', !ativo);
      nav.classList.toggle('et-oculta', !ativo);
      const ultimo = atual === nums.length - 1;
      if (envio) envio.classList.toggle('et-oculta', ativo && !ultimo);
      if (!ativo) return;
      topo.innerHTML = '<div class="et-txt">Etapa ' + (atual + 1) + ' de ' + nums.length + ' · <b></b></div>'
        + '<div class="et-barra"><span style="width:' + ((atual + 1) / nums.length) * 100 + '%"></span></div>';
      topo.querySelector('b').textContent = nomes[atual];
      nav.querySelector('.et-voltar').style.visibility = atual ? 'visible' : 'hidden';
      nav.querySelector('.et-prox').classList.toggle('et-oculta', ultimo);
      window.dispatchEvent(new Event('resize'));  // assinatura e barras se ajustam ao aparecer
    }
    function ir(i) {
      atual = Math.max(0, Math.min(nums.length - 1, i));
      render();
      topo.scrollIntoView({ block: 'start' });
    }
    nav.querySelector('.et-voltar').addEventListener('click', () => ir(atual - 1));
    nav.querySelector('.et-prox').addEventListener('click', () => ir(atual + 1));
    function aplicar() { ativo = mq.matches; render(); }
    if (mq.addEventListener) mq.addEventListener('change', aplicar); else mq.addListener(aplicar);
    aplicar();
    etapaAtiva = {
      mostrar(el) {
        const s = ativo && el.closest && el.closest('[data-etapa]');
        if (s) { const i = nums.indexOf(+s.dataset.etapa); if (i !== atual) { atual = i; render(); } }
      },
    };
    return etapaAtiva;
  }

  // Leva até um campo com problema: abre a etapa dele (no celular) e rola até ele.
  function mostrar(el) {
    if (!el) return;
    if (etapaAtiva) etapaAtiva.mostrar(el);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // ------------------------------------------------------------------ Rascunho automático
  // Guarda no próprio celular o que já foi preenchido: respostas (localStorage), fotos (IndexedDB)
  // e assinatura. Se o sinal cair ou a página fechar, ao voltar tudo é restaurado.
  const PREFIXO = 'polaris-rascunho:';
  const VALIDADE = 3 * 24 * 3600 * 1000;
  const IGNORAR = /^(csrfmiddlewaretoken|geo_|assinatura)/;

  function banco() {
    return new Promise((ok, falha) => {
      const r = indexedDB.open('polaris-rascunhos', 1);
      r.onupgradeneeded = () => r.result.createObjectStore('fotos');
      r.onsuccess = () => ok(r.result);
      r.onerror = () => falha(r.error);
    });
  }
  async function guardarFotos(chave, lista) {
    const db = await banco();
    await new Promise((ok, falha) => {
      const t = db.transaction('fotos', 'readwrite');
      if (lista && lista.length) t.objectStore('fotos').put(lista, chave); else t.objectStore('fotos').delete(chave);
      t.oncomplete = ok; t.onerror = () => falha(t.error);
    });
  }
  async function lerFotos(chave) {
    const db = await banco();
    return new Promise((ok, falha) => {
      const r = db.transaction('fotos').objectStore('fotos').get(chave);
      r.onsuccess = () => ok(r.result || []); r.onerror = () => falha(r.error);
    });
  }
  async function apagarFotos(prefixo) {
    const db = await banco();
    await new Promise((ok) => {
      const t = db.transaction('fotos', 'readwrite');
      const r = t.objectStore('fotos').openCursor();
      r.onsuccess = () => { const c = r.result; if (!c) return; if (String(c.key).startsWith(prefixo)) c.delete(); c.continue(); };
      t.oncomplete = ok; t.onerror = ok;
    });
  }
  function apagarRascunho(chave) {
    try { localStorage.removeItem(chave); } catch (e) { /* sem armazenamento */ }
    try { return apagarFotos(chave + '|'); } catch (e) { return Promise.resolve(); }
  }
  function apagarRascunhoEnviado() {
    try {
      const chave = sessionStorage.getItem('polaris-rascunho-enviado');
      sessionStorage.removeItem('polaris-rascunho-enviado');
      if (chave) apagarRascunho(chave);
    } catch (e) { /* sem armazenamento */ }
  }

  function rascunho(form, opcoes) {
    opcoes = opcoes || {};
    const chave = opcoes.chave || PREFIXO + location.pathname + location.search;
    const campos = () => [...form.elements].filter((el) => el.name && !IGNORAR.test(el.name)
      && !['file', 'submit', 'button', 'reset'].includes(el.type));
    const idDe = (el, i) => (el.type === 'radio' ? el.name : el.name + '#' + i);
    let dados = null;
    try { dados = JSON.parse(localStorage.getItem(chave) || 'null'); } catch (e) { dados = null; }
    if (dados && Date.now() - dados.t > VALIDADE) { apagarRascunho(chave); dados = null; }

    // 1) valores: restaurados já, antes do resto da página montar a tela
    if (dados && dados.v) {
      const contagem = {};
      campos().forEach((el) => {
        const i = (contagem[el.name] = (contagem[el.name] || 0) + 1) - 1;
        const v = dados.v[idDe(el, i)];
        if (v === undefined) return;
        if (el.type === 'radio') el.checked = el.value === v;
        else if (el.type === 'checkbox') el.checked = !!v;
        else el.value = v;
      });
    }

    function salvar() {
      const v = {}, contagem = {};
      campos().forEach((el) => {
        const i = (contagem[el.name] = (contagem[el.name] || 0) + 1) - 1;
        if (el.type === 'radio') { if (el.checked) v[el.name] = el.value; }
        else if (el.type === 'checkbox') v[idDe(el, i)] = el.checked;
        else v[idDe(el, i)] = el.value;
      });
      const atual = { t: Date.now(), v, s: {}, f: (dados && dados.f) || [] };
      Object.entries(opcoes.assinaturas || {}).forEach(([nome, sig]) => { if (sig.assinado) atual.s[nome] = sig.dataURL(); });
      dados = atual;
      try { localStorage.setItem(chave, JSON.stringify(atual)); } catch (e) { /* cheio ou bloqueado */ }
    }
    let timer = null;
    const salvarDepois = () => { clearTimeout(timer); timer = setTimeout(salvar, 400); };

    async function salvarFotosDe(input) {
      const lista = [...input.files].map((f) => ({ nome: f.name, tipo: f.type, dado: f }));
      try { await guardarFotos(chave + '|' + input.name, lista); } catch (e) { return; }
      const f = new Set((dados && dados.f) || []);
      if (lista.length) f.add(input.name); else f.delete(input.name);
      if (!dados) salvar();
      dados.f = [...f];
      salvar();
    }

    // 2) depois que a página montou: dispara os avisos, recoloca fotos e assinatura
    async function ativar(extra) {
      Object.assign(opcoes, extra || {});
      if (dados) {
        window.Polaris.restaurando = true;
        campos().forEach((el) => {
          if ((el.type === 'radio' && el.checked) || el.type === 'checkbox' || el.tagName === 'SELECT') {
            el.dispatchEvent(new Event('change', { bubbles: true }));
          }
        });
        window.Polaris.restaurando = false;
        Object.entries(opcoes.assinaturas || {}).forEach(([nome, sig]) => sig.carregar((dados.s || {})[nome]));
        for (const nome of dados.f || []) {
          const input = form.querySelector('input[type=file][name="' + nome + '"]');
          if (!input) continue;
          try {
            const lista = await lerFotos(chave + '|' + nome);
            if (!lista.length) continue;
            const dt = new DataTransfer();
            lista.forEach((x) => dt.items.add(new File([x.dado], x.nome, { type: x.tipo })));
            input.files = dt.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
          } catch (e) { /* navegador sem suporte: segue sem as fotos */ }
        }
        avisoRestaurado(form, dados.t, () => apagarRascunho(chave).then(() => location.reload()));
      }
      form.addEventListener('input', salvarDepois);
      form.addEventListener('change', (e) => { if (e.target.type !== 'file') salvarDepois(); });
      form.addEventListener('polaris-fotos', (e) => salvarFotosDe(e.target));
      form.addEventListener('polaris-assinatura', salvarDepois);
      form.addEventListener('submit', (e) => {
        if (e.defaultPrevented) return;
        salvar();
        try { sessionStorage.setItem('polaris-rascunho-enviado', chave); } catch (err) { /* sem armazenamento */ }
      });
    }
    return { ativar, chave };
  }

  function avisoRestaurado(form, quando, descartar) {
    const d = new Date(quando);
    const p = (n) => String(n).padStart(2, '0');
    const div = document.createElement('div');
    div.className = 'rasc-aviso';
    div.innerHTML = '<span><b>Rascunho recuperado.</b> O que você preencheu em ' + p(d.getDate()) + '/' + p(d.getMonth() + 1)
      + ' às ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ' voltou para a tela.</span><button type="button" class="v-btn-sm">Descartar e começar de novo</button>';
    div.querySelector('button').addEventListener('click', descartar);
    form.insertBefore(div, form.firstElementChild ? form.firstElementChild.nextSibling : null);
  }

  // Estilos das etapas e do aviso de rascunho (iguais em todos os formulários).
  const css = document.createElement('style');
  css.textContent = '.et-oculta{display:none !important}.sig-hint[hidden]{display:none !important}'
    + '.et-topo{position:sticky;top:56px;z-index:5;background:#f4f5f7;padding:10px 0 12px;margin:0 0 6px}'
    + '.et-txt{font-size:13px;color:#556072;margin:0 0 6px}.et-txt b{color:#0d1b2e}'
    + '.et-barra{height:6px;border-radius:6px;background:#e1e5ea;overflow:hidden}.et-barra span{display:block;height:100%;background:#f5a623;transition:width .2s}'
    + '.et-nav{display:flex;justify-content:space-between;gap:10px;margin:14px 0 4px}.et-nav .v-btn{flex:1}.et-nav .v-btn-sm{padding:12px 18px;border-radius:10px}'
    + '.sigfs{position:fixed;inset:0;z-index:1000;background:#fff;overflow:hidden;touch-action:none}'
    + '.sigfs-palco{position:absolute;top:0;left:0;transform-origin:0 0;display:flex;flex-direction:column;padding:12px 16px;box-sizing:border-box;background:#fff}'
    + '.sigfs-topo{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin:0 0 8px}.sigfs-topo b{font-size:16px;color:#0d1b2e}.sigfs-topo span{font-size:12.5px;color:#7b8591}'
    + '.sigfs-area{position:relative;flex:1;border:2px dashed #c5ccd4;border-radius:12px;min-height:0}.sigfs-area canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none}'
    + '.sigfs-linha{position:absolute;left:8%;right:8%;bottom:22%;border-bottom:1.5px solid #c5ccd4;pointer-events:none}'
    + '.sigfs-acoes{display:flex;gap:10px;justify-content:flex-end;margin-top:10px}.sigfs-acoes .v-btn{flex:0 1 260px}.sigfs-acoes .v-btn-sm{padding:12px 16px;border-radius:10px}'
    + 'html.sigfs-aberta,html.sigfs-aberta body{overflow:hidden}'
    + '.rasc-aviso{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;padding:12px 14px;margin:0 0 14px;border-radius:10px;background:#e8f0f8;border:1px solid #c9dbee;color:#1e3f66;font-size:13.5px}';
  document.head.appendChild(css);

  window.Polaris = Object.assign(window.Polaris || {}, {
    reduzir, trocarArquivos, assinatura, etapas, mostrar, rascunho, apagarRascunho, apagarRascunhoEnviado, restaurando: false,
  });
})();
