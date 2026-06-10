/* ═══════════════════════════════════════════════════════════════════════════
   DAILY GAMES — Porra Mundial 2026
   31 minijuegos en rotación: cada día del mes toca uno distinto.
   Cada juego es {name, icon, desc, render(el)}. render() monta el juego dentro
   del contenedor. El orden del array determina la rotación (día N → juego N%31).
   ═══════════════════════════════════════════════════════════════════════════ */

// ── Datos de los 48 equipos: [nombre, bandera, capital] ──────────────────────
const DG_TEAMS = [
  ['México','🇲🇽','Ciudad de México'], ['Corea del Sur','🇰🇷','Seúl'],
  ['Sudáfrica','🇿🇦','Pretoria'], ['República Checa','🇨🇿','Praga'],
  ['Canadá','🇨🇦','Ottawa'], ['Suiza','🇨🇭','Berna'], ['Qatar','🇶🇦','Doha'],
  ['Bosnia y Herzegovina','🇧🇦','Sarajevo'], ['Brasil','🇧🇷','Brasilia'],
  ['Marruecos','🇲🇦','Rabat'], ['Haití','🇭🇹','Puerto Príncipe'],
  ['Escocia','🏴󠁧󠁢󠁳󠁣󠁴󠁿','Edimburgo'], ['Estados Unidos','🇺🇸','Washington D.C.'],
  ['Paraguay','🇵🇾','Asunción'], ['Australia','🇦🇺','Canberra'],
  ['Turquía','🇹🇷','Ankara'], ['Alemania','🇩🇪','Berlín'],
  ['Curazao','🇨🇼','Willemstad'], ['Costa de Marfil','🇨🇮','Yamusukro'],
  ['Ecuador','🇪🇨','Quito'], ['Países Bajos','🇳🇱','Ámsterdam'],
  ['Japón','🇯🇵','Tokio'], ['Suecia','🇸🇪','Estocolmo'], ['Túnez','🇹🇳','Túnez'],
  ['Bélgica','🇧🇪','Bruselas'], ['Egipto','🇪🇬','El Cairo'], ['Irán','🇮🇷','Teherán'],
  ['Nueva Zelanda','🇳🇿','Wellington'], ['España','🇪🇸','Madrid'],
  ['Cabo Verde','🇨🇻','Praia'], ['Arabia Saudita','🇸🇦','Riad'],
  ['Uruguay','🇺🇾','Montevideo'], ['Francia','🇫🇷','París'],
  ['Senegal','🇸🇳','Dakar'], ['Irak','🇮🇶','Bagdad'], ['Noruega','🇳🇴','Oslo'],
  ['Argentina','🇦🇷','Buenos Aires'], ['Argelia','🇩🇿','Argel'],
  ['Austria','🇦🇹','Viena'], ['Jordania','🇯🇴','Ammán'],
  ['Portugal','🇵🇹','Lisboa'], ['RD Congo','🇨🇩','Kinsasa'],
  ['Uzbekistán','🇺🇿','Taskent'], ['Colombia','🇨🇴','Bogotá'],
  ['Inglaterra','🏴󠁧󠁢󠁥󠁮󠁧󠁿','Londres'], ['Croacia','🇭🇷','Zagreb'],
  ['Ghana','🇬🇭','Acra'], ['Panamá','🇵🇦','Ciudad de Panamá'],
];

// ── Helpers ──────────────────────────────────────────────────────────────────
function dgDay() { return Math.floor(Date.now() / 86400000); }

