// კოდის სავარჯიშოს რედაქტორი (ბიბლიოთეკის გარეშე). მუშაობს გაუმჭვირვალე წარმოშობის iframe-ში: localStorage და cookie აქ არ არის,
// ამიტომ შენახვას მშობელი გვერდი ასრულებს (postMessage). შეტყობინებებს ვიღებთ მხოლოდ window.parent-ისგან (event.source-ით).
'use strict';
const LIMIT_MS = 5000;        // Python-ის გაშვების დროის ლიმიტი
const INIT_MS = 90000;        // Pyodide-ის ჩატვირთვის მაქსიმალური დრო
const $ = id => document.getElementById(id);
const code = $('code'), out = $('out'), prev = $('prev'), res = $('res'), runBtn = $('run'), resetBtn = $('reset'), statusEl = $('status');
let ex = null, worker = null, ready = false, running = false, runId = 0, limitTimer = 0, initTimer = 0, saveTimer = 0, renderTimer = 0;
let pending = null, prevN = 0, trap = true, resetArmed = 0, runner = '';

const post = m => parent.postMessage(m, '*');
const setStatus = t => { statusEl.textContent = t; };
const clear = el => { while (el.firstChild) el.removeChild(el.firstChild); };
function span(cls, text) { const s = document.createElement('span'); if (cls) s.className = cls; s.textContent = text; return s; }

// ---------- შეტყობინებები მშობლისგან
addEventListener('message', e => {
  if (e.source !== parent) return;
  const m = e.data;
  if (!m || typeof m !== 'object') return;
  if (m.t === 'theme' && (m.theme === 'dark' || m.theme === 'light')) document.documentElement.setAttribute('data-theme', m.theme);
  else if (m.t === 'init' && !ex) init(m);
});

function init(m) {
  const x = m.ex;
  if (!x || (x.type !== 'python' && x.type !== 'html') || typeof x.starter !== 'string' || !Array.isArray(x.checks)) return;
  ex = x;
  if (m.theme === 'dark' || m.theme === 'light') document.documentElement.setAttribute('data-theme', m.theme);
  code.value = typeof m.code === 'string' ? m.code : ex.starter;
  if (ex.type === 'html') {
    $('outlab').textContent = 'შედეგი (ცოცხალი ნახვა)'; out.hidden = true; prev.hidden = false; runBtn.disabled = false;
    setStatus('მზადაა: ცვლილება ავტომატურად ჩანს, Run ამოწმებს');
    renderPreview(false);
  } else {
    $('outlab').textContent = 'შედეგი';
    setStatus('Python-ის გარემო იტვირთება… (პირველად რამდენიმე წამი სჭირდება)');
    startWorker();
  }
  report();
}

