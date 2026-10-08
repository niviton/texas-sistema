/*
 * Peças comuns dos formulários de campo do Polaris (vistoria, checklist, termo):
 * fotos reduzidas no celular e assinatura com o dedo. Uma correção aqui vale para todos.
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
    return input.files;
  }

  // Assinatura com o dedo num <canvas>. Retorna { assinado, ajustar(), limpar(), dataURL() }.
  function assinatura(canvas, opcoes) {
    opcoes = opcoes || {};
    const ctx = canvas.getContext('2d');
    const estado = { assinado: false };
    let desenhando = false, ultimo = null;
    function ajustar() {
      const dpr = window.devicePixelRatio || 1, r = canvas.getBoundingClientRect();
      if (!r.width) return;
      const antes = estado.assinado ? canvas.toDataURL() : null;
      canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.lineWidth = 2.4; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#0d1b2e'; ctx.fillStyle = '#0d1b2e';
      if (antes) { const im = new Image(); im.onload = () => ctx.drawImage(im, 0, 0, r.width, r.height); im.src = antes; }
    }
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    canvas.addEventListener('pointerdown', (e) => {
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
    ['pointerup', 'pointercancel', 'pointerleave'].forEach((ev) => canvas.addEventListener(ev, () => { desenhando = false; }));
    estado.limpar = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      estado.assinado = false;
      if (opcoes.aoLimpar) opcoes.aoLimpar();
    };
    estado.ajustar = ajustar;
    estado.dataURL = () => canvas.toDataURL('image/png');
    window.addEventListener('resize', ajustar);
    ajustar();
    return estado;
  }

  window.Polaris = Object.assign(window.Polaris || {}, { reduzir, trocarArquivos, assinatura });
})();