// RNG determinista (mulberry32) — mismo resultado para todos durante el día
function dgRng(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function dgShuffle(arr, rng) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor((rng ? rng() : Math.random()) * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function dgPick(arr, n, rng) { return dgShuffle(arr, rng).slice(0, n); }

// Récords en localStorage. higherIsBetter=true → guarda el mayor.
function dgBest(key) { return localStorage.getItem('porra_dg_' + key); }
function dgSaveBest(key, value, higherIsBetter = true) {
  const prev = parseFloat(dgBest(key));
  const isNew = isNaN(prev) || (higherIsBetter ? value > prev : value < prev);
  if (isNew) localStorage.setItem('porra_dg_' + key, value);
  return isNew;
}

// Barra inferior estándar: puntuación + récord
function dgScoreBar(id, label, unit) {
  return `<div class="d-flex justify-content-between align-items-end mt-2">
    <div><span class="fw-bold fs-3 text-info" id="${id}-score">—</span><small class="text-muted ms-1">${unit || ''}</small></div>
    <div class="text-end">
      <small class="text-muted d-block" style="font-size:.7rem">${label || 'Récord'}</small>
      <span class="fw-bold text-warning" id="${id}-best">—</span>
    </div>
  </div>`;
}

function dgSetText(el, sel, txt) { const n = el.querySelector(sel); if (n) n.textContent = txt; }

function dgRetryBtn(el, game) {
  const b = document.createElement('button');
  b.className = 'btn btn-outline-secondary btn-sm w-100 mt-2';
  b.innerHTML = '<i class="bi bi-arrow-repeat"></i> Reintentar';
  b.onclick = () => game.render(el);
  return b;
}

// Quiz genérico de 10 rondas: makeRound(rng) → {prompt, options:[4], answer}
function dgQuiz(el, game, bestKey, makeRound) {
  const rng = dgRng(dgDay() * 7919 + bestKey.length);
  let round = 0, score = 0;
  const total = 10;

  function next() {
    if (round >= total) return finish();
    const q = makeRound(rng);
    round++;
    el.innerHTML = `
      <div class="text-center mb-2">
        <span class="badge bg-dark border border-secondary">Ronda ${round}/${total} · ✅ ${score}</span>
      </div>
      <div class="text-center fs-5 fw-bold mb-3" style="min-height:2.2em">${q.prompt}</div>
      <div class="d-grid gap-2" id="dgq-opts"></div>`;
    const box = el.querySelector('#dgq-opts');
    q.options.forEach(opt => {
      const b = document.createElement('button');
      b.className = 'btn btn-outline-secondary btn-sm text-start';
      b.innerHTML = opt;
      b.onclick = () => {
        const ok = (opt === q.answer);
        if (ok) score++;
        box.querySelectorAll('button').forEach(x => {
          x.disabled = true;
          if (x.innerHTML === q.answer) x.className = 'btn btn-success btn-sm text-start';
          else if (x === b) x.className = 'btn btn-danger btn-sm text-start';
        });
        setTimeout(next, ok ? 600 : 1200);
      };
      box.appendChild(b);
    });
  }

  function finish() {
    const isNew = dgSaveBest(bestKey, score);
    const msgs = [[10,'🏆 ¡Perfecto!'],[8,'🔥 Impresionante'],[6,'👍 Muy bien'],[4,'🙂 No está mal'],[0,'😅 A repasar...']];
    el.innerHTML = `
      <div class="text-center py-3">
        <div style="font-size:3rem">${score >= 8 ? '🏆' : score >= 5 ? '⭐' : '📚'}</div>
        <div class="fw-bold fs-2">${score}/${total}</div>
        <div class="text-muted small mb-1">${msgs.find(([m]) => score >= m)[1]}</div>
        <div class="small">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + (dgBest(bestKey) || 0) + '/10'}</div>
      </div>`;
    el.appendChild(dgRetryBtn(el, game));
  }
  next();
}

/* ═══════════════════════════════════════════════════════════════════════════
   LOS 31 JUEGOS
   ═══════════════════════════════════════════════════════════════════════════ */

const DAILY_GAMES = [

// ── 0: Penaltis ──────────────────────────────────────────────────────────────
{
  name: 'Penaltis', icon: '⚽', desc: '¿Cuántos metes en 30 segundos?',
  render(el) {
    const game = this;
    el.innerHTML = `
      <div id="pk-area" style="position:relative;height:130px;background:#0a2e0a;border-radius:8px;
            overflow:hidden;border:2px solid #1a5c1a;cursor:crosshair;">
        <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
              width:55%;height:75%;border:1.5px solid rgba(255,255,255,.15);pointer-events:none;"></div>
        <button id="pk-ball" style="position:absolute;left:calc(50% - 18px);top:calc(50% - 18px);
              background:none;border:none;font-size:2.2rem;line-height:1;cursor:pointer;
              user-select:none;transition:transform .08s;padding:0;">⚽</button>
      </div>
      ${dgScoreBar('pk', 'Récord', 'goles')}
      <button class="btn btn-success btn-sm w-100 mt-2 fw-bold" id="pk-btn">
        <i class="bi bi-play-fill"></i> ¡Jugar!</button>`;
    dgSetText(el, '#pk-score', '0');
    dgSetText(el, '#pk-best', dgBest('penaltis') || '—');

    let active = false, score = 0, secs = 30, timer = null;
    const ball = el.querySelector('#pk-ball'), area = el.querySelector('#pk-area'),
          btn = el.querySelector('#pk-btn');
    const move = () => {
      ball.style.left = (Math.random() * (area.clientWidth - 38)) + 'px';
      ball.style.top  = (Math.random() * (area.clientHeight - 38)) + 'px';
    };
    ball.onclick = () => {
      if (!active) return;
      score++; dgSetText(el, '#pk-score', score);
      ball.style.transform = 'scale(1.5) rotate(30deg)';
      setTimeout(() => { ball.style.transform = ''; move(); }, 90);
    };
    btn.onclick = () => {
      if (active) return;
      active = true; score = 0; secs = 30;
      dgSetText(el, '#pk-score', '0');
      btn.disabled = true; btn.innerHTML = '<i class="bi bi-stopwatch-fill"></i> 30s ¡Venga!';
      move();
      timer = setInterval(() => {
        secs--;
        btn.innerHTML = `<i class="bi bi-stopwatch-fill"></i> ${secs}s ¡Venga!`;
        if (secs <= 0) {
          clearInterval(timer); active = false;
          const isNew = dgSaveBest('penaltis', score);
          dgSetText(el, '#pk-best', dgBest('penaltis'));
          btn.disabled = false;
          btn.innerHTML = isNew
            ? `<i class="bi bi-trophy-fill"></i> ¡Récord! ${score} goles – Repetir`
            : `<i class="bi bi-arrow-repeat"></i> Repetir (${score} goles)`;
        }
      }, 1000);
    };
  },
},

// ── 1: Tiempo de Reacción ────────────────────────────────────────────────────
{
  name: 'Tiempo de Reacción', icon: '⚡', desc: 'Pulsa en cuanto veas el verde',
  render(el) {
    el.innerHTML = `
      <div id="rt-box" style="height:130px;border-radius:8px;background:#6c757d;cursor:pointer;
            display:flex;align-items:center;justify-content:center;user-select:none;transition:background .15s;">
        <div id="rt-msg" style="font-size:1.05rem;font-weight:bold;color:#fff;text-align:center;pointer-events:none;">
          Pulsa para empezar</div>
      </div>
      ${dgScoreBar('rt', 'Récord', 'ms')}
      <div class="text-muted small text-center mt-1" id="rt-rating"></div>`;
    dgSetText(el, '#rt-best', dgBest('reaccion') ? dgBest('reaccion') + ' ms' : '—');

    let state = 'idle', timeout = null, start = 0;
    const box = el.querySelector('#rt-box');
    box.onclick = () => {
      if (state === 'idle') {
        state = 'waiting';
        box.style.background = '#dc3545';
        dgSetText(el, '#rt-msg', 'Espera...');
        timeout = setTimeout(() => {
          state = 'ready'; box.style.background = '#198754';
          dgSetText(el, '#rt-msg', '¡AHORA!');
          start = performance.now();
        }, 1500 + Math.random() * 3000);
      } else if (state === 'waiting') {
        clearTimeout(timeout); state = 'idle';
        box.style.background = '#6c757d';
        dgSetText(el, '#rt-msg', '¡Demasiado pronto! Pulsa para reintentar');
      } else {
        const ms = Math.round(performance.now() - start);
        state = 'idle'; box.style.background = '#6c757d';
        dgSetText(el, '#rt-msg', 'Pulsa para repetir');
        dgSetText(el, '#rt-score', ms);
        const r = [[180,'⚡ ¡Reflejos de portero profesional!'],[250,'🟢 Muy bueno'],[350,'🟡 Normal'],[500,'🔴 Lento'],[99999,'🐢 ¿Estabas dormido?']];
        dgSetText(el, '#rt-rating', r.find(([m]) => ms <= m)[1]);
        if (dgSaveBest('reaccion', ms, false)) dgSetText(el, '#rt-best', ms + ' ms');
      }
    };
  },
},

// ── 2: Adivina el Color ──────────────────────────────────────────────────────
{
  name: 'Adivina el Color', icon: '🎨', desc: 'Memoriza y recrea el color exacto',
  render(el) {
    const game = this;
    const t = [0,0,0].map(() => Math.floor(Math.random() * 256));
    const s = [0,0,0].map(() => Math.floor(Math.random() * 256));
    el.innerHTML = `
      <div id="cg1">
        <div style="height:110px;border-radius:8px;background:rgb(${t})"></div>
        <p class="text-muted small text-center mt-2 mb-3">Memoriza este color</p>
        <button class="btn btn-warning w-100 fw-bold" id="cg-go"><i class="bi bi-eye-slash-fill"></i> ¡Listo, ocultar!</button>
      </div>
      <div id="cg2" style="display:none">
        <div id="cg-prev" style="height:70px;border-radius:8px;background:rgb(${s});margin-bottom:.75rem"></div>
        ${['R','G','B'].map((c, i) => `
          <div class="mb-2">
            <div class="d-flex justify-content-between small mb-1">
              <span class="fw-bold text-${['danger','success','info'][i]}">${c}</span><span id="cg-v${i}">${s[i]}</span>
            </div>
            <input type="range" class="form-range" id="cg-s${i}" min="0" max="255" value="${s[i]}">
          </div>`).join('')}
        <button class="btn btn-primary w-100 fw-bold" id="cg-check"><i class="bi bi-check2-circle"></i> Comprobar</button>
      </div>`;
    el.querySelector('#cg-go').onclick = () => {
      el.querySelector('#cg1').style.display = 'none';
      el.querySelector('#cg2').style.display = 'block';
    };
    const sliders = [0,1,2].map(i => el.querySelector('#cg-s' + i));
    sliders.forEach((sl, i) => sl.oninput = () => {
      dgSetText(el, '#cg-v' + i, sl.value);
      el.querySelector('#cg-prev').style.background = `rgb(${sliders.map(x => x.value)})`;
    });
    el.querySelector('#cg-check').onclick = () => {
      const g = sliders.map(x => parseInt(x.value));
      const dist = Math.sqrt(g.reduce((acc, v, i) => acc + (v - t[i]) ** 2, 0));
      const pct = Math.round((1 - dist / 441.67) * 100);
      const msgs = [[97,'👁️ ¡Perfecto! Ojo de artista'],[90,'🎨 ¡Muy cerca! Gran ojo'],[75,'👍 Bien, pero no del todo'],[55,'🤔 Bastante lejos'],[0,'😅 ¿Eres daltónico?']];
      const isNew = dgSaveBest('color', pct);
      el.innerHTML = `
        <div class="d-flex gap-2 mb-3">
          <div style="flex:1;text-align:center"><div style="height:70px;border-radius:8px;background:rgb(${t})"></div><small class="text-muted">Original</small></div>
          <div style="flex:1;text-align:center"><div style="height:70px;border-radius:8px;background:rgb(${g})"></div><small class="text-muted">Tu color</small></div>
        </div>
        <div class="text-center mb-2">
          <div class="fw-bold" style="font-size:2.5rem">${pct}%</div>
          <div class="text-muted small">${msgs.find(([m]) => pct >= m)[1]}</div>
          <div class="small mt-1">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + (dgBest('color') || 0) + '%'}</div>
        </div>`;
      el.appendChild(dgRetryBtn(el, game));
    };
  },
},

// ── 3: Clicks por Segundo ────────────────────────────────────────────────────
{
  name: 'Clicks por Segundo', icon: '🖱️', desc: '¿Cuántos clicks en 5 segundos?',
  render(el) {
    const game = this;
    el.innerHTML = `
      <div id="cps-box" style="height:130px;border-radius:8px;background:#1a1a2e;border:2px solid #333;
            cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;
            user-select:none;transition:background .05s;">
        <div class="fw-bold" id="cps-count" style="font-size:3rem;color:#fff;line-height:1">0</div>
        <div id="cps-msg" style="color:#aaa;font-size:.85rem;margin-top:.3rem">Pulsa aquí para empezar</div>
      </div>
      ${dgScoreBar('cps', 'Récord', 'CPS')}`;
    dgSetText(el, '#cps-best', dgBest('cps') ? dgBest('cps') + ' CPS' : '—');

    let active = false, done = false, clicks = 0, secs = 5, timer = null;
    const box = el.querySelector('#cps-box');
    box.onclick = () => {
      if (done) return;
      if (!active) {
        active = true; clicks = 0; secs = 5;
        dgSetText(el, '#cps-msg', '¡Dale! (5s)');
        box.style.background = '#0d2137';
        timer = setInterval(() => {
          secs--;
          dgSetText(el, '#cps-msg', `¡Dale! (${secs}s)`);
          if (secs <= 0) {
            clearInterval(timer); active = false; done = true;
            const cps = (clicks / 5).toFixed(2);
            dgSetText(el, '#cps-score', cps);
            const isNew = dgSaveBest('cps', parseFloat(cps));
            dgSetText(el, '#cps-best', dgBest('cps') + ' CPS');
            const r = [[14,'⚡ ¿Eres humano?'],[10,'🔥 Top tier'],[7,'👍 Muy rápido'],[5,'🙂 Normal'],[0,'🐢 Con calma...']];
            dgSetText(el, '#cps-msg', (isNew ? '¡Nuevo récord! ' : '') + r.find(([m]) => parseFloat(cps) >= m)[1]);
            box.style.background = '#1a1a2e';
            el.appendChild(dgRetryBtn(el, game));
          }
        }, 1000);
      }
      clicks++;
      dgSetText(el, '#cps-count', clicks);
      box.style.background = '#0a3d62';
      setTimeout(() => { if (active) box.style.background = '#0d2137'; }, 60);
    };
  },
},

// ── 4: ¿Qué bandera es? ──────────────────────────────────────────────────────
{
  name: '¿Qué bandera es?', icon: '🚩', desc: 'Adivina el país de cada bandera',
  render(el) {
    dgQuiz(el, this, 'banderas', (rng) => {
      const opts = dgPick(DG_TEAMS, 4, rng);
      const ans = opts[Math.floor(rng() * 4)];
      return {
        prompt: `<span style="font-size:3rem">${ans[1]}</span>`,
        options: opts.map(t => t[0]),
        answer: ans[0],
      };
    });
  },
},

// ── 5: Memoria de Banderas ───────────────────────────────────────────────────
{
  name: 'Memoria de Banderas', icon: '🧠', desc: 'Encuentra las parejas en menos intentos',
  render(el) {
    const game = this;
    const flags = dgPick(DG_TEAMS.filter(t => !['Escocia','Inglaterra'].includes(t[0])), 6).map(t => t[1]);
    const cards = dgShuffle([...flags, ...flags]);
    let first = null, lock = false, moves = 0, found = 0;
    el.innerHTML = `
      <div class="text-center small text-muted mb-2">Intentos: <strong id="mem-moves">0</strong> · Récord: <strong class="text-warning">${dgBest('memoria') || '—'}</strong></div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px" id="mem-grid"></div>`;
    const grid = el.querySelector('#mem-grid');
    cards.forEach((f) => {
      const c = document.createElement('button');
      c.style.cssText = 'aspect-ratio:1;border-radius:8px;border:1px solid #444;background:#1b1c2a;font-size:1.6rem;cursor:pointer;transition:all .2s';
      c.textContent = '❓';
      c.dataset.flag = f;
      c.onclick = () => {
        if (lock || c.disabled || c === first) return;
        c.textContent = f;
        if (!first) { first = c; return; }
        moves++; dgSetText(el, '#mem-moves', moves);
        if (first.dataset.flag === f) {
          c.disabled = true; first.disabled = true;
          c.style.background = first.style.background = '#14532d';
          first = null; found++;
          if (found === 6) {
            const isNew = dgSaveBest('memoria', moves, false);
            setTimeout(() => {
              el.innerHTML = `<div class="text-center py-3">
                <div style="font-size:3rem">🧠</div>
                <div class="fw-bold fs-3">${moves} intentos</div>
                <div class="small">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + dgBest('memoria')}</div>
              </div>`;
              el.appendChild(dgRetryBtn(el, game));
            }, 500);
          }
        } else {
          lock = true;
          const f1 = first;
          setTimeout(() => { c.textContent = '❓'; f1.textContent = '❓'; first = null; lock = false; }, 700);
        }
      };
      grid.appendChild(c);
    });
  },
},

// ── 6: Número Misterioso ─────────────────────────────────────────────────────
{
  name: 'Número Misterioso', icon: '🔢', desc: 'Adivina el número del 1 al 100',
  render(el) {
    const game = this;
    const target = Math.floor(Math.random() * 100) + 1;
    let tries = 0;
    el.innerHTML = `
      <div class="text-center mb-2"><span class="badge bg-dark border border-secondary">Entre 1 y 100 · Récord: ${dgBest('numero') || '—'} intentos</span></div>
      <div class="d-flex gap-2 mb-2">
        <input type="number" class="form-control" id="num-in" min="1" max="100" placeholder="Tu número...">
        <button class="btn btn-primary fw-bold" id="num-go">Probar</button>
      </div>
      <div id="num-log" class="small" style="max-height:130px;overflow-y:auto"></div>`;
    const input = el.querySelector('#num-in'), log = el.querySelector('#num-log');
    const guess = () => {
      const v = parseInt(input.value);
      if (!v || v < 1 || v > 100) return;
      tries++;
      const row = document.createElement('div');
      row.className = 'py-1 border-bottom border-secondary d-flex justify-content-between';
      if (v === target) {
        const isNew = dgSaveBest('numero', tries, false);
        el.innerHTML = `<div class="text-center py-3">
          <div style="font-size:3rem">🎯</div>
          <div class="fw-bold fs-3">¡Era ${target}!</div>
          <div class="text-muted small">Lo lograste en ${tries} intento${tries > 1 ? 's' : ''}</div>
          <div class="small mt-1">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + dgBest('numero')}</div>
        </div>`;
        el.appendChild(dgRetryBtn(el, game));
        return;
      }
      row.innerHTML = `<span>${v}</span><span class="${v < target ? 'text-info' : 'text-danger'}">${v < target ? '⬆️ Más alto' : '⬇️ Más bajo'}</span>`;
      log.prepend(row);
      input.value = ''; input.focus();
    };
    el.querySelector('#num-go').onclick = guess;
    input.onkeydown = (e) => { if (e.key === 'Enter') guess(); };
  },
},

// ── 7: Simon Dice ────────────────────────────────────────────────────────────
{
  name: 'Simon Dice', icon: '🟢', desc: 'Repite la secuencia de colores',
  render(el) {
    const game = this;
    const colors = ['#dc3545', '#198754', '#0d6efd', '#ffc107'];
    let seq = [], pos = 0, playing = false;
    el.innerHTML = `
      <div class="text-center small text-muted mb-2">Nivel: <strong id="si-lvl" class="text-info">0</strong> · Récord: <strong class="text-warning">${dgBest('simon') || '—'}</strong></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px" id="si-grid"></div>
      <button class="btn btn-success btn-sm w-100 mt-2 fw-bold" id="si-btn"><i class="bi bi-play-fill"></i> Empezar</button>`;
    const grid = el.querySelector('#si-grid');
    const pads = colors.map((c, i) => {
      const p = document.createElement('button');
      p.style.cssText = `height:60px;border-radius:10px;border:none;background:${c};opacity:.35;cursor:pointer;transition:opacity .15s`;
      p.onclick = () => {
        if (!playing) return;
        flash(i);
        if (i === seq[pos]) {
          pos++;
          if (pos === seq.length) { playing = false; setTimeout(nextLevel, 700); }
        } else {
          playing = false;
          const lvl = seq.length - 1;
          const isNew = dgSaveBest('simon', lvl);
          el.querySelector('#si-btn').innerHTML = `❌ Nivel ${lvl} ${isNew ? '· 🎉 ¡Récord!' : ''} – Reintentar`;
          el.querySelector('#si-btn').disabled = false;
          seq = [];
        }
      };
      grid.appendChild(p);
      return p;
    });
    const flash = (i) => {
      pads[i].style.opacity = '1';
      setTimeout(() => pads[i].style.opacity = '.35', 250);
    };
    const playSeq = (k) => {
      if (k >= seq.length) { playing = true; pos = 0; return; }
      flash(seq[k]);
      setTimeout(() => playSeq(k + 1), 450);
    };
    const nextLevel = () => {
      seq.push(Math.floor(Math.random() * 4));
      dgSetText(el, '#si-lvl', seq.length);
      setTimeout(() => playSeq(0), 400);
    };
    el.querySelector('#si-btn').onclick = (e) => {
      e.target.disabled = true;
      e.target.innerHTML = 'Observa y repite...';
      seq = []; nextLevel();
    };
  },
},

// ── 8: Puntería ──────────────────────────────────────────────────────────────
{
  name: 'Puntería', icon: '🎯', desc: 'Acierta 10 dianas lo más rápido posible',
  render(el) {
    const game = this;
    el.innerHTML = `
      <div id="aim-area" style="position:relative;height:160px;background:#10101c;border-radius:8px;border:2px solid #333;overflow:hidden">
        <button class="btn btn-success fw-bold" id="aim-start"
          style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%)">
          <i class="bi bi-play-fill"></i> ¡Jugar!</button>
      </div>
      ${dgScoreBar('aim', 'Récord', 'seg')}`;
    dgSetText(el, '#aim-best', dgBest('punteria') ? dgBest('punteria') + ' s' : '—');
    const area = el.querySelector('#aim-area');
    let hits = 0, start = 0;
    const spawn = () => {
      const t = document.createElement('button');
      t.textContent = '🎯';
      t.style.cssText = `position:absolute;background:none;border:none;font-size:1.8rem;cursor:pointer;padding:0;
        left:${Math.random() * (area.clientWidth - 34)}px;top:${Math.random() * (area.clientHeight - 34)}px`;
      t.onclick = () => {
        t.remove(); hits++;
        if (hits >= 10) {
          const secs = ((performance.now() - start) / 1000).toFixed(2);
          dgSetText(el, '#aim-score', secs);
          const isNew = dgSaveBest('punteria', parseFloat(secs), false);
          dgSetText(el, '#aim-best', dgBest('punteria') + ' s');
          area.innerHTML = `<div class="d-flex flex-column align-items-center justify-content-center h-100">
            <div style="font-size:2rem">${isNew ? '🎉' : '🎯'}</div>
            <div class="fw-bold">${secs}s ${isNew ? '· ¡Récord!' : ''}</div></div>`;
          setTimeout(() => el.appendChild(dgRetryBtn(el, game)), 100);
        } else spawn();
      };
      area.appendChild(t);
    };
    el.querySelector('#aim-start').onclick = (e) => {
      e.target.remove(); hits = 0; start = performance.now(); spawn();
    };
  },
},

// ── 9: Cálculo Exprés ────────────────────────────────────────────────────────
{
  name: 'Cálculo Exprés', icon: '➕', desc: 'Resuelve cuantas más sumas en 30s',
  render(el) {
    const game = this;
    el.innerHTML = `
      <div class="text-center mb-2"><span class="badge bg-dark border border-secondary" id="ce-status">30s · Récord: ${dgBest('calculo') || '—'}</span></div>
      <div class="text-center fw-bold mb-2" style="font-size:2rem" id="ce-q">—</div>
      <div class="d-flex gap-2">
        <input type="number" class="form-control" id="ce-in" placeholder="Respuesta..." disabled>
        <button class="btn btn-primary fw-bold" id="ce-go">Empezar</button>
      </div>`;
    let score = 0, secs = 30, answer = 0, timer = null, running = false;
    const input = el.querySelector('#ce-in'), btn = el.querySelector('#ce-go');
    const newQ = () => {
      const op = Math.random();
      let a, b, txt;
      if (op < 0.4) { a = 10 + Math.floor(Math.random() * 90); b = 10 + Math.floor(Math.random() * 90); answer = a + b; txt = `${a} + ${b}`; }
      else if (op < 0.7) { a = 30 + Math.floor(Math.random() * 70); b = Math.floor(Math.random() * a); answer = a - b; txt = `${a} − ${b}`; }
      else { a = 2 + Math.floor(Math.random() * 11); b = 2 + Math.floor(Math.random() * 11); answer = a * b; txt = `${a} × ${b}`; }
      dgSetText(el, '#ce-q', txt);
    };
    const check = () => {
      if (!running) return;
      if (parseInt(input.value) === answer) { score++; input.value = ''; newQ(); }
    };
    input.oninput = check;
    btn.onclick = () => {
      if (running) return;
      running = true; score = 0; secs = 30;
      input.disabled = false; input.value = ''; input.focus();
      btn.disabled = true; newQ();
      timer = setInterval(() => {
        secs--;
        dgSetText(el, '#ce-status', `${secs}s · Aciertos: ${score}`);
        if (secs <= 0) {
          clearInterval(timer); running = false;
          const isNew = dgSaveBest('calculo', score);
          el.innerHTML = `<div class="text-center py-3">
            <div style="font-size:3rem">🧮</div>
            <div class="fw-bold fs-2">${score} aciertos</div>
            <div class="small">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + dgBest('calculo')}</div>
          </div>`;
          el.appendChild(dgRetryBtn(el, game));
        }
      }, 1000);
    };
  },
},

// ── 10: Mecanografía ─────────────────────────────────────────────────────────
{
  name: 'Mecanografía', icon: '⌨️', desc: 'Escribe la frase lo más rápido posible',
  render(el) {
    const game = this;
    const phrases = [
      'el balon rueda y la grada ruge',
      'gol en el ultimo minuto del partido',
      'la copa del mundo brilla en el estadio',
      'el portero vuela y detiene el penalti',
      'tiki taka toque y control en el centro',
      'fuera de juego por un palmo de la bota',
      'el delantero define cruzado al palo largo',
      'cantamos juntos el himno antes de jugar',
    ];
    const phrase = phrases[dgDay() % phrases.length];
    el.innerHTML = `
      <div class="p-2 rounded mb-2 small" style="background:#10101c;border:1px solid #333" id="ty-target">${phrase}</div>
      <input type="text" class="form-control mb-2" id="ty-in" placeholder="Escribe aquí... (empieza al teclear)" autocomplete="off">
      ${dgScoreBar('ty', 'Récord', 'PPM')}`;
    dgSetText(el, '#ty-best', dgBest('typing') ? dgBest('typing') + ' PPM' : '—');
    const input = el.querySelector('#ty-in'), target = el.querySelector('#ty-target');
    let start = null;
    input.oninput = () => {
      if (!start) start = performance.now();
      const v = input.value;
      if (phrase.startsWith(v)) {
        input.classList.remove('is-invalid');
        target.innerHTML = `<span class="text-success">${phrase.slice(0, v.length)}</span>${phrase.slice(v.length)}`;
        if (v === phrase) {
          const mins = (performance.now() - start) / 60000;
          const wpm = Math.round(phrase.split(' ').length / mins);
          input.disabled = true;
          dgSetText(el, '#ty-score', wpm);
          const isNew = dgSaveBest('typing', wpm);
          dgSetText(el, '#ty-best', dgBest('typing') + ' PPM');
          target.innerHTML = `<span class="text-success fw-bold">✅ ¡Completado! ${wpm} palabras/min ${isNew ? '· 🎉 ¡Récord!' : ''}</span>`;
          el.appendChild(dgRetryBtn(el, game));
        }
      } else {
        input.classList.add('is-invalid');
      }
    };
  },
},

// ── 11: Piedra, Papel, Tijera ────────────────────────────────────────────────
{
  name: 'Piedra, Papel, Tijera', icon: '✊', desc: 'Al mejor de 5 contra la máquina',
  render(el) {
    const game = this;
    const opts = [['✊','piedra'], ['✋','papel'], ['✌️','tijera']];
    let me = 0, cpu = 0;
    el.innerHTML = `
      <div class="text-center fs-4 mb-1"><span id="ppt-me" class="text-success fw-bold">0</span> — <span id="ppt-cpu" class="text-danger fw-bold">0</span></div>
      <div class="text-center mb-3" style="font-size:2.5rem;min-height:1.3em" id="ppt-show">🤜 🤛</div>
      <div class="d-flex gap-2 justify-content-center" id="ppt-btns">
        ${opts.map((o, i) => `<button class="btn btn-outline-secondary" style="font-size:1.5rem" data-i="${i}">${o[0]}</button>`).join('')}
      </div>
      <div class="text-center text-muted small mt-2" id="ppt-msg">Elige tu jugada</div>`;
    el.querySelectorAll('#ppt-btns button').forEach(b => b.onclick = () => {
      const i = parseInt(b.dataset.i), j = Math.floor(Math.random() * 3);
      el.querySelector('#ppt-show').textContent = `${opts[i][0]} vs ${opts[j][0]}`;
      let msg;
      if (i === j) msg = '🤝 Empate';
      else if ((i - j + 3) % 3 === 1) { me++; msg = '✅ ¡Punto para ti!'; }
      else { cpu++; msg = '❌ Punto para la máquina'; }
      dgSetText(el, '#ppt-me', me); dgSetText(el, '#ppt-cpu', cpu);
      dgSetText(el, '#ppt-msg', msg);
      if (me === 3 || cpu === 3) {
        const won = me === 3;
        if (won) {
          const wins = parseInt(dgBest('ppt') || 0) + 1;
          localStorage.setItem('porra_dg_ppt', wins);
        }
        setTimeout(() => {
          el.innerHTML = `<div class="text-center py-3">
            <div style="font-size:3rem">${won ? '🏆' : '🤖'}</div>
            <div class="fw-bold fs-3">${won ? '¡Ganaste!' : 'Gana la máquina'}</div>
            <div class="text-muted small">${me} — ${cpu}</div>
            <div class="small mt-1">Victorias totales: ${dgBest('ppt') || 0}</div>
          </div>`;
          el.appendChild(dgRetryBtn(el, game));
        }, 900);
      }
    });
  },
},

// ── 12: Wordle Futbolero ─────────────────────────────────────────────────────
{
  name: 'Wordle Futbolero', icon: '📝', desc: 'Adivina la palabra de 5 letras',
  render(el) {
    const game = this;
    const words = ['GOLES','SAQUE','FALTA','PENAL','BOTAS','MUNDO','COPAS','PASES','REDES','BANDA','GRADA','JUEGO','TANDA','LIGAS','FICHA','CANTO','PRIMA','CRACK'];
    const word = words[dgDay() % words.length];
    let row = 0;
    const maxRows = 6;
    el.innerHTML = `
      <div id="wd-grid" class="mb-2" style="display:grid;grid-template-rows:repeat(${maxRows},1fr);gap:4px"></div>
      <div class="d-flex gap-2">
        <input type="text" class="form-control text-uppercase" id="wd-in" maxlength="5" placeholder="5 letras..." autocomplete="off">
        <button class="btn btn-primary fw-bold" id="wd-go">Probar</button>
      </div>
      <div class="text-muted small text-center mt-1">Palabra futbolera del día · Racha: ${dgBest('wordle') || 0}</div>`;
    const grid = el.querySelector('#wd-grid');
    for (let r = 0; r < maxRows; r++) {
      const rowEl = document.createElement('div');
      rowEl.style.cssText = 'display:grid;grid-template-columns:repeat(5,1fr);gap:4px';
      for (let c = 0; c < 5; c++) {
        const cell = document.createElement('div');
        cell.style.cssText = 'aspect-ratio:1;max-height:42px;border:1px solid #444;border-radius:6px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:1.1rem;background:#10101c';
        rowEl.appendChild(cell);
      }
      grid.appendChild(rowEl);
    }
    const input = el.querySelector('#wd-in');
    const submit = () => {
      const v = input.value.toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
      if (v.length !== 5 || !/^[A-ZÑ]+$/.test(v)) return;
      const cells = grid.children[row].children;
      const target = word.split('');
      const used = new Array(5).fill(false);
      // greens first
      const status = new Array(5).fill('absent');
      for (let i = 0; i < 5; i++) if (v[i] === target[i]) { status[i] = 'correct'; used[i] = true; }
      for (let i = 0; i < 5; i++) {
        if (status[i] === 'correct') continue;
        const j = target.findIndex((ch, k) => ch === v[i] && !used[k]);
        if (j !== -1) { status[i] = 'present'; used[j] = true; }
      }
      for (let i = 0; i < 5; i++) {
        cells[i].textContent = v[i];
        cells[i].style.background = status[i] === 'correct' ? '#198754' : status[i] === 'present' ? '#b8860b' : '#2a2a35';
      }
      row++;
      input.value = '';
      if (v === word) {
        localStorage.setItem('porra_dg_wordle', parseInt(dgBest('wordle') || 0) + 1);
        input.disabled = true;
        const div = document.createElement('div');
        div.className = 'alert alert-success py-2 small text-center mt-2 mb-0';
        div.textContent = `🎉 ¡Acertaste en ${row} intento${row > 1 ? 's' : ''}!`;
        el.appendChild(div);
      } else if (row >= maxRows) {
        input.disabled = true;
        const div = document.createElement('div');
        div.className = 'alert alert-danger py-2 small text-center mt-2 mb-0';
        div.textContent = `La palabra era: ${word}`;
        el.appendChild(div);
        el.appendChild(dgRetryBtn(el, game));
      }
    };
    el.querySelector('#wd-go').onclick = submit;
    input.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
  },
},

// ── 13: Memoria Numérica ─────────────────────────────────────────────────────
{
  name: 'Memoria Numérica', icon: '🧮', desc: 'Memoriza números cada vez más largos',
  render(el) {
    const game = this;
    let digits = 3;
    el.innerHTML = `
      <div class="text-center fw-bold mb-2" style="font-size:1.8rem;letter-spacing:3px;min-height:1.5em" id="mn-show">—</div>
      <div class="d-flex gap-2 mb-2">
        <input type="number" class="form-control" id="mn-in" placeholder="¿Qué número era?" disabled>
        <button class="btn btn-primary fw-bold" id="mn-go">Empezar</button>
      </div>
      <div class="text-center small text-muted">Dígitos: <strong id="mn-lvl" class="text-info">3</strong> · Récord: <strong class="text-warning">${dgBest('memnum') || '—'}</strong></div>`;
    const show = el.querySelector('#mn-show'), input = el.querySelector('#mn-in'), btn = el.querySelector('#mn-go');
    let current = '';
    const playRound = () => {
      current = '';
      for (let i = 0; i < digits; i++) current += Math.floor(Math.random() * 10);
      if (current[0] === '0') current = '1' + current.slice(1);
      show.textContent = current;
      input.disabled = true; input.value = '';
      dgSetText(el, '#mn-lvl', digits);
      setTimeout(() => {
        show.textContent = '🙈';
        input.disabled = false; input.focus();
      }, 800 + digits * 350);
    };
    const check = () => {
      if (input.disabled) return;
      if (input.value === current) {
        digits++;
        show.textContent = '✅';
        setTimeout(playRound, 600);
      } else {
        const lvl = digits - 1;
        const isNew = dgSaveBest('memnum', lvl);
        el.innerHTML = `<div class="text-center py-3">
          <div style="font-size:3rem">🧮</div>
          <div class="fw-bold fs-4">Era ${current}</div>
          <div class="text-muted small">Llegaste a ${lvl} dígitos seguidos</div>
          <div class="small mt-1">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + dgBest('memnum')}</div>
        </div>`;
        el.appendChild(dgRetryBtn(el, game));
      }
    };
    btn.onclick = () => { btn.disabled = true; playRound(); };
    input.onkeydown = (e) => { if (e.key === 'Enter') check(); };
    input.oninput = () => { if (input.value.length >= digits) check(); };
  },
},

// ── 14: Caza Balones ─────────────────────────────────────────────────────────
{
  name: 'Caza Balones', icon: '🥅', desc: 'Pilla los balones, esquiva las bombas (20s)',
  render(el) {
    const game = this;
    el.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px" id="wm-grid"></div>
      ${dgScoreBar('wm', 'Récord', 'pts')}
      <button class="btn btn-success btn-sm w-100 mt-2 fw-bold" id="wm-btn"><i class="bi bi-play-fill"></i> ¡Jugar!</button>`;
    dgSetText(el, '#wm-best', dgBest('topos') || '—');
    const grid = el.querySelector('#wm-grid');
    const cells = [];
    for (let i = 0; i < 9; i++) {
      const c = document.createElement('button');
      c.style.cssText = 'aspect-ratio:1.3;border-radius:8px;border:1px solid #333;background:#10101c;font-size:1.6rem;cursor:pointer';
      c.textContent = '';
      grid.appendChild(c); cells.push(c);
    }
    let score = 0, running = false, spawner = null, timer = null, secs = 20;
    const btn = el.querySelector('#wm-btn');
    const clearCells = () => cells.forEach(c => { c.textContent = ''; c.onclick = null; });
    const spawn = () => {
      clearCells();
      const i = Math.floor(Math.random() * 9);
      const isBomb = Math.random() < 0.25;
      cells[i].textContent = isBomb ? '🧨' : '⚽';
      cells[i].onclick = () => {
        score += isBomb ? -3 : 1;
        if (score < 0) score = 0;
        dgSetText(el, '#wm-score', score);
        cells[i].textContent = isBomb ? '💥' : '🥅';
        setTimeout(spawn, 150);
      };
    };
    btn.onclick = () => {
      if (running) return;
      running = true; score = 0; secs = 20;
      dgSetText(el, '#wm-score', '0');
      btn.disabled = true;
      spawner = setInterval(spawn, 900);
      spawn();
      timer = setInterval(() => {
        secs--;
        btn.innerHTML = `<i class="bi bi-stopwatch-fill"></i> ${secs}s`;
        if (secs <= 0) {
          clearInterval(timer); clearInterval(spawner);
          running = false; clearCells();
          const isNew = dgSaveBest('topos', score);
          dgSetText(el, '#wm-best', dgBest('topos'));
          btn.disabled = false;
          btn.innerHTML = isNew ? `🎉 ¡Récord! ${score} pts – Repetir` : `<i class="bi bi-arrow-repeat"></i> Repetir (${score} pts)`;
        }
      }, 1000);
    };
  },
},

// ── 15: Capitales ────────────────────────────────────────────────────────────
{
  name: 'Capitales del Mundial', icon: '🏛️', desc: '¿Conoces la capital de cada selección?',
  render(el) {
    dgQuiz(el, this, 'capitales', (rng) => {
      const opts = dgPick(DG_TEAMS, 4, rng);
      const ans = opts[Math.floor(rng() * 4)];
      return {
        prompt: `${ans[1]} ¿Capital de <span class="text-warning">${ans[0]}</span>?`,
        options: opts.map(t => t[2]),
        answer: ans[2],
      };
    });
  },
},

// ── 16: Orden Alfabético ─────────────────────────────────────────────────────
{
  name: 'Orden Alfabético', icon: '🔤', desc: 'Pulsa las selecciones en orden A→Z',
  render(el) {
    const game = this;
    const teams = dgPick(DG_TEAMS, 6);
    const sorted = teams.slice().sort((a, b) => a[0].localeCompare(b[0], 'es'));
    let next = 0, start = null;
    el.innerHTML = `
      <div class="text-muted small text-center mb-2">Récord: <strong class="text-warning">${dgBest('alfabeto') ? dgBest('alfabeto') + ' s' : '—'}</strong></div>
      <div class="d-grid gap-2" id="ab-list"></div>`;
    const list = el.querySelector('#ab-list');
    dgShuffle(teams).forEach(t => {
      const b = document.createElement('button');
      b.className = 'btn btn-outline-secondary btn-sm text-start';
      b.innerHTML = `${t[1]} ${t[0]}`;
      b.onclick = () => {
        if (!start) start = performance.now();
        if (t[0] === sorted[next][0]) {
          b.className = 'btn btn-success btn-sm text-start';
          b.disabled = true;
          next++;
          if (next === sorted.length) {
            const secs = ((performance.now() - start) / 1000).toFixed(2);
            const isNew = dgSaveBest('alfabeto', parseFloat(secs), false);
            const div = document.createElement('div');
            div.className = 'alert alert-success py-2 small text-center mt-1 mb-0';
            div.textContent = `✅ ${secs}s ${isNew ? '· 🎉 ¡Nuevo récord!' : ''}`;
            el.appendChild(div);
            el.appendChild(dgRetryBtn(el, game));
          }
        } else {
          b.classList.add('btn-danger');
          setTimeout(() => b.classList.remove('btn-danger'), 350);
        }
      };
      list.appendChild(b);
    });
  },
},

// ── 17: Cronómetro Ciego ─────────────────────────────────────────────────────
{
  name: 'Cronómetro Ciego', icon: '⏱️', desc: 'Para el crono justo en 5.00 segundos',
  render(el) {
    const game = this;
    el.innerHTML = `
      <div class="text-center fw-bold mb-2" style="font-size:2.6rem" id="cc-display">0.00</div>
      <div class="text-muted small text-center mb-2">El contador se oculta a los 2s. ¡Páralo en 5.00!</div>
      <button class="btn btn-success w-100 fw-bold" id="cc-btn"><i class="bi bi-play-fill"></i> Empezar</button>
      ${dgScoreBar('cc', 'Mejor desvío', 's')}`;
    dgSetText(el, '#cc-best', dgBest('crono') ? '±' + dgBest('crono') + 's' : '—');
    const disp = el.querySelector('#cc-display'), btn = el.querySelector('#cc-btn');
    let start = 0, raf = null, running = false;
    const tick = () => {
      const t = (performance.now() - start) / 1000;
      disp.textContent = t < 2 ? t.toFixed(2) : '🙈';
      raf = requestAnimationFrame(tick);
    };
    btn.onclick = () => {
      if (!running) {
        running = true; start = performance.now();
        btn.innerHTML = '<i class="bi bi-stop-fill"></i> ¡PARA!';
        btn.className = 'btn btn-danger w-100 fw-bold';
        tick();
      } else {
        cancelAnimationFrame(raf); running = false;
        const t = (performance.now() - start) / 1000;
        const diff = Math.abs(t - 5);
        disp.textContent = t.toFixed(2);
        const isNew = dgSaveBest('crono', parseFloat(diff.toFixed(3)), false);
        dgSetText(el, '#cc-score', '±' + diff.toFixed(2));
        dgSetText(el, '#cc-best', '±' + dgBest('crono') + 's');
        const msgs = [[0.05,'🎯 ¡INHUMANO!'],[0.15,'🔥 Increíble'],[0.4,'👍 Muy bien'],[1,'🙂 Casi casi'],[99,'😅 Uy...']];
        btn.className = 'btn btn-success w-100 fw-bold';
        btn.innerHTML = `${msgs.find(([m]) => diff <= m)[1]} ${isNew ? '· 🎉 ¡Récord!' : ''} – Repetir`;
        running = false;
      }
    };
  },
},

// ── 18: Doble o Nada ─────────────────────────────────────────────────────────
{
  name: 'Doble o Nada', icon: '🪙', desc: 'Cara o cruz: ¿hasta dónde llegarás?',
  render(el) {
    const game = this;
    let pot = 10;
    el.innerHTML = `
      <div class="text-center mb-1" style="font-size:2.5rem" id="dn-coin">🪙</div>
      <div class="text-center fw-bold fs-3 mb-2"><span id="dn-pot" class="text-warning">10</span> pts</div>
      <div class="d-flex gap-2 mb-2">
        <button class="btn btn-outline-light w-50 fw-bold" id="dn-cara">🙂 Cara</button>
        <button class="btn btn-outline-light w-50 fw-bold" id="dn-cruz">✖️ Cruz</button>
      </div>
      <button class="btn btn-warning btn-sm w-100 fw-bold" id="dn-out">💰 Plantarse</button>
      <div class="text-center small text-muted mt-2">Récord: <strong class="text-warning">${dgBest('doble') || '—'} pts</strong></div>`;
    const coin = el.querySelector('#dn-coin');
    const finish = (msg, emoji) => {
      el.innerHTML = `<div class="text-center py-3">
        <div style="font-size:3rem">${emoji}</div>
        <div class="fw-bold fs-3">${msg}</div>
        <div class="small mt-1">Récord: ${dgBest('doble') || 0} pts</div>
      </div>`;
      el.appendChild(dgRetryBtn(el, game));
    };
    const play = (choice) => {
      coin.style.transition = 'transform .5s';
      coin.style.transform = 'rotateY(720deg)';
      setTimeout(() => {
        coin.style.transition = 'none'; coin.style.transform = 'none';
        const result = Math.random() < 0.5 ? 'cara' : 'cruz';
        coin.textContent = result === 'cara' ? '🙂' : '✖️';
        if (choice === result) {
          pot *= 2;
          dgSetText(el, '#dn-pot', pot);
          dgSaveBest('doble', pot);
        } else {
          finish('¡Perdiste todo!', '💸');
        }
      }, 500);
    };
    el.querySelector('#dn-cara').onclick = () => play('cara');
    el.querySelector('#dn-cruz').onclick = () => play('cruz');
    el.querySelector('#dn-out').onclick = () => {
      dgSaveBest('doble', pot);
      finish(`Te llevas ${pot} pts`, '💰');
    };
  },
},

// ── 19: Tragaperras ──────────────────────────────────────────────────────────
{
  name: 'Tragaperras Mundialista', icon: '🎰', desc: 'Alinea 3 símbolos iguales',
  render(el) {
    const symbols = ['⚽','🏆','🥅','🧤','🟨','🌍'];
    el.innerHTML = `
      <div class="d-flex justify-content-center gap-2 mb-3" id="sl-reels">
        ${[0,1,2].map(i => `<div id="sl-r${i}" style="width:64px;height:64px;background:#10101c;border:2px solid #444;
          border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:2rem">❔</div>`).join('')}
      </div>
      <button class="btn btn-warning w-100 fw-bold" id="sl-btn">🎰 ¡Tirar!</button>
      <div class="text-center small text-muted mt-2" id="sl-msg">Jackpots: ${dgBest('slots') || 0}</div>`;
    const reels = [0,1,2].map(i => el.querySelector('#sl-r' + i));
    const btn = el.querySelector('#sl-btn');
    btn.onclick = () => {
      btn.disabled = true;
      const finals = [0,1,2].map(() => symbols[Math.floor(Math.random() * symbols.length)]);
      reels.forEach((r, i) => {
        let spins = 0;
        const iv = setInterval(() => {
          r.textContent = symbols[Math.floor(Math.random() * symbols.length)];
          if (++spins > 8 + i * 5) {
            clearInterval(iv);
            r.textContent = finals[i];
            if (i === 2) {
              btn.disabled = false;
              const [a, b, c] = finals;
              if (a === b && b === c) {
                localStorage.setItem('porra_dg_slots', parseInt(dgBest('slots') || 0) + 1);
                dgSetText(el, '#sl-msg', `🎉 ¡¡JACKPOT ${a}${a}${a}!! · Total: ${dgBest('slots')}`);
              } else if (a === b || b === c || a === c) {
                dgSetText(el, '#sl-msg', '😮 ¡Casi! Dos iguales');
              } else {
                dgSetText(el, '#sl-msg', `Sin suerte... · Jackpots: ${dgBest('slots') || 0}`);
              }
            }
          }
        }, 70);
      });
    };
  },
},

// ── 20: Trivia Mundialista ───────────────────────────────────────────────────
{
  name: 'Trivia Mundialista', icon: '❓', desc: 'Historia de los Mundiales',
  render(el) {
    const QS = [
      ['¿Quién ganó el Mundial 2022?', ['Argentina','Francia','Brasil','Croacia'], 'Argentina'],
      ['¿Cuántos Mundiales tiene Brasil?', ['5','4','3','6'], '5'],
      ['Máximo goleador histórico de los Mundiales', ['Miroslav Klose','Ronaldo','Pelé','Messi'], 'Miroslav Klose'],
      ['¿Dónde se jugó el primer Mundial (1930)?', ['Uruguay','Italia','Brasil','Francia'], 'Uruguay'],
      ['¿Quién ganó el Mundial 2018?', ['Francia','Croacia','Alemania','España'], 'Francia'],
      ['2026 es el primer Mundial con...', ['48 equipos','32 equipos','24 equipos','40 equipos'], '48 equipos'],
      ['¿En qué año fue el Mundial de España?', ['1982','1978','1986','1990'], '1982'],
      ['¿Cuántos países organizan el Mundial 2026?', ['3','2','1','4'], '3'],
      ['¿Quién marcó "la mano de Dios" (1986)?', ['Maradona','Pelé','Valdano','Burruchaga'], 'Maradona'],
      ['¿Quién ganó el Mundial 2010?', ['España','Países Bajos','Alemania','Uruguay'], 'España'],
      ['¿En qué Mundial debutó el VAR?', ['2018','2014','2010','2022'], '2018'],
      ['Más goles en un solo Mundial (13 en 1958)', ['Just Fontaine','Pelé','Kocsis','Müller'], 'Just Fontaine'],
      ['Único país presente en TODOS los Mundiales', ['Brasil','Alemania','Argentina','Italia'], 'Brasil'],
      ['Balón de Oro del Mundial 2022', ['Messi','Mbappé','Modric','Griezmann'], 'Messi'],
      ['¿Dónde se juega la final de 2026?', ['Nueva Jersey','Los Ángeles','Ciudad de México','Dallas'], 'Nueva Jersey'],
      ['¿Quién ganó el Mundial 2014?', ['Alemania','Argentina','Brasil','Países Bajos'], 'Alemania'],
      ['Resultado del Brasil–Alemania de 2014', ['1-7','0-5','2-6','1-5'], '1-7'],
      ['Primer Mundial jugado en Asia', ['2002','1998','2006','2010'], '2002'],
      ['¿Quién ganó el Mundial 2006?', ['Italia','Francia','Alemania','Portugal'], 'Italia'],
      ['¿Cuántos Mundiales ganó Italia?', ['4','3','5','2'], '4'],
      ['Bota de Oro 2022 (8 goles)', ['Mbappé','Messi','Giroud','Álvarez'], 'Mbappé'],
      ['¿Quién falló el penalti decisivo en la final de 1994?', ['Roberto Baggio','Baresi','Massaro','Romário'], 'Roberto Baggio'],
      ['Anfitrión del Mundial 2010', ['Sudáfrica','Brasil','Alemania','Japón'], 'Sudáfrica'],
      ['El goleador más joven de un Mundial (17 años)', ['Pelé','Mbappé','Owen','Messi'], 'Pelé'],
      ['¿Quién ganó el Mundial 1998?', ['Francia','Brasil','Italia','Países Bajos'], 'Francia'],
      ['Mascota del Mundial España 82', ['Naranjito','Footix','Zakumi','Pique'], 'Naranjito'],
      ['¿Qué selección es "La Naranja Mecánica"?', ['Países Bajos','Bélgica','Suecia','Australia'], 'Países Bajos'],
      ['¿Cuántas finales ha perdido Alemania?', ['4','2','3','5'], '4'],
      ['Sede de la final del Mundial 2022', ['Lusail','Doha','Al Rayán','Al Jor'], 'Lusail'],
      ['¿Qué país NO ha ganado nunca un Mundial?', ['Países Bajos','Uruguay','Inglaterra','Francia'], 'Países Bajos'],
      ['Goles de Messi en Mundiales', ['13','10','8','16'], '13'],
    ];
    const game = this;
    const rng = dgRng(dgDay() * 31 + 7);
    const qs = dgPick(QS, 5, rng);
    let i = 0, score = 0;
    const next = () => {
      if (i >= qs.length) {
        const isNew = dgSaveBest('trivia', score);
        el.innerHTML = `<div class="text-center py-3">
          <div style="font-size:3rem">${score >= 4 ? '🏆' : '📚'}</div>
          <div class="fw-bold fs-2">${score}/5</div>
          <div class="small">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + (dgBest('trivia') || 0) + '/5'}</div>
        </div>`;
        el.appendChild(dgRetryBtn(el, game));
        return;
      }
      const [q, opts, ans] = qs[i];
      i++;
      el.innerHTML = `
        <div class="text-center mb-2"><span class="badge bg-dark border border-secondary">Pregunta ${i}/5 · ✅ ${score}</span></div>
        <div class="fw-bold mb-3" style="min-height:2.5em">${q}</div>
        <div class="d-grid gap-2" id="tr-opts"></div>`;
      const box = el.querySelector('#tr-opts');
      dgShuffle(opts).forEach(o => {
        const b = document.createElement('button');
        b.className = 'btn btn-outline-secondary btn-sm text-start';
        b.textContent = o;
        b.onclick = () => {
          const ok = o === ans;
          if (ok) score++;
          box.querySelectorAll('button').forEach(x => {
            x.disabled = true;
            if (x.textContent === ans) x.className = 'btn btn-success btn-sm text-start';
            else if (x === b) x.className = 'btn btn-danger btn-sm text-start';
          });
          setTimeout(next, ok ? 600 : 1400);
        };
        box.appendChild(b);
      });
    };
    next();
  },
},

// ── 21: Encuentra el Diferente ───────────────────────────────────────────────
{
  name: 'Encuentra el Diferente', icon: '🔍', desc: 'Un cuadro tiene otro tono, ¿cuál?',
  render(el) {
    const game = this;
    let level = 1;
    const draw = () => {
      const n = Math.min(2 + Math.ceil(level / 2), 6);
      const hue = Math.floor(Math.random() * 360);
      const diff = Math.max(28 - level * 2.5, 5);
      const target = Math.floor(Math.random() * n * n);
      el.innerHTML = `
        <div class="text-center small text-muted mb-2">Nivel: <strong class="text-info">${level}</strong> · Récord: <strong class="text-warning">${dgBest('diferente') || '—'}</strong></div>
        <div style="display:grid;grid-template-columns:repeat(${n},1fr);gap:4px" id="fd-grid"></div>`;
      const grid = el.querySelector('#fd-grid');
      for (let i = 0; i < n * n; i++) {
        const c = document.createElement('button');
        const l = i === target ? 52 + diff / 2 : 52 - diff / 2;
        c.style.cssText = `aspect-ratio:1;border:none;border-radius:6px;cursor:pointer;background:hsl(${hue},65%,${l}%)`;
        c.onclick = () => {
          if (i === target) { level++; draw(); }
          else {
            const lvl = level - 1;
            const isNew = dgSaveBest('diferente', lvl);
            el.innerHTML = `<div class="text-center py-3">
              <div style="font-size:3rem">👁️</div>
              <div class="fw-bold fs-3">Nivel ${lvl}</div>
              <div class="small">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + (dgBest('diferente') || 0)}</div>
            </div>`;
            el.appendChild(dgRetryBtn(el, game));
          }
        };
        grid.appendChild(c);
      }
    };
    draw();
  },
},

// ── 22: Reflejos de Portero ──────────────────────────────────────────────────
{
  name: 'Reflejos de Portero', icon: '🧤', desc: 'Vuela hacia donde va el balón',
  render(el) {
    const game = this;
    const dirs = [['⬅️', 0], ['⬆️', 1], ['➡️', 2]];
    let round = 0, totalMs = 0, current = -1, shownAt = 0;
    el.innerHTML = `
      <div class="text-center" style="font-size:2.6rem;min-height:1.4em" id="gk-show">🧤</div>
      <div class="text-center small text-muted mb-2" id="gk-msg">Pulsa la dirección del balón. 10 paradas.</div>
      <div class="d-flex gap-2" id="gk-btns">
        ${dirs.map(d => `<button class="btn btn-outline-light w-100 fw-bold fs-5" data-d="${d[1]}" disabled>${d[0]}</button>`).join('')}
      </div>
      <button class="btn btn-success btn-sm w-100 mt-2 fw-bold" id="gk-start"><i class="bi bi-play-fill"></i> ¡Jugar!</button>
      <div class="text-center small text-muted mt-1">Récord: <strong class="text-warning">${dgBest('portero') ? dgBest('portero') + ' ms/parada' : '—'}</strong></div>`;
    const show = el.querySelector('#gk-show');
    const btns = [...el.querySelectorAll('#gk-btns button')];
    const next = () => {
      round++;
      if (round > 10) {
        const avg = Math.round(totalMs / 10);
        const isNew = dgSaveBest('portero', avg, false);
        el.innerHTML = `<div class="text-center py-3">
          <div style="font-size:3rem">🧤</div>
          <div class="fw-bold fs-3">${avg} ms</div>
          <div class="text-muted small">media por parada</div>
          <div class="small mt-1">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + dgBest('portero') + ' ms'}</div>
        </div>`;
        el.appendChild(dgRetryBtn(el, game));
        return;
      }
      show.textContent = '🧤';
      dgSetText(el, '#gk-msg', `Parada ${round}/10...`);
      setTimeout(() => {
        current = Math.floor(Math.random() * 3);
        show.textContent = ['↖️⚽','⬆️⚽','↗️⚽'][current];
        shownAt = performance.now();
      }, 400 + Math.random() * 1200);
    };
    btns.forEach(b => b.onclick = () => {
      if (current < 0) return;
      const d = parseInt(b.dataset.d);
      if (d === current) {
        totalMs += performance.now() - shownAt;
        current = -1;
        show.textContent = '🛡️';
        setTimeout(next, 300);
      } else {
        totalMs += 800; // penalización
        current = -1;
        show.textContent = '🥅 ¡Gol!';
        setTimeout(next, 400);
      }
    });
    el.querySelector('#gk-start').onclick = (e) => {
      e.target.style.display = 'none';
      btns.forEach(b => b.disabled = false);
      next();
    };
  },
},

// ── 23: Memoria de Posiciones ────────────────────────────────────────────────
{
  name: 'Memoria de Posiciones', icon: '💡', desc: 'Repite el patrón de casillas',
  render(el) {
    const game = this;
    let seq = [], pos = 0, playing = false;
    el.innerHTML = `
      <div class="text-center small text-muted mb-2">Nivel: <strong id="mp-lvl" class="text-info">0</strong> · Récord: <strong class="text-warning">${dgBest('posiciones') || '—'}</strong></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px" id="mp-grid"></div>
      <button class="btn btn-success btn-sm w-100 mt-2 fw-bold" id="mp-btn"><i class="bi bi-play-fill"></i> Empezar</button>`;
    const grid = el.querySelector('#mp-grid');
    const cells = [];
    for (let i = 0; i < 9; i++) {
      const c = document.createElement('button');
      c.style.cssText = 'aspect-ratio:1.4;border-radius:8px;border:1px solid #444;background:#1b1c2a;cursor:pointer;transition:background .15s';
      c.onclick = () => {
        if (!playing) return;
        flash(i, '#0d6efd');
        if (i === seq[pos]) {
          pos++;
          if (pos === seq.length) { playing = false; setTimeout(nextLevel, 600); }
        } else {
          playing = false;
          const lvl = seq.length - 1;
          const isNew = dgSaveBest('posiciones', lvl);
          const btn = el.querySelector('#mp-btn');
          btn.disabled = false;
          btn.innerHTML = `❌ Nivel ${lvl} ${isNew ? '· 🎉 ¡Récord!' : ''} – Reintentar`;
          seq = [];
        }
      };
      grid.appendChild(c); cells.push(c);
    }
    const flash = (i, color) => {
      cells[i].style.background = color || '#ffc107';
      setTimeout(() => cells[i].style.background = '#1b1c2a', 300);
    };
    const playSeq = (k) => {
      if (k >= seq.length) { playing = true; pos = 0; return; }
      flash(seq[k]);
      setTimeout(() => playSeq(k + 1), 500);
    };
    const nextLevel = () => {
      seq.push(Math.floor(Math.random() * 9));
      dgSetText(el, '#mp-lvl', seq.length);
      setTimeout(() => playSeq(0), 350);
    };
    el.querySelector('#mp-btn').onclick = (e) => {
      e.target.disabled = true; e.target.innerHTML = 'Memoriza...';
      seq = []; nextLevel();
    };
  },
},

// ── 24: ¿Dónde está la Copa? ─────────────────────────────────────────────────
{
  name: '¿Dónde está la Copa?', icon: '🏆', desc: 'Sigue el trofeo con la mirada',
  render(el) {
    const game = this;
    let level = 1;
    el.innerHTML = `
      <div class="text-center small text-muted mb-2">Nivel: <strong class="text-info" id="cup-lvl">1</strong> · Récord: <strong class="text-warning">${dgBest('copa') || '—'}</strong></div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px" id="cup-grid"></div>
      <div class="text-center small text-muted mt-2" id="cup-msg">Memoriza dónde aparece la copa</div>`;
    const grid = el.querySelector('#cup-grid');
    const cells = [];
    for (let i = 0; i < 9; i++) {
      const c = document.createElement('button');
      c.style.cssText = 'aspect-ratio:1.4;border-radius:8px;border:1px solid #444;background:#1b1c2a;font-size:1.5rem;cursor:pointer';
      grid.appendChild(c); cells.push(c);
    }
    const round = () => {
      dgSetText(el, '#cup-lvl', level);
      const target = Math.floor(Math.random() * 9);
      cells.forEach(c => { c.textContent = ''; c.onclick = null; });
      dgSetText(el, '#cup-msg', '👀 ¡Mira!');
      cells[target].textContent = '🏆';
      const showMs = Math.max(900 - level * 80, 220);
      setTimeout(() => {
        cells[target].textContent = '';
        dgSetText(el, '#cup-msg', '¿Dónde estaba?');
        cells.forEach((c, i) => c.onclick = () => {
          if (i === target) {
            c.textContent = '🏆'; level++;
            dgSetText(el, '#cup-msg', '✅ ¡Bien!');
            setTimeout(round, 700);
          } else {
            c.textContent = '❌'; cells[target].textContent = '🏆';
            const lvl = level - 1;
            const isNew = dgSaveBest('copa', lvl);
            setTimeout(() => {
              el.innerHTML = `<div class="text-center py-3">
                <div style="font-size:3rem">🏆</div>
                <div class="fw-bold fs-3">Nivel ${lvl}</div>
                <div class="small">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + (dgBest('copa') || 0)}</div>
              </div>`;
              el.appendChild(dgRetryBtn(el, game));
            }, 800);
          }
        });
      }, showMs);
    };
    setTimeout(round, 600);
  },
},

// ── 25: Dados de la Suerte ───────────────────────────────────────────────────
{
  name: 'Dados de la Suerte', icon: '🎲', desc: 'Al mejor de 5 tiradas contra la máquina',
  render(el) {
    const game = this;
    const faces = ['⚀','⚁','⚂','⚃','⚄','⚅'];
    let me = 0, cpu = 0, rounds = 0;
    el.innerHTML = `
      <div class="text-center fs-4 mb-1"><span class="text-success fw-bold" id="dd-me">0</span> — <span class="text-danger fw-bold" id="dd-cpu">0</span></div>
      <div class="d-flex justify-content-center gap-4 mb-2" style="font-size:3rem">
        <span id="dd-d1">🎲</span><span class="text-muted fs-4 align-self-center">vs</span><span id="dd-d2">🎲</span>
      </div>
      <button class="btn btn-warning w-100 fw-bold" id="dd-btn">🎲 ¡Tirar! (ronda 1/5)</button>
      <div class="text-center small text-muted mt-2">Victorias: ${dgBest('dados') || 0}</div>`;
    const btn = el.querySelector('#dd-btn');
    btn.onclick = () => {
      btn.disabled = true;
      let spins = 0;
      const iv = setInterval(() => {
        dgSetText(el, '#dd-d1', faces[Math.floor(Math.random() * 6)]);
        dgSetText(el, '#dd-d2', faces[Math.floor(Math.random() * 6)]);
        if (++spins > 10) {
          clearInterval(iv);
          const a = Math.floor(Math.random() * 6), b = Math.floor(Math.random() * 6);
          dgSetText(el, '#dd-d1', faces[a]); dgSetText(el, '#dd-d2', faces[b]);
          if (a > b) me++; else if (b > a) cpu++;
          dgSetText(el, '#dd-me', me); dgSetText(el, '#dd-cpu', cpu);
          rounds++;
          if (rounds >= 5 || me === 3 || cpu === 3) {
            const won = me > cpu;
            if (won) localStorage.setItem('porra_dg_dados', parseInt(dgBest('dados') || 0) + 1);
            setTimeout(() => {
              el.innerHTML = `<div class="text-center py-3">
                <div style="font-size:3rem">${won ? '🏆' : me === cpu ? '🤝' : '🤖'}</div>
                <div class="fw-bold fs-3">${won ? '¡Ganaste!' : me === cpu ? 'Empate' : 'Gana la máquina'}</div>
                <div class="text-muted small">${me} — ${cpu}</div>
                <div class="small mt-1">Victorias totales: ${dgBest('dados') || 0}</div>
              </div>`;
              el.appendChild(dgRetryBtn(el, game));
            }, 800);
          } else {
            btn.disabled = false;
            btn.textContent = `🎲 ¡Tirar! (ronda ${rounds + 1}/5)`;
          }
        }
      }, 80);
    };
  },
},

// ── 26: Stop la Barra ────────────────────────────────────────────────────────
{
  name: 'Stop la Barra', icon: '📊', desc: 'Para la barra en la zona verde',
  render(el) {
    const game = this;
    let level = 1, pos = 0, dir = 1, raf = null, running = false;
    el.innerHTML = `
      <div class="text-center small text-muted mb-2">Nivel: <strong class="text-info" id="sb-lvl">1</strong> · Récord: <strong class="text-warning">${dgBest('barra') || '—'}</strong></div>
      <div id="sb-track" style="position:relative;height:38px;background:#10101c;border-radius:8px;border:1px solid #333;overflow:hidden;margin-bottom:.75rem">
        <div id="sb-zone" style="position:absolute;top:0;bottom:0;background:rgba(34,197,94,.35);border-inline:2px solid #22c55e"></div>
        <div id="sb-bar" style="position:absolute;top:0;bottom:0;width:6px;background:#ffc107;border-radius:3px"></div>
      </div>
      <button class="btn btn-success w-100 fw-bold" id="sb-btn"><i class="bi bi-play-fill"></i> Empezar</button>`;
    const track = el.querySelector('#sb-track'), zone = el.querySelector('#sb-zone'),
          bar = el.querySelector('#sb-bar'), btn = el.querySelector('#sb-btn');
    let zoneStart = 0, zoneW = 0;
    const setup = () => {
      dgSetText(el, '#sb-lvl', level);
      const w = track.clientWidth;
      zoneW = Math.max(w * (0.3 - level * 0.022), w * 0.06);
      zoneStart = Math.random() * (w - zoneW);
      zone.style.left = zoneStart + 'px'; zone.style.width = zoneW + 'px';
      pos = 0; dir = 1;
    };
    const speed = () => 2.2 + level * 0.7;
    const tick = () => {
      pos += dir * speed();
      const max = track.clientWidth - 6;
      if (pos >= max) { pos = max; dir = -1; }
      if (pos <= 0) { pos = 0; dir = 1; }
      bar.style.left = pos + 'px';
      raf = requestAnimationFrame(tick);
    };
    btn.onclick = () => {
      if (!running) {
        running = true; setup(); tick();
        btn.innerHTML = '✋ ¡PARA!'; btn.className = 'btn btn-danger w-100 fw-bold';
      } else {
        cancelAnimationFrame(raf); running = false;
        const center = pos + 3;
        if (center >= zoneStart && center <= zoneStart + zoneW) {
          level++;
          btn.innerHTML = `✅ ¡Dentro! Nivel ${level} – Continuar`;
          btn.className = 'btn btn-success w-100 fw-bold';
        } else {
          const lvl = level - 1;
          const isNew = dgSaveBest('barra', lvl);
          el.innerHTML = `<div class="text-center py-3">
            <div style="font-size:3rem">📊</div>
            <div class="fw-bold fs-3">Nivel ${lvl}</div>
            <div class="small">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + (dgBest('barra') || 0)}</div>
          </div>`;
          el.appendChild(dgRetryBtn(el, game));
        }
      }
    };
  },
},

// ── 27: Secuencias Lógicas ───────────────────────────────────────────────────
{
  name: 'Secuencias Lógicas', icon: '🧩', desc: '¿Qué número sigue la serie?',
  render(el) {
    const makers = [
      (r) => { const a = 2 + Math.floor(r() * 8), d = 2 + Math.floor(r() * 9); const s = [a, a+d, a+2*d, a+3*d]; return [s, a+4*d]; },
      (r) => { const a = 1 + Math.floor(r() * 4), m = 2 + Math.floor(r() * 2); const s = [a, a*m, a*m*m, a*m*m*m]; return [s, a*m**4]; },
      (r) => { const a = 1 + Math.floor(r() * 6); const s = [a, a+1, a+3, a+6, a+10]; return [s, a+15]; },
      (r) => { const a = 1 + Math.floor(r() * 5), b = a + 1 + Math.floor(r() * 4); const s = [a, b, a+b, a+2*b, 2*a+3*b]; return [s, 3*a+5*b]; },
      (r) => { const a = 2 + Math.floor(r() * 5); const s = [a*a, (a+1)*(a+1), (a+2)*(a+2), (a+3)*(a+3)]; return [s, (a+4)*(a+4)]; },
    ];
    dgQuiz(el, this, 'secuencias', (rng) => {
      const [seq, ans] = makers[Math.floor(rng() * makers.length)](rng);
      const wrongs = new Set();
      while (wrongs.size < 3) {
        const w = ans + Math.floor(rng() * 11) - 5;
        if (w !== ans && w > 0) wrongs.add(w);
      }
      return {
        prompt: `${seq.join(', ')}, <span class="text-warning">?</span>`,
        options: dgShuffle([String(ans), ...[...wrongs].map(String)], rng),
        answer: String(ans),
      };
    });
  },
},

// ── 28: Carta Más Alta ───────────────────────────────────────────────────────
{
  name: 'Carta Más Alta', icon: '🃏', desc: 'Al mejor de 5 cartas contra la banca',
  render(el) {
    const game = this;
    const vals = ['2','3','4','5','6','7','8','9','10','J','Q','K','A'];
    const suits = ['♠️','♥️','♦️','♣️'];
    let me = 0, cpu = 0, rounds = 0;
    el.innerHTML = `
      <div class="text-center fs-4 mb-1"><span class="text-success fw-bold" id="ca-me">0</span> — <span class="text-danger fw-bold" id="ca-cpu">0</span></div>
      <div class="d-flex justify-content-center gap-3 mb-2 align-items-center">
        <div class="text-center p-2 rounded" style="background:#10101c;border:1px solid #444;min-width:64px">
          <div style="font-size:1.8rem" id="ca-c1">🂠</div><small class="text-muted">Tú</small>
        </div>
        <span class="text-muted">vs</span>
        <div class="text-center p-2 rounded" style="background:#10101c;border:1px solid #444;min-width:64px">
          <div style="font-size:1.8rem" id="ca-c2">🂠</div><small class="text-muted">Banca</small>
        </div>
      </div>
      <button class="btn btn-warning w-100 fw-bold" id="ca-btn">🃏 Robar carta (1/5)</button>
      <div class="text-center small text-muted mt-2">Victorias: ${dgBest('cartas') || 0}</div>`;
    const btn = el.querySelector('#ca-btn');
    btn.onclick = () => {
      const a = Math.floor(Math.random() * 13), b = Math.floor(Math.random() * 13);
      dgSetText(el, '#ca-c1', vals[a] + suits[Math.floor(Math.random() * 4)]);
      dgSetText(el, '#ca-c2', vals[b] + suits[Math.floor(Math.random() * 4)]);
      if (a > b) me++; else if (b > a) cpu++;
      dgSetText(el, '#ca-me', me); dgSetText(el, '#ca-cpu', cpu);
      rounds++;
      if (rounds >= 5 || me === 3 || cpu === 3) {
        const won = me > cpu;
        if (won) localStorage.setItem('porra_dg_cartas', parseInt(dgBest('cartas') || 0) + 1);
        btn.disabled = true;
        setTimeout(() => {
          el.innerHTML = `<div class="text-center py-3">
            <div style="font-size:3rem">${won ? '🏆' : me === cpu ? '🤝' : '🏦'}</div>
            <div class="fw-bold fs-3">${won ? '¡Ganaste!' : me === cpu ? 'Empate' : 'Gana la banca'}</div>
            <div class="text-muted small">${me} — ${cpu}</div>
            <div class="small mt-1">Victorias totales: ${dgBest('cartas') || 0}</div>
          </div>`;
          el.appendChild(dgRetryBtn(el, game));
        }, 900);
      } else {
        btn.textContent = `🃏 Robar carta (${rounds + 1}/5)`;
      }
    };
  },
},

// ── 29: Semáforo F1 ──────────────────────────────────────────────────────────
{
  name: 'Semáforo de Salida', icon: '🚦', desc: '5 luces rojas... ¡sal cuando se apaguen!',
  render(el) {
    const game = this;
    el.innerHTML = `
      <div class="d-flex justify-content-center gap-2 mb-3 p-2 rounded" style="background:#10101c;border:1px solid #333" id="f1-lights">
        ${[0,1,2,3,4].map(i => `<div id="f1-l${i}" style="width:28px;height:28px;border-radius:50%;background:#2a2a35;transition:background .1s"></div>`).join('')}
      </div>
      <button class="btn btn-success w-100 fw-bold" id="f1-btn"><i class="bi bi-flag-fill"></i> Preparados...</button>
      ${dgScoreBar('f1', 'Récord', 'ms')}`;
    dgSetText(el, '#f1-best', dgBest('semaforo') ? dgBest('semaforo') + ' ms' : '—');
    const btn = el.querySelector('#f1-btn');
    const lights = [0,1,2,3,4].map(i => el.querySelector('#f1-l' + i));
    let state = 'idle', goAt = 0, timeouts = [];
    const reset = () => { lights.forEach(l => l.style.background = '#2a2a35'); timeouts.forEach(clearTimeout); timeouts = []; };
    btn.onclick = () => {
      if (state === 'idle') {
        state = 'arming'; reset();
        btn.textContent = '...';
        lights.forEach((l, i) => timeouts.push(setTimeout(() => l.style.background = '#dc3545', 600 * (i + 1))));
        const goDelay = 600 * 5 + 400 + Math.random() * 1800;
        timeouts.push(setTimeout(() => {
          reset(); state = 'go'; goAt = performance.now();
          btn.textContent = '🟢 ¡¡SAL!!';
        }, goDelay));
        timeouts.push(setTimeout(() => { if (state === 'arming') btn.textContent = '¡Espera a que se apaguen!'; }, 600));
      } else if (state === 'arming') {
        state = 'idle'; reset();
        btn.textContent = '🚨 ¡Salida en falso! – Reintentar';
      } else if (state === 'go') {
        const ms = Math.round(performance.now() - goAt);
        state = 'idle';
        dgSetText(el, '#f1-score', ms);
        const isNew = dgSaveBest('semaforo', ms, false);
        dgSetText(el, '#f1-best', dgBest('semaforo') + ' ms');
        const r = [[160,'🏎️ ¡Salida de Fórmula 1!'],[230,'🔥 Brutal'],[320,'👍 Buena salida'],[500,'🙂 Normal'],[99999,'🐢 Te dejaron atrás']];
        btn.innerHTML = `${r.find(([m]) => ms <= m)[1]} ${isNew ? '· 🎉 ¡Récord!' : ''} – Repetir`;
      }
    };
  },
},

// ── 30: Anagrama Mundialista ─────────────────────────────────────────────────
{
  name: 'Anagrama Mundialista', icon: '🔀', desc: 'Ordena las letras de la selección',
  render(el) {
    const game = this;
    const rng = dgRng(dgDay() * 13 + 5);
    const simple = DG_TEAMS.map(t => t[0]).filter(n => !n.includes(' ') && n.length >= 5 && n.length <= 10);
    let round = 0, score = 0, start = performance.now();
    const total = 5;
    const teams = dgPick(simple, total, rng);
    const next = () => {
      if (round >= total) {
        const secs = ((performance.now() - start) / 1000).toFixed(1);
        const isNew = dgSaveBest('anagrama', score);
        el.innerHTML = `<div class="text-center py-3">
          <div style="font-size:3rem">🔀</div>
          <div class="fw-bold fs-2">${score}/${total}</div>
          <div class="text-muted small">en ${secs}s</div>
          <div class="small mt-1">${isNew ? '🎉 ¡Nuevo récord!' : 'Récord: ' + (dgBest('anagrama') || 0) + '/5'}</div>
        </div>`;
        el.appendChild(dgRetryBtn(el, game));
        return;
      }
      const name = teams[round];
      round++;
      const norm = name.toUpperCase();
      let scrambled = norm;
      while (scrambled === norm) scrambled = dgShuffle(norm.split('')).join('');
      el.innerHTML = `
        <div class="text-center mb-2"><span class="badge bg-dark border border-secondary">Selección ${round}/${total} · ✅ ${score}</span></div>
        <div class="text-center fw-bold mb-3" style="font-size:1.6rem;letter-spacing:4px">${scrambled}</div>
        <div class="d-flex gap-2">
          <input type="text" class="form-control" id="an-in" placeholder="¿Qué selección es?" autocomplete="off">
          <button class="btn btn-primary fw-bold" id="an-go">OK</button>
        </div>
        <button class="btn btn-link btn-sm text-muted w-100 mt-1" id="an-skip">Saltar →</button>`;
      const input = el.querySelector('#an-in');
      const norm2 = (s) => s.toUpperCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
      const check = () => {
        if (norm2(input.value) === norm2(name)) {
          score++;
          input.classList.add('is-valid');
          setTimeout(next, 400);
        } else {
          input.classList.add('is-invalid');
          setTimeout(() => input.classList.remove('is-invalid'), 400);
        }
      };
      el.querySelector('#an-go').onclick = check;
      el.querySelector('#an-skip').onclick = next;
      input.onkeydown = (e) => { if (e.key === 'Enter') check(); };
      input.focus();
    };
    next();
  },
},

];

// ── Inicialización ───────────────────────────────────────────────────────────
function initDailyGame() {
  const day = dgDay();
  const idx = day % DAILY_GAMES.length;
  const game = DAILY_GAMES[idx];
  const icon = document.getElementById('dg-icon');
  const title = document.getElementById('dg-title');
  const desc = document.getElementById('dg-desc');
  const body = document.getElementById('dg-body');
  if (!body) return;
  if (icon)  icon.textContent  = game.icon;
  if (title) title.textContent = game.name;
  if (desc)  desc.textContent  = game.desc;
  game.render(body);
  // Pie: posición en la rotación
  const foot = document.createElement('div');
  foot.className = 'text-center text-muted mt-2';
  foot.style.fontSize = '.68rem';
  foot.innerHTML = `🎮 Juego ${idx + 1} de ${DAILY_GAMES.length} · mañana toca otro`;
  body.parentElement.appendChild(foot);
}