// ---------- Python: Worker Pyodide-ით
async function startWorker() {
  ready = false; runBtn.disabled = true;
  clearTimeout(initTimer);
  try {
    if (!runner) {
      const [w, r] = await Promise.all([fetch('pyworker.js'), fetch('runner.py')]);
      if (!w.ok || !r.ok) throw new Error('სამუშაო ფაილები ვერ ჩაიტვირთა');
      runner = await r.text();
      startWorker.src = await w.text();
    }
    const url = URL.createObjectURL(new Blob([startWorker.src], { type: 'text/javascript' }));
    worker = new Worker(url);
    URL.revokeObjectURL(url);
    worker.onmessage = onWorker;
    worker.onerror = () => failInit('Worker-მა შეცდომა დააბრუნა');
    worker.postMessage({ t: 'init', base: new URL('/vendor/pyodide/', location.href).href, runner });
    initTimer = setTimeout(() => failInit('ჩატვირთვას ძალიან დიდი დრო მოუნდა'), INIT_MS);
  } catch (err) { failInit(String(err.message || err)); }
}
function failInit(why) {
  clearTimeout(initTimer);
  if (worker) { worker.terminate(); worker = null; }
  setStatus('Python-ის გარემო ვერ ჩაიტვირთა');
  clear(out); out.appendChild(span('er', 'Python-ის გარემო ვერ ჩაიტვირთა (' + why + ').\nთუ ეს საიტის მფლობელია: public/vendor/pyodide/ ცარიელია. გაუშვი tools/fetch_pyodide.py.\nთუ მოსწავლე ხარ: განაახლე გვერდი და სცადე ხელახლა.'));
}
function onWorker(e) {
  const m = e.data || {};
  if (m.t === 'ready') { clearTimeout(initTimer); ready = true; runBtn.disabled = false; setStatus('მზადაა: დააჭირე Run-ს'); }
  else if (m.t === 'result' && m.id === runId && running) { finishRun(m.data); }
  else if (m.t === 'fail') {
    if (m.stage === 'init') failInit(m.msg);
    else if (running) { finishRun(null, 'შიდა შეცდომა: ' + m.msg); }
  }
}
function runPython() {
  if (!ready || running) return;
  running = true; runBtn.disabled = true; setStatus('მუშაობს…'); res.hidden = true;
  const id = ++runId;
  worker.postMessage({ t: 'run', id, code: code.value, stdin: ex.stdin || [], checks: ex.checks });
  limitTimer = setTimeout(() => {
    if (!running || id !== runId) return;
    running = false; ready = false;
    worker.terminate(); worker = null;
    clear(out);
    out.appendChild(span('er', 'პროგრამა ' + LIMIT_MS / 1000 + ' წამზე მეტხანს მუშაობდა და შეჩერდა.\nეს ხშირად უსასრულო ციკლის ნიშანია: შეამოწმე, რომ ციკლის პირობა რაღაც მომენტში მცდარი გახდება (მაგ. მთვლელი იზრდება) ან გამოიყენე break.'));
    setStatus('დროის ლიმიტი ამოიწურა, გარემო თავიდან იტვირთება…');
    startWorker();
  }, LIMIT_MS);
}
const INTRO = {
  SyntaxError: 'სინტაქსის შეცდომა: Python-მა კოდი ვერ წაიკითხა (შეამოწმე ფრჩხილები, ორწერტილი, ბრჭყალები).',
  IndentationError: 'ჩაღრმავების შეცდომა: ხაზების დასაწყისის ცარიელი ადგილები არ ემთხვევა (ჩვეულებრივ 4 ცარიელი ადგილი).',
  TabError: 'ჩაღრმავების შეცდომა: Tab და ცარიელი ადგილები აირია.',
  NameError: 'სახელი ვერ მოიძებნა: ცვლადი ან ფუნქცია გამოიყენე იქამდე, სანამ შექმნიდი, ან სახელი არასწორად დაწერე.',
  TypeError: 'ტიპის შეცდომა: მოქმედება არ ჯდება ამ ტიპის მნიშვნელობებზე (მაგ. ტექსტი და რიცხვი).',
  ValueError: 'მნიშვნელობის შეცდომა: ტიპი სწორია, მაგრამ მნიშვნელობა არ ვარგა (მაგ. int("abc")).',
  ZeroDivisionError: 'ნულზე გაყოფა შეუძლებელია.',
  IndexError: 'ინდექსი სიის საზღვრებს სცდება.',
  KeyError: 'ასეთი გასაღები ლექსიკონში არ არის.',
  EOFError: 'input() მნიშვნელობას ელოდა, მაგრამ აღარ დარჩა. ამ რედაქტორში input() კლავიატურიდან არ იკითხება: მნიშვნელობებს სავარჯიშო აძლევს, ამიტომ input()-ს იმდენჯერ გამოძახება, რამდენიც ინსტრუქციაშია.',
};
function finishRun(d, internal) {
  clearTimeout(limitTimer); running = false; runBtn.disabled = false; setStatus('მზადაა');
  clear(out);
  if (!d) { out.appendChild(span('er', internal || 'უცნობი შეცდომა')); return; }
  if (d.out) out.appendChild(document.createTextNode(d.out));
  if (d.cut) out.appendChild(span('mu', '\n… გამოსავალი შეიკვეცა (ძალიან გრძელია)'));
  if (!d.out && !d.err) out.appendChild(span('mu', '(პროგრამა დასრულდა, დაბეჭდილი არაფერია)'));
  if (d.err) {
    const e = d.err;
    out.appendChild(span('er', (d.out ? '\n' : '') + 'პროგრამა შეცდომით გაჩერდა' + (e.line ? ' (ხაზი ' + e.line + ')' : '') + '.\n' + (INTRO[e.type] ? INTRO[e.type] + '\n' : '') + 'ორიგინალური შეტყობინება:\n' + e.msg));
  }
  showChecks(d.results);
}

// ---------- html: ცოცხალი ნახვა sandbox iframe-ში (preview.html: საკუთარი CSP, ცალკე URL)
function renderPreview(withChecks) {
  pending = { html: code.value, checks: withChecks ? ex.checks.map(c => ({ selector: c.selector, min: c.min, text_contains: c.text_contains, attr: c.attr, attr_startswith: c.attr_startswith })) : null };
  prev.src = 'preview.html?r=' + (++prevN);
}
addEventListener('message', e => {
  if (!ex || ex.type !== 'html' || e.source !== prev.contentWindow) return;
  const m = e.data;
  if (!m || typeof m !== 'object') return;
  if (m.t === 'pready' && pending) { prev.contentWindow.postMessage({ t: 'render', html: pending.html, checks: pending.checks }, '*'); pending = null; }
  else if (m.t === 'checks' && Array.isArray(m.results)) { showChecks(m.results.map(Boolean)); setStatus('მზადაა'); }
});

// ---------- შემოწმებების ჩვენება: ✓/✗; დამალულ შემოწმებას წარწერა არ აქვს
function showChecks(results) {
  clear(res);
  if (!ex.checks.length || !Array.isArray(results)) { res.hidden = true; return; }
  const n = results.filter(Boolean).length;
  const p = document.createElement('p'); p.className = 'sum';
  p.textContent = n === ex.checks.length ? 'ყველა შემოწმება გავიდა (' + n + '/' + n + ')' : 'შემოწმება გავიდა: ' + n + '/' + ex.checks.length;
  res.appendChild(p);
  const ul = document.createElement('ul');
  let hid = 0;
  ex.checks.forEach((c, i) => {
    const li = document.createElement('li'), ok = !!results[i];
    li.appendChild(span(ok ? 'y' : 'n', ok ? '✓' : '✗'));
    li.appendChild(span('', c.hidden ? 'დამალული შემოწმება ' + (++hid) : String(c.label || 'შემოწმება ' + (i + 1))));
    li.setAttribute('aria-label', (ok ? 'გავიდა: ' : 'ჩავარდა: ') + li.lastChild.textContent);
    ul.appendChild(li);
  });
  res.appendChild(ul); res.hidden = false;
}

// ---------- ღილაკები
runBtn.addEventListener('click', () => { if (!ex) return; if (ex.type === 'python') runPython(); else { setStatus('მოწმდება…'); renderPreview(true); } });
resetBtn.addEventListener('click', () => {
  if (!ex) return;
  if (code.value !== ex.starter && !resetArmed) {   // confirm() sandbox-ში აკრძალულია: ორმაგი დაჭერა
    resetBtn.textContent = 'დარწმუნებული ხარ?'; resetArmed = setTimeout(() => { resetBtn.textContent = 'Reset'; resetArmed = 0; }, 4000); return;
  }
  clearTimeout(resetArmed); resetArmed = 0; resetBtn.textContent = 'Reset';
  code.value = ex.starter; res.hidden = true; if (ex.type === 'python') clear(out); else renderPreview(false);
  report(true);
});

// ---------- textarea: Tab, Shift+Tab, Escape, ავტოჩაღრმავება
code.addEventListener('focus', () => { trap = true; });
code.addEventListener('keydown', e => {
  if (e.key === 'Escape') { trap = false; setStatus('Tab ახლა ფოკუსს გადაიტანს'); return; }
  if (e.key === 'Tab' && trap && !e.ctrlKey && !e.altKey && !e.metaKey) {
    e.preventDefault();
    const v = code.value, a = code.selectionStart, b = code.selectionEnd;
    const ls = v.lastIndexOf('\n', a - 1) + 1;
    if (a === b && !e.shiftKey) { setText(v.slice(0, a) + '    ' + v.slice(b), a + 4, a + 4); return; }
    const end = b > a && v[b - 1] === '\n' ? b - 1 : b;
    const block = v.slice(ls, end).split('\n');
    const mod = e.shiftKey ? block.map(l => l.replace(/^( {1,4}|\t)/, '')) : block.map(l => '    ' + l);
    const nv = v.slice(0, ls) + mod.join('\n') + v.slice(end);
    setText(nv, Math.max(ls, a + (mod[0].length - block[0].length)), end + mod.join('\n').length - block.join('\n').length);
  } else if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey && !e.shiftKey && code.selectionStart === code.selectionEnd) {
    const v = code.value, a = code.selectionStart, ls = v.lastIndexOf('\n', a - 1) + 1, line = v.slice(ls, a);
    let ind = (line.match(/^[ \t]*/) || [''])[0];
    if (ex && ex.type === 'python' && /:\s*$/.test(line)) ind += '    ';
    if (ind) { e.preventDefault(); setText(v.slice(0, a) + '\n' + ind + v.slice(a), a + 1 + ind.length, a + 1 + ind.length); }
  }
});
function setText(v, s, e) {   // execCommand ინარჩუნებს ბრაუზერის undo-ს; თუ არ მუშაობს, პირდაპირ ვწერთ
  code.value = v; code.setSelectionRange(s, e); code.dispatchEvent(new Event('input'));
}
code.addEventListener('input', () => {
  report();
  if (ex && ex.type === 'html') { clearTimeout(renderTimer); renderTimer = setTimeout(() => renderPreview(false), 700); }
});
function report(now) {   // შენახვას მშობელი ასრულებს (localStorage იქ არის)
  clearTimeout(saveTimer);
  const send = () => post({ t: 'code', code: code.value });
  now ? send() : (saveTimer = setTimeout(send, 400));
}

// ---------- სიმაღლე მშობელს
let lastH = 0;
new ResizeObserver(() => {
  const h = Math.ceil(document.documentElement.getBoundingClientRect().height);
  if (h !== lastH) { lastH = h; post({ t: 'height', h }); }
}).observe(document.body);
post({ t: 'ready' });
