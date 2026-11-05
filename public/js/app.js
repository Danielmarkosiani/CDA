// CDA ფრონტენდი: ჩვეულებრივი JavaScript, ეხმიანება /api-ს. ინლაინ სტილები არ გამოიყენება (CSP style-src 'self')
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dec = s => { try { return decodeURIComponent(s || ''); } catch (e) { return ''; } };
const S = { until: 0, flash: '', user: null, pending: null, courses: [], cid: '', defCid: '', ac: '', stages: [], lessons: [], done: new Set(), passed: new Set(), scores: {}, cfg: { plans: [], payInfo: '', contact: '', mentor: '', requireVerify: true, resendSeconds: 60 }, tab: 'overview', loaded: false, au: { q: '', plan: '', page: 0 }, qf: 'open', oall: false };
const MINPW = () => S.cfg.minPw || 15;   // სერვერის MIN_PW_LEN (/api/config)
const fmtDate = t => t ? new Date(t).toLocaleDateString('ka-GE') : '—';
const fmtTime = t => t ? new Date(t).toLocaleString('ka-GE', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const hrs = m => m >= 60 ? Math.floor(m / 60) + ' სთ' + (m % 60 ? ' ' + (m % 60) + ' წთ' : '') : m + ' წთ';

async function api(path, data) {
  const r = await fetch('/api/' + path, data === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'cda' }, body: JSON.stringify(data) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const er = new Error(j.error || 'შეცდომა'); er.retry = j.retry_after; throw er; }
  return j;
}
let tt;
function toast(t) { const el = $('#toast'); el.textContent = t; el.classList.add('show'); clearTimeout(tt); tt = setTimeout(() => el.classList.remove('show'), 3200); }

// მინიმალური Markdown (ჯერ ესკეიპი, მერე ფორმატირება): ## სათაური, ### ქვესათაური, - სია, 1. დანომრილი სია,
// > შენიშვნა, | ცხრილი |, **მუქი**, `კოდი`, ``` ბლოკი ```, [ტექსტი](https://...) და ![წარწერა](/img/lessons/ფაილი.svg)
// ბმული მხოლოდ https-ით (target=_blank, rel=noopener noreferrer). სურათი მხოლოდ საკუთარი /img/lessons/ საქაღალდიდან და მხოლოდ ცალკე ხაზზე.
function md(src) {
  const fmt = t => t
    .replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g, (m, txt, u) => /&(quot|#39|lt|gt);/.test(u) ? m
      : '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + txt + '</a>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  const inline = t => {
    const parts = t.split('`');
    if (parts.length % 2 === 0) { const last = parts.pop(); parts[parts.length - 1] += '`' + last; }  // დაუხურავი ` ჩვეულებრივი ტექსტია
    return parts.map((p, i) => i % 2 ? '<code>' + p + '</code>' : fmt(p)).join('');
  };
  const IMG = /^!\[([^\]]*)\]\((\/img\/lessons\/[A-Za-z0-9_][\w.-]*\.(?:svg|png|jpe?g|webp))\)$/;
  const cells = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
  let out = '', mode = null, buf = [], code = false;
  const close = () => {
    if (mode === 'ul') out += '</ul>'; else if (mode === 'ol') out += '</ol>';
    else if (mode === 'bq') out += '<aside class="callout">' + buf.map(x => '<p>' + inline(x) + '</p>').join('') + '</aside>';
    else if (mode === 'tb') {
      const rows = buf.filter(r => !/^\|?\s*:?-{2,}/.test(r.trim())).map(cells);
      out += '<div class="scroll"><table><thead><tr>' + rows[0].map(c => '<th>' + inline(c) + '</th>').join('') + '</tr></thead><tbody>' +
        rows.slice(1).map(r => '<tr>' + r.map(c => '<td>' + inline(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>';
    }
    mode = null; buf = [];
  };
  const open = m => { if (mode !== m) { close(); mode = m; if (m === 'ul') out += '<ul>'; if (m === 'ol') out += '<ol>'; } };
  for (const ln of esc(src).split('\n')) {
    if (ln.startsWith('```')) {
      if (code) { out += '<pre><code>' + buf.join('\n') + '</code></pre>'; buf = []; code = false; } else { close(); code = true; }
      continue;
    }
    if (code) { buf.push(ln); continue; }
    if (ln.startsWith('- ')) { open('ul'); out += '<li>' + inline(ln.slice(2)) + '</li>'; continue; }
    if (/^\d+\. /.test(ln)) { open('ol'); out += '<li>' + inline(ln.replace(/^\d+\. /, '')) + '</li>'; continue; }
    if (ln.startsWith('&gt; ')) { open('bq'); buf.push(ln.slice(5)); continue; }
    if (ln.startsWith('|')) { open('tb'); buf.push(ln); continue; }
    close();
    const im = IMG.exec(ln.trim());
    if (im) { out += '<figure class="fig"><img src="' + im[2] + '" alt="' + im[1] + '" loading="lazy">' + (im[1] ? '<figcaption>' + im[1] + '</figcaption>' : '') + '</figure>'; continue; }
    if (ln.startsWith('### ')) out += '<h4>' + inline(ln.slice(4)) + '</h4>';
    else if (ln.startsWith('## ')) out += '<h3>' + inline(ln.slice(3)) + '</h3>';
    else if (ln.trim()) out += '<p>' + inline(ln) + '</p>';
  }
  close();
  return out;
}
// YouTube/Vimeo ბმულების გადაყვანა embed-ად (მენტორს ჩვეულებრივი ბმულის ჩასმაც შეუძლია)
function embed(u) {
  try {
    const x = new URL(u), h = x.hostname.replace(/^www\./, ''), id = /^[\w-]{6,20}$/;
    if (h === 'youtu.be' && id.test(x.pathname.slice(1))) return 'https://www.youtube-nocookie.com/embed/' + x.pathname.slice(1);
    if (['youtube.com', 'm.youtube.com'].includes(h) && x.pathname === '/watch' && id.test(x.searchParams.get('v') || '')) return 'https://www.youtube-nocookie.com/embed/' + x.searchParams.get('v');
    if (['youtube.com', 'youtube-nocookie.com'].includes(h) && /^\/embed\/[\w-]{6,20}$/.test(x.pathname)) return 'https://www.youtube-nocookie.com' + x.pathname;
    if (h === 'vimeo.com' && /^\/\d+$/.test(x.pathname)) return 'https://player.vimeo.com/video' + x.pathname;
    if (h === 'player.vimeo.com' && /^\/video\/\d+/.test(x.pathname)) return u;
  } catch {}
  return null;
}

const plans = () => S.cfg.plans, planOf = id => plans().find(p => p.id === id) || plans()[0] || { name: '', price: 0 };
const level = () => S.user ? S.user.level : 0;
async function load() {
  S.cfg = await api('config');
  const me = await api('me'); S.user = me.user; S.pending = me.pending || null;
  const cs = await api('courses'); S.courses = cs.courses; S.defCid = cs.default;   // კურსების სია სერვერიდანაა (courses.py): ერთი წყარო
  if (!S.courses.some(c => c.id === S.ac)) S.ac = S.defCid;                             // ადმინის პანელში არჩეული კურსი
  try { await loadCourse(S.cid || S.defCid); } catch (e) {
    if (S.cid && S.cid !== S.defCid) { try { await loadCourse(S.defCid); } catch (e2) { applyCourse(S.defCid, {}); } } else applyCourse(S.defCid, {});   // შიგთავსის გარეშე: ცარიელი კურსი, გვერდი მაინც იხსნება
  }
  S.loaded = true;
}
// ერთი კურსის გაკვეთილები და პროგრესი (S.lessons/S.done... ყოველთვის S.cid კურსისაა)
function applyCourse(cid, d) { S.cid = cid; S.stages = d.stages || []; S.lessons = d.lessons || []; S.done = new Set(d.done || []); S.scores = d.scores || {}; S.passed = new Set(d.passed || []); }
async function loadCourse(cid) { applyCourse(cid, await api('lessons?course=' + encodeURIComponent(cid))); }
async function switchCourse(cid) { if (S.cid === cid) return true; try { await loadCourse(cid); return true; } catch (e) { return false; } }
// გაკვეთილის id გლობალურია: თუ მიმდინარე კურსში არ არის, ვეძებთ სხვა გახსნად კურსებში (მოსწავლეს soon კურსი არ ეგზავნება)
async function courseOfLesson(id) {
  if (S.lessons.some(x => x.id == id)) return true;
  for (const c of S.courses) {
    if (c.id === S.cid || !(c.status === 'available' || c.open)) continue;
    try { const d = await api('lessons?course=' + encodeURIComponent(c.id)); if (d.lessons.some(x => x.id == id)) { applyCourse(c.id, d); return true; } } catch (e) { /* სხვა კურსი */ }
  }
  return true;
}
// გაკვეთილის ტექსტი, დავალება, ვიდეო და ქვიზის სტატუსი გახსნისას იტვირთება ცალკე (სია მხოლოდ მეტამონაცემებს შეიცავს)
async function loadLesson(l) {
  const { quiz, ...rest } = await api('lesson/' + l.id);
  Object.assign(l, rest, { qinfo: quiz, loaded: true });
}
const unlocked = () => S.lessons.filter(l => !l.locked);
const pct = () => S.lessons.length ? Math.round(S.done.size / S.lessons.length * 100) : 0;
// ეტაპების დაჯგუფება: [{id, title, description, lessons}]
const stages = () => {
  const m = {}; S.lessons.forEach(l => (m[l.stage] ||= []).push(l));
  return Object.keys(m).map(Number).sort((a, b) => a - b).map(id => {
    const meta = S.stages.find(s => s.id === id) || {}, ls = m[id];
    return { id, title: meta.title || ls[0].summary, description: meta.description || '', lessons: ls, minutes: ls.reduce((n, l) => n + (l.minutes || 0), 0), locked: ls[0].locked, free: ls[0].free };
  });
};
const totalMin = () => S.lessons.reduce((n, l) => n + (l.minutes || 0), 0);
const currentTheme = () => document.documentElement.getAttribute('data-theme');
const lockIco = () => '<svg class="ico" viewBox="0 0 16 16" role="img" aria-label="დაკეტილია"><path fill="currentColor" d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1h-.5V4.5A3.5 3.5 0 0 0 8 1Zm2 5H6V4.5a2 2 0 1 1 4 0V6Z"/></svg>';
const bar = p => `<div class="prog" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${p}"><i data-w="${p}"></i></div>`;

function nav() {
  const h = location.hash || '#/', on = p => h.startsWith('#/' + p) ? 'on' : '';
  const u = S.user;
  const cat = h === '#/' || h === '#' || h === '' || h.startsWith('#/cybersecurity') || h.startsWith('#/c/') || h.startsWith('#/soon') || h.startsWith('#/course') || h.startsWith('#/lesson') ? 'on' : '';
  $('#nav').innerHTML = `<a class="${cat}" href="#/">კურსები</a><a class="${on('pricing')}" href="#/pricing">ფასი</a>` +
    (u ? `<a class="${on('qa')}" href="#/qa">მენტორი</a><a class="${on('account')}" href="#/account">ანგარიში</a>${u.role === 'admin' ? `<a class="${on('admin')}" href="#/admin">ადმინი</a>` : ''}<button id="out">გასვლა</button>`
       : `<a class="${on('login')}" href="#/login">შესვლა</a><a class="cta" href="#/register">რეგისტრაცია</a>`) +
    `<button class="theme" id="th" aria-label="${currentTheme() === 'dark' ? 'ღია თემა' : 'მუქი თემა'}" title="თემის შეცვლა">${currentTheme() === 'dark' ? 'ღია' : 'მუქი'}</button>`;
  const o = $('#out'); if (o) o.onclick = async () => { await api('logout', {}); location.hash = '#/'; await boot(); };
  $('#th').onclick = () => {
    const t = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('cda-theme', t); } catch {}
    nav();
  };
}
function foot() {
  const c = S.cfg.contact;
  $('#foot').innerHTML = `<div class="fb"><p><b>CDA</b> Cyber &amp; Digital Academy</p><p>Learn. Build. Secure.</p></div>
    <div class="fl"><a href="#/">კურსები</a><a href="#/pricing">ფასები</a><a href="#/terms">წესები და პირობები</a><a href="#/privacy">კონფიდენციალურობა</a></div>
    ${c ? `<div class="fc"><p>კონტაქტი</p><p>${esc(c)}</p></div>` : ''}
    <p class="fine">CDA-ს სერტიფიკატი არის კურსის დასრულების დოკუმენტი და არ ცვლის სახელმწიფოს მიერ აღიარებულ კვალიფიკაციას.</p>`;
}

const planCard = (p, cur) => {
  const isCur = S.user && cur === p.id, free = p.id === 'free';
  let btn;
  if (isCur) btn = `<button class="btn ${p.popular ? 'white' : 'line'}" disabled>შენი მიმდინარე გეგმა</button>`;
  else if (free) btn = `<a class="btn line" href="${S.user ? '#/course' : '#/register'}">დაიწყე უფასოდ</a>`;
  else if (!S.user) btn = `<a class="btn ${p.popular ? 'white' : ''}" href="#/register">დარეგისტრირდი</a>`;
  else btn = `<button class="btn ${p.popular ? 'white' : ''}" data-plan="${p.id}">${S.pending === p.id ? 'განაცხადი გაგზავნილია' : 'აირჩიე ' + esc(p.name)}</button>`;
  return `<div class="plan ${p.popular ? 'pop' : ''}">${p.popular ? '<span class="pill">პოპულარული</span>' : ''}<h3>${esc(p.name)}</h3><p class="tg">${esc(p.tagline)}</p>
    <div class="price">${p.price} ₾ <small>${p.price ? '/ თვეში' : ''}</small></div><ul class="ck">${p.features.map(f => `<li>${esc(f)}</li>`).join('')}</ul>${btn}</div>`;
};

// კურსის გვერდი: ეტაპები ბარათებად, თითო ბარათში გაკვეთილების სია
const stageCards = () => `<div class="stgs">${stages().map(st => {
  const d = st.lessons.filter(l => S.done.has(l.id)).length;
  const tag = st.locked ? `${lockIco()} დაკეტილია` : st.free ? 'უფასო' : S.user ? `${d}/${st.lessons.length}` : '';
  return `<article class="sc${st.locked ? ' lk' : ''}"><header><span class="n">${st.id}</span><div><h3>${esc(st.title)}</h3><small>${st.lessons.length} გაკვ. · ${hrs(st.minutes)}${tag ? ` · ${tag}` : ''}</small></div></header>
    <ul>${st.lessons.map(l => `<li><span class="dot ${S.done.has(l.id) ? 'd' : ''}">${S.done.has(l.id) ? '✓' : ''}</span><a href="#/lesson/${l.id}">${esc(l.title)}</a><span class="mi">${l.minutes ? hrs(l.minutes) : ''}</span></li>`).join('')}</ul></article>`;
}).join('')}</div>`;

// კურსების კატალოგი: კურსები მოდის GET /api/courses-იდან (courses.py = ერთადერთი წყარო; იხ. README, "Adding a new course").
const crsHref = c => '#/c/' + encodeURIComponent(c.id);
const courseBase = (cid = S.cid) => cid === S.defCid ? '#/course' : '#/course/' + encodeURIComponent(cid);
const certHref = (cid = S.cid) => cid === S.defCid ? '#/certificate' : '#/certificate/' + encodeURIComponent(cid);
const mailLink = c => c && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c) ? `<a href="mailto:${esc(c)}">${esc(c)}</a>` : esc(c || '');
const soonCourse = id => S.courses.find(c => c.status === 'soon' && c.id === id);
// "აირჩიე კურსი": ყველა ბარათი ნამდვილი <a>, თანაბარი ზომით; ხელმისაწვდომი → c.href, "მალე" → #/soon/<id>
const pickCard = c => {
  const av = c.status === 'available', stats = av ? [[c.stages, 'ეტაპი'], [c.lessons, 'გაკვეთილი'], [hrs(c.minutes), 'მასალა']] : [];
  return `<a class="cc pk${av ? ' av' : ''}" href="${av ? crsHref(c) : '#/soon/' + encodeURIComponent(c.id)}"><span class="soon-tag${av ? ' on' : ''}">${av ? 'ხელმისაწვდომია' : 'მალე'}</span><h3>${esc(c.title)}</h3><p>${esc(c.description)}</p>
    ${av ? `<ul class="cm">${stats.map(([v, n]) => `<li><b>${esc(String(v))}</b><span>${esc(n)}</span></li>`).join('')}<li class="fr"><span>პირველი ეტაპი უფასოა</span></li></ul>` : ''}<span class="go">${av ? 'გახსნა' : 'ნახვა'} →</span></a>`;
};
// უფასო გაკვეთილის გადახედვა: პირველი გაკვეთილი (ეტაპი 1), თუ სტუმარს უფასოდ იხსნება; ველი რომ არ არის, ის ბლოკი არ ჩანს
const previewCard = () => {
  const l = S.lessons[0]; if (!l || !l.free || l.locked) return '';
  const n = S.lessons.filter(x => x.stage === l.stage && (x.pos < l.pos || x === l)).length;
  const im = typeof l.content === 'string' && l.content.match(/!\[([^\]]*)\]\((\/img\/lessons\/[^)\s]+)\)/);
  const obj = Array.isArray(l.objectives) ? l.objectives.filter(x => typeof x === 'string' && x.trim()).slice(0, 3) : [];
  return `<article class="cc big pv" aria-labelledby="pv-t"><p class="pvm">ეტაპი ${l.stage}, გაკვეთილი ${n}${l.minutes ? ` · ${l.minutes} წთ` : ''}</p><h3 id="pv-t">${esc(l.title)}</h3>
    ${im ? `<img class="pvi" src="${esc(im[2])}" alt="${esc(im[1])}" loading="lazy">` : ''}
    ${obj.length ? `<div class="pvo"><h4>რას ისწავლი</h4><ul>${obj.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>` : ''}
    <a class="btn" href="#/lesson/${l.id}">უფასო გაკვეთილის ნახვა</a></article>`;
};

const views = {
  home: () => {
    const pv = previewCard();
    const btns = `<div class="row">${S.user ? '<a class="btn" href="#/course">განაგრძე სწავლა</a>' : '<button type="button" class="btn" id="pick-go">კურსის არჩევა</button>'}<a class="btn line" href="#/pricing">გეგმები და ფასები</a></div>`;
    const nx = unlocked().find(l => !S.done.has(l.id)) || S.lessons[0], q = S.cfg;
    const cont = S.user && nx ? `<section class="sec cat" aria-labelledby="h-cont"><h2 id="h-cont">განაგრძე სწავლა</h2><div class="cc cont"><div class="cp"><div><b>${pct()}%</b><span>${S.done.size} / ${S.lessons.length} გაკვეთილი</span></div>${bar(pct())}</div>
      <div class="cn"><p>${S.done.size ? 'შემდეგი გაკვეთილი' : 'პირველი გაკვეთილი'}: <b>${esc(nx.title)}</b></p><a class="btn" href="#/lesson/${nx.id}">${S.done.size ? 'განაგრძე' : 'დაიწყე'}</a></div></div></section>` : '';
    const gets = [['ქვიზები განმარტებებით', `ყოველი გაკვეთილის ქვიზში გავლის შემდეგ ჩანს სწორი პასუხები და განმარტებები.`],
      ['სავარჯიშოები ბრაუზერში', 'ინტერაქტიული Python სავარჯიშოები იწერება და მოწმდება პირდაპირ გაკვეთილში.'],
      ['კითხვები მენტორს', `კითხვას მენტორს აგზავნი გაკვეთილის გვერდიდან, ${planOf('start').name} გეგმიდან.`],
      ['სერტიფიკატი', 'კურსის დასრულების სერტიფიკატი აკადემიისაა და არა აკრედიტებული დოკუმენტი.']];
    const faq = [['ვისთვისაა კურსი?', 'დამწყებისთვის. წინასწარი გამოცდილება საჭირო არ არის.'],
      ['რა არის უფასო?', 'პირველი ეტაპი სრულად: ტექსტი, ქვიზები და დავალებები. დანარჩენი ეტაპები იხსნება გეგმით. <a href="#/pricing"><u>გეგმები და ფასები</u></a>'],
      ['როგორ მუშაობს ქვიზი?', `გაკვეთილი დასრულებულად ითვლება ${q.quizPassPct ? q.quizPassPct + '%-ზე' : 'გასავლელ ზღვარზე'} და მეტზე. სწორი პასუხები და განმარტებები ჩანს გავლისას${q.quizMaxFails ? ` ან ${q.quizMaxFails} წარუმატებელი მცდელობის შემდეგ` : ''}${q.quizPauseMinutes ? `; ამ შემთხვევაში ${q.quizPauseMinutes} წუთიანი პაუზაა, მერე ახალი მცდელობა შეგიძლია` : ''}.`],
      ['რას ნიშნავს სერტიფიკატი?', 'ეს არის აკადემიის სერტიფიკატი კურსის დასრულების შესახებ და არა აკრედიტებული დოკუმენტი: ის სახელმწიფოს მიერ აღიარებულ კვალიფიკაციას არ ცვლის. გაიცემა Pro ან Mentor გეგმაზე, როცა ყველა გაკვეთილი დასრულებულია და მენტორმა შემაჯამებელი პროექტი დაადასტურა.'],
      ['როგორ ვიღებ პასუხს კითხვაზე?', 'კითხვის გაგზავნა შეგიძლია იმ გეგმებით, რომლებიც ამას მოიცავს; გაკვეთილის გვერდზე არის ღილაკი „კითხვა მენტორს“. გეგმების დეტალები ფასების გვერდზეა. <a href="#/pricing"><u>ფასები</u></a>']];
    return `<section class="chero"><div class="ct"><h1>ისწავლე ციფრული პროფესია ნულიდან</h1>
    <p class="lead">ქართულენოვანი ონლაინ აკადემია: ეტაპობრივი კურსები, ქვიზები, პრაქტიკული დავალებები და მენტორი, რომელიც კითხვებს პასუხობს.</p>${btns}</div>
    ${pv ? `<div class="cr"><h2 class="eyebrow">უფასო გაკვეთილის გადახედვა</h2>${pv}</div>` : ''}</section>
    ${cont}
    <section class="sec cat" id="pick" tabindex="-1" aria-labelledby="h-pick"><h2 id="h-pick">აირჩიე კურსი</h2><div class="cgrid pick">${S.courses.map(pickCard).join('')}</div></section>
    <section class="sec cat" aria-labelledby="h-how"><h2 id="h-how">როგორ ისწავლი</h2>
    <ol class="steps"><li><b>წაიკითხე გაკვეთილი</b></li><li><b>შეასრულე სავარჯიშო</b></li><li><b>ჩააბარე ქვიზი</b></li><li><b>დასვი კითხვა მენტორს</b><p>${esc(planOf('start').name)} გეგმიდან.</p></li></ol></section>
    <section class="sec cat" aria-labelledby="h-get"><h2 id="h-get">რას მიიღებ</h2><div class="cgrid gets">${gets.map(([t, d]) => `<div class="cc"><h3>${esc(t)}</h3><p>${esc(d)}</p></div>`).join('')}</div></section>
    <section class="sec cat" aria-labelledby="h-faq"><h2 id="h-faq">ხშირი შეკითხვები</h2><div class="faq">${faq.map(([t, a]) => `<details><summary>${esc(t)}</summary><p>${a}</p></details>`).join('')}</div></section>`;
  },

  soon: id => {
    const c = soonCourse(decodeURIComponent(id || '')); if (!c) return views.notfound();
    const ct = S.cfg.contact;
    return `<section class="soonp"><span class="soon-tag">მალე</span><h1>${esc(c.title)}</h1><p class="lead">${esc(c.description)}</p><p>ეს კურსი ჯერ მზადდება და მალე გამოქვეყნდება.</p>
    <div class="row"><a class="btn line" href="#/">← ყველა კურსი</a><a class="btn" href="#/cybersecurity">დაიწყე Cybersecurity for Beginners</a>${c.open ? `<a class="btn line" href="${crsHref(c)}">გახსნა (მხოლოდ ადმინისთვის)</a>` : ''}</div>
    ${ct ? `<p class="soonc">კითხვა გაქვს? მომწერე: ${mailLink(ct)}</p>` : ''}</section>`;
  },

  // კურსის გვერდი: Beginners → არსებული მარკეტინგული გვერდი (ასევე #/cybersecurity-ზე), სხვა კურსი → ზოგადი გვერდი ეტაპების სიით
  c: id => {
    const cid = decodeURIComponent(id || '');
    if (!S.courses.some(x => x.id === cid) || S.cid !== cid) return views.notfound();
    return cid === S.defCid ? views.cybersecurity() : views.course();
  },

  cybersecurity: () => {
    const st = stages();
    return `<section class="hero"><div><h1>კიბერუსაფრთხოების სისტემური კურსი დამწყებისთვის</h1>
    <p class="lead">ნულიდან პირველ პროექტამდე: გაკვეთილები, ქვიზები, პრაქტიკული დავალებები უსაფრთხო გარემოში და მენტორი, რომელიც კითხვებს პასუხობს.</p>
    <div class="row"><a class="btn" href="${S.user ? '#/course' : '#/register'}">${S.user ? 'განაგრძე სწავლა' : 'დაიწყე უფასოდ'}</a><a class="btn line" href="#/course">მთელი კურსი</a></div></div>
    <aside class="syl" aria-label="სასწავლო გეგმის მოკლე შინაარსი"><header><b>Cybersecurity: Beginner Path</b><span>${st.length} ეტაპი, ${S.lessons.length} გაკვეთილი, დაახლოებით ${hrs(totalMin())}</span></header>
    <ol>${st.map(s => `<li><a href="#/course"><span class="n">${s.id}</span><span class="t">${esc(s.title)}</span><span class="m">${s.free ? 'უფასო' : s.lessons.length + ' გაკვ.'}</span></a></li>`).join('')}</ol>
    <footer>პირველი ეტაპი უფასოა. დანარჩენი ეტაპები იხსნება გეგმით.</footer></aside></section>
    <ul class="metrics"><li><b>${st.length}</b><span>ეტაპი</span></li><li><b>${S.lessons.length}</b><span>გაკვეთილი</span></li><li><b>${hrs(totalMin())}</b><span>მასალა</span></li><li><b>${S.lessons.length * 4}</b><span>ქვიზის კითხვა</span></li><li><b>${S.lessons.length}</b><span>პრაქტიკული დავალება</span></li></ul>
    <section class="sec"><header><h2>როგორ მიმდინარეობს სწავლა</h2><p>ყოველი გაკვეთილი ერთი და იგივე რიტმით მიდის.</p></header>
    <ol class="steps"><li><b>წაიკითხე და უყურე</b><p>მიზნები, ტექსტი, ვიდეო და PDF კონსპექტი.</p></li><li><b>შეამოწმე</b><p>ქვიზი ყოველი გაკვეთილის შემდეგ, ავტომატური შეფასებით და განმარტებით.</p></li><li><b>გააკეთე</b><p>პრაქტიკული დავალება უსაფრთხო, კანონიერ გარემოში.</p></li><li><b>იკითხე</b><p>მენტორი პასუხობს კითხვებს და აფასებს დავალებებს.</p></li></ol></section>
    <section class="sec"><header><h2>რას შეძლებ კურსის შემდეგ</h2></header><ul class="outc">
      <li>აგიხსნა, როგორ მუშაობს კომპიუტერი, ოპერაციული სისტემა და ქსელი</li><li>იმუშაო Linux-ის ტერმინალში და მართო ფაილების უფლებები</li><li>შეაფასო რისკი და გამართო ფენოვანი დაცვა სახლისა და მცირე ორგანიზაციისთვის</li><li>ამოიცნო ფიშინგი, დაიცვა ანგარიშები პაროლებითა და 2FA-თი</li><li>გაიგო ვებ-აპლიკაციების ძირითადი სისუსტეები და მათგან დაცვის გზები</li><li>დაწერო Python სკრიპტები ლოგების ანალიზისა და ავტომატიზაციისთვის</li><li>გადაამოწმო ინფორმაცია და ეთიკურად იმუშაო ღია წყაროებით</li><li>შექმნა პორტფოლიოში ჩასართავი საბოლოო ნამუშევარი</li></ul></section>
    <section class="sec full"><header><h2>აირჩიე გეგმა</h2><p>დაიწყე უფასოდ. გადახდილ გეგმას ნებისმიერ დროს შეცვლი.</p></header><div class="plans">${plans().map(p => planCard(p, S.user && S.user.plan)).join('')}</div></section>
    <section class="sec"><header><h2>მენტორი</h2></header><div class="mentor"><img src="img/logo.png" alt=""><div><h3>${S.cfg.mentor ? esc(S.cfg.mentor) : 'შენი მენტორი'}</h3><p>კურსი ისე არის აგებული, რომ დამწყებმაც გაიგოს: მარტივი ენა, პრაქტიკული მაგალითები და ყოველთვის კანონიერი, უსაფრთხო ვარჯიში. კითხვებს პირადად ვპასუხობ.</p></div></div></section>
    <section class="sec"><header><h2>ხშირი შეკითხვები</h2></header><div class="faq">
    <details><summary>წინასწარი ცოდნა მჭირდება?</summary><p>არა. კურსი იწყება ნულიდან: კომპიუტერი, ქსელები, შემდეგ უსაფრთხოება.</p></details>
    <details><summary>რამდენი დრო სჭირდება?</summary><p>სწავლა შენს ტემპში მიდის. გაკვეთილები დაახლოებით ${hrs(Math.round(totalMin() / Math.max(1, S.lessons.length)))} გრძელდება, ანუ კვირაში 2-3 გაკვეთილით კურსს რამდენიმე თვეში დაასრულებ.</p></details>
    <details><summary>როგორ ვიხდი ფულს?</summary><p>აირჩევ გეგმას, გაგიგზავნით გადახდის რეკვიზიტებს, გადახდის შემდეგ მენტორი წვდომას ხელით გაგიხსნის (ჩვეულებრივ რამდენიმე საათში).</p></details>
    <details><summary>შემიძლია გეგმის გაუქმება?</summary><p>დიახ. გეგმა 30 დღით აქტიურდება და ავტომატურად არ განახლდება: გაგრძელება შენზეა დამოკიდებული.</p></details>
    <details><summary>არასრულწლოვანს შეუძლია სწავლა?</summary><p>დიახ, მშობლის ან მეურვის თანხმობით. გადახდასა და რეგისტრაციაზე მშობელი უნდა იყოს ინფორმირებული.</p></details>
    <details><summary>ჰაკერობას ვისწავლი?</summary><p>ვსწავლობთ დაცვას და უსაფრთხო პრაქტიკას. სხვის სისტემაზე უნებართვო ქმედება კანონით დასჯადია და კურსში არ მოიაზრება.</p></details>
    <details><summary>რა მოხდება, თუ პაროლი დამავიწყდა?</summary><p>მოწერე მენტორს: ის დროებით პაროლს გამოგიგზავნის, შემდეგ ანგარიშის გვერდზე შეცვლი.</p></details></div></section>
    <section class="sec"><header><h2>მიმართულებები</h2></header><div class="dirs"><div class="dir now"><small>ახლა ხელმისაწვდომია</small><h3>Cybersecurity</h3><p>ქსელები, Linux, უსაფრთხოების პრინციპები.</p></div>
    ${['Programming', 'Web Development', 'Digital Design'].map(x => `<div class="dir soon"><small>მალე</small><h3>${x}</h3><p>კურსი მზადდება.</p></div>`).join('')}</div></section>`;
  },

  course: () => {
    const nx = unlocked().find(l => !S.done.has(l.id)) || S.lessons[0] || {};
    const cert = level() >= 2 && S.done.size === S.lessons.length && S.lessons.length ? `<a class="btn dark" href="${certHref()}">სერტიფიკატი</a>` : '';
    const cc = S.courses.find(x => x.id === S.cid) || {}, dflt = S.cid === S.defCid;
    const side = S.user
      ? `<div class="cp"><div><b>${pct()}%</b><span>${S.done.size} / ${S.lessons.length} გაკვეთილი</span></div>${bar(pct())}<div class="row"><a class="btn sm" href="#/lesson/${nx.id}">${S.done.size ? 'განაგრძე' : 'დაიწყე'}</a>${cert}</div></div>`
      : `<div class="row"><a class="btn" href="#/lesson/${nx.id}">დაიწყე უფასოდ</a><a class="btn line" href="#/register">რეგისტრაცია</a></div>`;
    return `<div class="chead"><div><h1 class="s">${dflt ? 'Cybersecurity: Beginner Path' : esc(cc.title || '')}</h1>${!dflt && cc.description ? `<p>${esc(cc.description)}</p>` : ''}<p class="lead">${stages().length} ეტაპი, ${S.lessons.length} გაკვეთილი, დაახლოებით ${hrs(totalMin())}. პირველი ეტაპი უფასოა.</p>${cc.status === 'soon' ? '<p><span class="badge">მალე (მხოლოდ ადმინისთვის)</span></p>' : ''}</div>${side}</div>
    ${stageCards()}`;
  },

  lesson: id => {
    const l = S.lessons.find(x => x.id == id) || S.lessons[0]; if (!l) return '<p>იტვირთება…</p>';
    const idx = S.lessons.indexOf(l), next = S.lessons[idx + 1], prev = S.lessons[idx - 1];
    const side = stages().map(st => `<details class="sg"${st.id === l.stage ? ' open' : ''}><summary>${st.id}. ${esc(st.title)}</summary>` + st.lessons.map(x => `<a class="li ${x.id === l.id ? 'on' : ''}" href="#/lesson/${x.id}" ${x.id === l.id ? 'aria-current="page"' : ''}><span class="dot ${S.done.has(x.id) ? 'd' : ''}">${S.done.has(x.id) ? '✓' : ''}</span>${esc(x.title)}${x.locked ? lockIco() : ''}</a>`).join('') + '</details>').join('');
    const head = `<div class="lh"><div><a class="crumb" href="${courseBase()}">ეტაპი ${l.stage}. ${esc(l.summary)}</a><h2>${esc(l.title)}</h2>${l.minutes ? `<div class="lmeta">გაკვეთილი ${l.pos} · დაახლოებით ${hrs(l.minutes)}</div>` : ''}</div></div>`;
    let main;
    if (l.locked) main = `${head}<div class="note"><p><b>ეს გაკვეთილი გადახდილი გეგმის მფლობელებისთვისაა.</b></p><p>Start გეგმა (${planOf('start').price} ₾ / თვე) გიხსნის კურსის ყველა გაკვეთილს.</p></div><div class="row"><a class="btn" href="#/pricing">გეგმების ნახვა</a>${S.user ? '' : '<a class="btn line" href="#/register">რეგისტრაცია</a>'}</div>`;
    else {
      const em = l.video_url && embed(l.video_url);
      const player = !l.video_url ? '' : em ? `<div class="player"><iframe src="${esc(em)}" title="${esc(l.title)}" allow="fullscreen" allowfullscreen loading="lazy" referrerpolicy="strict-origin-when-cross-origin"></iframe></div>` : `<div class="player"><video controls preload="metadata" src="${esc(l.video_url)}"></video></div>`;
      const cap = l.video_url && (l.video_title || l.video_channel) ? `<p class="vcap">ვიდეო: ${l.video_title ? '<b>' + esc(l.video_title) + '</b>' : ''}${l.video_title && l.video_channel ? ' · ' : ''}${l.video_channel ? 'არხი: ' + esc(l.video_channel) : ''}</p>` : '';
      const alt = l.video2_url && /^https:\/\//.test(l.video2_url) ? `<p class="vcap">სათადარიგო ვიდეო: <a href="${esc(l.video2_url)}" target="_blank" rel="noopener noreferrer">${esc(l.video2_title || l.video2_url)}</a>${l.video2_channel ? ' · არხი: ' + esc(l.video2_channel) : ''}</p>` : '';
      const sc = S.scores[l.id];
      const goals = l.objectives && l.objectives.length ? `<div class="goals"><h3>მიზნები</h3><ul>${l.objectives.map(o => `<li>${esc(o)}</li>`).join('')}</ul></div>` : '';
      const rail = `${goals}${l.task ? `<div class="task"><h3>პრაქტიკული დავალება</h3><p>${esc(l.task)}</p></div>` : ''}
        ${l.bonus ? `<details class="bonus"><summary>ბონუსი</summary>${md(l.bonus)}</details>` : l.bonus_locked ? `<p class="why">${lockIco()} ბონუს ლაბები Pro გეგმაშია. <a href="#/pricing"><u>გეგმები</u></a></p>` : ''}
        ${level() >= 2 ? `<details><summary>გაუგზავნე დავალება მენტორს</summary><textarea id="tk" rows="5" maxlength="4000" placeholder="ჩაწერე შენი პასუხი ან ჩასვი ბმული" aria-label="დავალების პასუხი"></textarea><div class="row"><button class="btn sm" id="tks">გაგზავნა შესაფასებლად</button></div></details>`
          : S.user ? `<p class="why">დავალების გაგზავნა და შეფასება Pro და Mentor გეგმებშია. <a href="#/pricing"><u>გეგმები</u></a></p>` : ''}`;
      const done = S.done.has(l.id);
      const foot = `<div class="lfoot"><div class="grp">${S.user ? `<button class="btn ${done ? 'line' : ''}" id="dn"${!done && l.quiz_n && !S.passed.has(l.id) ? ' disabled title="ჯერ გაიარე ქვიზი (მინ. 70%)"' : ''}>${done ? '✓ დასრულებულია (მოხსნა)' : l.quiz_n && !S.passed.has(l.id) ? 'დასრულებამდე გაიარე ქვიზი' : 'დავასრულე გაკვეთილი'}</button>` : '<a class="btn" href="#/login">შედი პროგრესის შესანახად</a>'}<a class="btn line" href="#/qa/${l.id}">კითხვა მენტორს</a></div>
        <div class="grp">${prev ? `<a class="btn line" href="#/lesson/${prev.id}">წინა</a>` : ''}${next ? `<a class="btn line" href="#/lesson/${next.id}">შემდეგი</a>` : '<a class="btn line" href="#/course">კურსის გვერდი</a>'}</div></div>`;
      main = `${head}${player}${cap}${alt}<div class="body"><div><div class="prose">${md(l.content)}</div>${exHtml(l)}${l.pdf_url ? `<div class="row"><a class="btn line sm" href="${esc(l.pdf_url)}" target="_blank" rel="noopener noreferrer">PDF კონსპექტი</a></div>` : ''}</div><aside class="rail" aria-label="დავალება და მოქმედებები">${rail}</aside></div>
      ${l.quiz_n ? `<div class="quiz" id="qbox"><h3>ცოდნის შემოწმება${sc ? ` <span class="badge">საუკეთესო: ${sc[0]}/${sc[1]}</span>` : ''}</h3>
        <p class="why">ყოველ მცდელობაზე ბანკიდან ${Math.min(5, l.quiz_n)} შემთხვევითი კითხვა მოგივა. გაკვეთილის დასასრულებლად საჭიროა მინიმუმ 70%.</p>
        <div id="qarea">${!S.user ? '<p class="why">შედი ანგარიშში, რომ ქვიზი გაიარო.</p>' : l.qinfo && l.qinfo.retry_at ? `<div class="note"><p>3 წარუმატებელი მცდელობის შემდეგ პაუზაა. გადაიკითხე გაკვეთილი და წინა მცდელობის განმარტებები; ახალი კითხვებით ${fmtTime(l.qinfo.retry_at)}-ის შემდეგ სცადე.</p></div>` : `<button class="btn sm" id="qstart">${S.passed.has(l.id) ? 'ქვიზის გამეორება' : 'დაიწყე ქვიზი'}</button>`}</div></div>` : ''}
      ${foot}
      ${S.user && S.user.role === 'admin' ? `<div class="adm"><h3>ადმინი: მასალის ბმულები</h3><label for="vu">ვიდეო (https; YouTube/Vimeo ჩვეულებრივი ბმულიც ვარგა)</label><input id="vu" value="${esc(l.video_url)}"><label for="vt">ვიდეოს სათაური (გამოჩნდება ვიდეოს ქვეშ)</label><input id="vt" maxlength="200" value="${esc(l.video_title)}"><label for="vc">არხი</label><input id="vc" maxlength="200" value="${esc(l.video_channel)}"><label for="v2">სათადარიგო ვიდეო (https)</label><input id="v2" value="${esc(l.video2_url)}"><label for="v2t">სათადარიგოს სათაური</label><input id="v2t" maxlength="200" value="${esc(l.video2_title)}"><label for="v2c">სათადარიგოს არხი</label><input id="v2c" maxlength="200" value="${esc(l.video2_channel)}"><label for="pu">PDF (https)</label><input id="pu" value="${esc(l.pdf_url)}"><div class="row"><button class="btn sm dark" id="sv">შენახვა</button></div></div>` : ''}`;
    }
    return `<div class="lay"><aside class="side" aria-label="კურსის სია"><div class="sp"><b>პროგრესი ${pct()}%</b>${bar(pct())}</div>${side}</aside><section>${main}</section></div>`;
  },

  pricing: () => `<h1 class="s">ფასი</h1><p class="lead">აირჩიე შენთვის შესაფერისი გეგმა. თითოეული 30 დღით აქტიურდება და ავტომატურად არ განახლდება. ფასები საცდელია და შეიძლება შეიცვალოს.</p>
    ${S.user ? `<p>შენი გეგმა: <b>${esc(planOf(S.user.plan).name)}</b>${S.user.plan_expires && S.user.plan !== 'free' ? ` (მოქმედებს ${fmtDate(S.user.plan_expires)}-მდე)` : ''}</p>` : ''}
    ${S.pending ? `<div class="note"><p><b>განაცხადი გაგზავნილია: ${esc(planOf(S.pending).name)}.</b></p><p>${S.cfg.payInfo ? esc(S.cfg.payInfo) : 'მენტორი დაგიკავშირდება და გადახდის რეკვიზიტებს გამოგიგზავნის. გადახდის დადასტურების შემდეგ წვდომა გაიხსნება.'}</p></div>` : ''}
    <div class="plans">${plans().map(p => planCard(p, S.user && S.user.plan)).join('')}</div>
    <div class="note"><p>ონლაინ გადახდა ჯერ არ არის ჩართული: წვდომას მენტორი ხელით გაგიხსნის გადახდის შემდეგ. არასრულწლოვნებისთვის საჭიროა მშობლის თანხმობა.</p></div>`,

  auth: reg => { const cv = reg && S.cfg.requireVerify; return `<form class="form" id="af"><h1 class="s">${reg ? 'რეგისტრაცია' : 'შესვლა'}</h1>
    ${reg ? '<label for="n">სახელი</label><input id="n" autocomplete="name" required minlength="2" maxlength="60">' : ''}
    <label for="e">ელფოსტა</label><input id="e" type="email" autocomplete="email" required maxlength="120">
    ${cv ? '<p class="why">ამ მისამართზე გამოგიგზავნით 6-ნიშნა კოდს. კოდის შეყვანისას თავად აირჩევ პაროლს.</p>'
      : `<label for="p">პაროლი${reg ? ` (მინ. ${MINPW()} სიმბოლო, ფრაზაც ვარგა)` : ''}</label><div class="pw"><input id="p" type="password" autocomplete="${reg ? 'new' : 'current'}-password" minlength="${reg ? MINPW() : 1}" maxlength="200" required><button type="button" id="pt" aria-label="პაროლის ჩვენება">ჩვენება</button></div>`}
    ${reg ? '<label class="chk"><input type="checkbox" id="tm" required><span>ვეთანხმები <a href="#/terms"><u>წესებს</u></a> და <a href="#/privacy"><u>კონფიდენციალურობის პოლიტიკას</u></a>. თუ 18 წელს ქვემოთ ვარ, მშობელს/მეურვეს თანხმობა აქვს.</span></label>' : ''}
    <div class="err" id="er" role="alert"></div><button class="btn block">${cv ? 'კოდის მიღება' : reg ? 'შექმენი ანგარიში' : 'შესვლა'}</button>
    <p class="center">${reg ? 'უკვე გაქვს ანგარიში? <a href="#/login"><u>შესვლა</u></a>' : 'ახალი ხარ? <a href="#/register"><u>რეგისტრაცია</u></a>. <br><a href="#/forgot"><u>დაგავიწყდა პაროლი?</u></a>' + (S.cfg.requireVerify ? ' · <a href="#/resend"><u>დადასტურების კოდი არ მივიღე</u></a>' : '')}</p></form>`; },

  qa: lid => !S.user ? views.auth(false) : level() < 1 ? `<h1 class="s">მენტორი</h1><div class="note"><p><b>კითხვების დასმა Start გეგმიდან არის ხელმისაწვდომი.</b></p><p>გეგმის გააქტიურების შემდეგ მენტორი 48 საათში გიპასუხებს (Pro-ზე 24 საათში).</p></div><a class="btn" href="#/pricing">გეგმები</a>` : (() => {
    const l = S.lessons.find(x => x.id == lid);
    return `<h1 class="s">მენტორი</h1><p class="lead">პასუხს ${level() >= 2 ? '24' : '48'} საათში მიიღებ (სამუშაო დღეებში). პირადი მონაცემები არ გამოგვიგზავნო.</p>
    ${l ? `<p><span class="badge">გაკვეთილი: ${esc(l.title)}</span></p>` : ''}
    <div class="qa-box"><textarea id="qt" rows="3" maxlength="800" placeholder="რა გაუგებარია?" aria-label="კითხვა"></textarea><div class="row"><button class="btn" id="qs">გაგზავნა</button></div><div id="ql"></div></div>`; })(),

  account: () => !S.user ? views.auth(false) : `<h1 class="s">ანგარიში</h1><div class="acct">
    <div class="panel"><h2>${esc(S.user.name)}</h2><p>${esc(S.user.email)}</p>
    <p>გეგმა: <b>${esc(planOf(S.user.plan).name)}</b>${S.user.plan_expires && S.user.plan !== 'free' ? `, მოქმედებს ${fmtDate(S.user.plan_expires)}-მდე` : ''}${S.user.role === 'admin' ? ' (ადმინი)' : ''}</p>
    <p>პროგრესი: ${S.done.size}/${S.lessons.length} (${pct()}%)</p>${bar(pct())}
    <div class="row"><a class="btn sm" href="#/pricing">გეგმის შეცვლა</a>${level() >= 2 ? '<a class="btn dark sm" href="#/certificate">სერტიფიკატი</a>' : ''}</div></div>
    <div class="panel"><h2>პაროლის შეცვლა</h2><form class="f" id="pf"><label for="op">ძველი პაროლი</label><input id="op" type="password" autocomplete="current-password" required>
    <label for="np">ახალი პაროლი (მინ. ${MINPW()} სიმბოლო, ფრაზაც ვარგა)</label><input id="np" type="password" autocomplete="new-password" minlength="${MINPW()}" maxlength="200" required><div class="err" id="er" role="alert"></div><button class="btn sm">შეცვლა</button></form></div>
    <div class="panel"><h2>შეტყობინებები</h2><label class="chk"><input type="checkbox" id="nf"${S.user.notify ? ' checked' : ''}><span>ელფოსტით შემატყობინეთ, როცა მენტორი მიპასუხებს ან დავალებას დაადასტურებს</span></label></div>
    <div class="panel"><h2>უსაფრთხოება</h2><p>თუ სხვა მოწყობილობაზე დარჩი შესული, გამოდი ყველგან.</p><div class="row"><button class="btn line sm" id="lo">გასვლა ყველა მოწყობილობიდან</button></div></div>
    ${S.user.role === 'admin' ? '' : `<div class="panel danger"><h2>ანგარიშის წაშლა</h2><p>წაიშლება შენი პროფილი, პროგრესი, ქვიზის შედეგები და კითხვები. ეს ქმედება შეუქცევადია.</p>
    <form class="f" id="df"><label for="dp">პაროლი დასადასტურებლად</label><input id="dp" type="password" autocomplete="current-password" required><div class="err" id="er2" role="alert"></div><button class="btn dark sm">სამუდამოდ წაშლა</button></form></div>`}</div>`,

  forgot: () => `<form class="form" id="ff"><h1 class="s">პაროლის აღდგენა</h1><p class="lead">შეიყვანე ელფოსტა და გამოგიგზავნით 6-ნიშნა კოდს ახალი პაროლის დასაყენებლად.</p>
    <label for="fe">ელფოსტა</label><input id="fe" type="email" autocomplete="email" required maxlength="120">
    <div class="err" id="er" role="alert"></div><button class="btn block">კოდის გაგზავნა</button>
    <p class="center"><a href="#/login"><u>შესვლაზე დაბრუნება</u></a></p></form>`,

  reset: a => { const f = S.flash; S.flash = ''; return `<form class="form" id="rf"><h1 class="s">ახალი პაროლი</h1>
    ${f ? `<div class="note"><p>${esc(f)}</p></div>` : ''}
    <label for="re">ელფოსტა</label><input id="re" type="email" autocomplete="email" required maxlength="120" value="${esc(dec(a))}">
    <label for="rc">6-ნიშნა კოდი ფოსტიდან</label><input id="rc" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required>
    <label for="p">ახალი პაროლი (მინ. ${MINPW()} სიმბოლო, ფრაზაც ვარგა)</label><div class="pw"><input id="p" type="password" autocomplete="new-password" minlength="${MINPW()}" maxlength="200" required><button type="button" id="pt" aria-label="პაროლის ჩვენება">ჩვენება</button></div>
    <div class="err" id="er" role="alert"></div><button class="btn block">პაროლის შეცვლა</button>
    <p class="center"><button type="button" class="btn sm line" id="rn">ახალი კოდი</button></p>
    <p class="center">კოდი ერთჯერადია და ${S.cfg.codeMinutes || 10} წუთში იწურება. 5 არასწორი მცდელობის შემდეგ ახალი კოდი დაგჭირდება.</p></form>`; },

  confirm: a => { const f = S.flash; S.flash = ''; return `<form class="form" id="cf"><h1 class="s">ელფოსტის დადასტურება</h1>
    ${f ? `<div class="note"><p>${esc(f)}</p></div>` : '<p class="lead">შეიყვანე კოდი, რომელიც ელფოსტაზე მოგივიდა, და აირჩიე პაროლი.</p>'}
    <label for="ce">ელფოსტა</label><input id="ce" type="email" autocomplete="email" required maxlength="120" value="${esc(dec(a))}">
    <label for="cc">6-ნიშნა კოდი ფოსტიდან</label><input id="cc" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required>
    <label for="p">შენი პაროლი (მინ. ${MINPW()} სიმბოლო, ფრაზაც ვარგა)</label><div class="pw"><input id="p" type="password" autocomplete="new-password" minlength="${MINPW()}" maxlength="200" required><button type="button" id="pt" aria-label="პაროლის ჩვენება">ჩვენება</button></div>
    <div class="err" id="er" role="alert"></div><button class="btn block">დაადასტურე და შედი</button>
    <p class="center"><button type="button" class="btn sm line" id="rn">ახალი კოდი</button></p>
    <p class="center">კოდი ერთჯერადია და ${S.cfg.codeMinutes || 10} წუთში იწურება. 5 არასწორი მცდელობის შემდეგ ახალი კოდი დაგჭირდება.</p></form>`; },

  resend: () => `<form class="form" id="rsf"><h1 class="s">დადასტურების კოდი</h1><p class="lead">შეიყვანე ელფოსტა და თუ ის დადასტურებას ელოდება, ახალ კოდს გამოგიგზავნით.</p>
    <label for="re">ელფოსტა</label><input id="re" type="email" autocomplete="email" required maxlength="120"><div class="err" id="er" role="alert"></div><button class="btn block">კოდის გაგზავნა</button>
    <p class="center"><a href="#/login"><u>შესვლა</u></a></p></form>`,

  verify: () => `<h1 class="s">სერტიფიკატის გადამოწმება</h1><div id="vc"><p>მოწმდება…</p></div>`,

  certificate: () => `<div id="cert"><p>იტვირთება…</p></div>`,

  admin: () => `<h1 class="s">ადმინისტრატორი</h1><div class="tools" id="acw"></div><div class="tabs" role="tablist" id="tabs"></div><div id="ad"></div>`,

  notfound: () => `<h1 class="s">გვერდი ვერ მოიძებნა</h1><p class="lead">ეს მისამართი არ არსებობს ან გადატანილია.</p><div class="row"><a class="btn" href="#/">მთავარი გვერდი</a><a class="btn line" href="#/course">კურსი</a></div>`,

  terms: () => `<h1 class="s">წესები და პირობები</h1><div class="prose">${md(`## ზოგადი
CDA (Cyber & Digital Academy) არის ონლაინ საგანმანათლებლო სერვისი. რეგისტრაციით ეთანხმები ამ წესებს.

## ანგარიში
- ანგარიში პირადია, მისი გაზიარება დაუშვებელია.
- პაროლის უსაფრთხოებაზე პასუხისმგებელი ხარ.
- არასრულწლოვნის რეგისტრაციისთვის საჭიროა მშობლის ან მეურვის თანხმობა.

## გეგმები და გადახდა
- გეგმა აქტიურდება გადახდის დადასტურების შემდეგ 30 დღით და ავტომატურად არ განახლდება.
- თანხის დაბრუნება განიხილება ინდივიდუალურად, მენტორთან დაკავშირებით.

## მასალის გამოყენება
- კურსის მასალა მხოლოდ პირადი სწავლისთვისაა; ვიდეოების, ტექსტებისა და PDF-ების გავრცელება აკრძალულია.

## ეთიკა
- კურსში ნასწავლი უნარები უნდა გამოიყენო მხოლოდ კანონიერად: საკუთარ სისტემებზე ან წერილობითი ნებართვით.
- სხვის სისტემაზე ან ანგარიშზე უნებართვო წვდომა კანონით დასჯადია.

## სერტიფიკატი
CDA-ს სერტიფიკატი არის კურსის დასრულების დოკუმენტი და არ ცვლის სახელმწიფოს მიერ აღიარებულ კვალიფიკაციას.

## შენიშვნა
ეს ტექსტი საწყისი ნიმუშია. გამოქვეყნებამდე გადაამოწმებინე იურისტს.`)}</div>`,

  privacy: () => `<h1 class="s">კონფიდენციალურობა</h1><div class="prose">${md(`## რას ვინახავთ
- სახელს, ელფოსტას და პაროლის დაშიფრულ ჰეშს (თავად პაროლს არა);
- სწავლის პროგრესს, ქვიზის შედეგებს, შენს კითხვებს და გაგზავნილ დავალებებს;
- გეგმას და მის ვადას;
- უსაფრთხოების მიზნით: ბოლო შესვლის დროს და შესვლის მოვლენებს (დრო და IP მისამართი). ეს ჟურნალი 90 დღეში იშლება; ანგარიშის წაშლისას მასში შენი ელფოსტა და IP ანონიმიზდება.
- გეგმის შეკვეთები (გადახდის ჩანაწერები): ანგარიშის წაშლისას ინახება ანონიმურად (გეგმა, თანხა, თარიღი), სახელისა და ელფოსტის გარეშე. ეს აუცილებელია აღრიცხვისთვის.
- სერტიფიკატი: წაშლისას მფლობელის სახელი იშლება, ნომერი, თარიღი და კურსი რჩება, რომ ნომრის გადამოწმება კვლავ შესაძლებელი იყოს (სახელის გარეშე).

## რისთვის
მხოლოდ სწავლის სერვისის მისაწოდებლად და ანგარიშის დასაცავად: ავტორიზაცია, პროგრესი, მენტორთან კომუნიკაცია.

## ელფოსტა
შენს მისამართზე წერილებს მხოლოდ სერვისისთვის გიგზავნით: ელფოსტის დადასტურება, პაროლის აღდგენა და (ჩართვის შემთხვევაში) შეტყობინება მენტორის პასუხზე. სარეკლამო წერილებს არ ვგზავნით.

## მესამე მხარეები
შრიფტები ჩვენს სერვერზეა და შრიფტებისთვის Google-თან კავშირი არ მყარდება. გაკვეთილზე ვიდეოს გახსნისას ბრაუზერი უკავშირდება ვიდეოს პლატფორმას (YouTube, privacy-enhanced რეჟიმში), რომელიც თავისი წესებით ამუშავებს შენს მოწყობილობის მონაცემებს.

## რას არ ვაკეთებთ
- მონაცემებს მესამე მხარეს არ ვყიდით;
- სარეკლამო თვალთვალს არ ვიყენებთ.

## Cookie
ვიყენებთ ერთ აუცილებელ cookie-ს ავტორიზაციისთვის და ბრაუზერში ვინახავთ შენს თემის არჩევანს (ღია/მუქი).

## შენი უფლებები
ანგარიშის გვერდზე შეგიძლია ანგარიში და მასთან დაკავშირებული მონაცემები თავად წაშალო. მონაცემების ასლის მისაღებად მიმართე მენტორს.

## შენიშვნა
ეს ტექსტი საწყისი ნიმუშია. გამოქვეყნებამდე გადაამოწმებინე იურისტს, განსაკუთრებით არასრულწლოვანთა მონაცემების დამუშავების ნაწილში.`)}</div>`
};

const TITLES = { cybersecurity: 'Cybersecurity for Beginners', soon: 'კურსი მალე', course: 'კურსი', pricing: 'ფასი', login: 'შესვლა', register: 'რეგისტრაცია', qa: 'მენტორი', account: 'ანგარიში', admin: 'ადმინი', certificate: 'სერტიფიკატი', forgot: 'პაროლის აღდგენა', reset: 'ახალი პაროლი', resend: 'დადასტურების კოდი', confirm: 'ელფოსტის დადასტურება', verify: 'სერტიფიკატის გადამოწმება', terms: 'წესები და პირობები', privacy: 'კონფიდენციალურობა' };

async function route() {   // შეცდომის შემთხვევაში ცარიელი გვერდის ნაცვლად ეკრანზე ჩანს, რა მოხდა
  try { await route0(); } catch (x) {
    console.error(x); const app = $('#app');
    if (app) app.innerHTML = `<div class="note" role="alert"><p><b>გვერდის ჩატვირთვა ვერ მოხერხდა.</b> ${esc(x && x.message || String(x))}</p><p><a href="#/">მთავარი გვერდი</a></p></div>`;
  }
}

async function route0() {
  const h = location.hash; nav(); const [p, a] = (location.hash || '#/').slice(2).split('/'); const app = $('#app');
  const adminOnly = p === 'admin' && !(S.user && S.user.role === 'admin');
  let title = TITLES[p] || '';
  if (S.loaded && p !== 'terms' && p !== 'privacy') {   // სწორი კურსის მონაცემები: #/c/<id>, #/course[/<id>], #/lesson/<id>; მთავარი/ანგარიში/ძველი #/cybersecurity = ნაგულისხმევი კურსი
    let okc = true;
    if (p === 'c') okc = !!a && await switchCourse(decodeURIComponent(a));
    else if (p === 'course') okc = await switchCourse(a ? decodeURIComponent(a) : S.defCid);
    else if (p === 'lesson') await courseOfLesson(a);
    else if (['', 'cybersecurity', 'account'].includes(p)) await switchCourse(S.defCid);
    if (location.hash !== h) return;
    if (!okc) { app.innerHTML = views.notfound(); document.title = 'გვერდი ვერ მოიძებნა — CDA'; foot(); return; }
  }
  if (!p && S.loaded && S.lessons[0] && S.lessons[0].free && !S.lessons[0].locked && !S.lessons[0].loaded) {   // უფასო გაკვეთილის გადახედვისთვის
    try { await loadLesson(S.lessons[0]); } catch (x) { /* გადახედვა უბრალოდ არ გამოჩნდება */ }
    if (location.hash !== h) return;
  }
  if (!S.loaded && p !== 'terms' && p !== 'privacy') app.innerHTML = '<p>იტვირთება…</p>';
  else if (p === 'lesson') {
    const l = S.lessons.find(x => x.id == a) || S.lessons[0];
    if (l && !l.locked && !l.loaded) {
      app.innerHTML = '<p>იტვირთება…</p>';
      try { await loadLesson(l); } catch (x) { toast(x.message); }
      if (location.hash !== h) return;  // სანამ იტვირთებოდა, სხვა გვერდზე გადავიდა
    }
    app.innerHTML = views.lesson(a); if (l) title = l.title;
  }
  else if (p === 'login' || p === 'register') app.innerHTML = S.user ? views.account() : views.auth(p === 'register');
  else if (adminOnly) app.innerHTML = '<p>მხოლოდ ადმინისთვის.</p>';
  else if (p && !views[p]) { app.innerHTML = views.notfound(); title = 'გვერდი ვერ მოიძებნა'; }
  else if (p === 'soon') { const c = soonCourse(decodeURIComponent(a || '')); app.innerHTML = views.soon(a); title = c ? c.title + ' — მალე' : 'გვერდი ვერ მოიძებნა'; }
  else app.innerHTML = views[p || 'home'](a);
  if (S.user && S.user.verified === false && p !== 'confirm' && p !== 'reset') app.insertAdjacentHTML('afterbegin', `<div class="note" id="vn"><p><b>დაადასტურე ელფოსტა.</b> მისამართზე ${esc(S.user.email)} გამოგიგზავნით 6-ნიშნა კოდს. დადასტურებამდე კითხვის დასმა და გეგმის განაცხადი დაკეტილია.</p><div class="row"><button class="btn sm line" id="rv">კოდის გამოგზავნა</button></div></div>`);
  if (p === 'c' || p === 'course') { const cc = S.courses.find(x => x.id === S.cid); if (cc) title = cc.title; }
  document.title = (title ? title + ' — ' : '') + 'CDA';
  fillBars();
  foot(); scrollTo(0, 0); app.focus({ preventScroll: true }); bind(p, a);
  if (p === 'lesson') initExercises(a);
}
// ---------- ინტერაქტიული კოდის სავარჯიშოები (რედაქტორი: public/sandbox/, ცალკე იზოლირებულ iframe-ში; იხსნება მხოლოდ ღილაკით)
function exHtml(l) {
  const xs = l.exercises || []; if (!xs.length) return '';
  return `<section class="exs" aria-label="კოდის სავარჯიშოები"><h3>${xs.length > 1 ? 'კოდის სავარჯიშოები' : 'კოდის სავარჯიშო'}</h3>` + xs.map((x, i) => `<div class="ex" data-i="${i}"><h4>${esc(x.title)}</h4><div class="prose">${md(x.instructions)}</div>
    <p class="why">${x.type === 'python' ? 'Python შენს ბრაუზერში სრულდება, სერვერზე არაფერი იგზავნება. input() კლავიატურიდან არ იკითხება: მნიშვნელობებს სავარჯიშო თავად აძლევს.' : 'HTML-ის ნახვა იზოლირებულ ფანჯარაშია: გარე ფაილები და ქსელი ჩართული არ არის.'}</p>
    <div class="exbox"><button class="btn sm" data-open>სავარჯიშოს გახსნა</button></div>
    <div class="row"><button class="btn line sm" data-hint>მინიშნება</button><button class="btn line sm" data-sol>ამოხსნის ჩვენება</button></div>
    <p class="exhint" hidden></p><pre class="exsol" hidden></pre></div>`).join('') + '</section>';
}
const lsGet = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
const lsSet = (k, v) => { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* კერძო რეჟიმი ან სავსე საცავი */ } };
const exFrames = new Map();   // iframe-ის window → { x, key }
function themeNow() { return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'; }
// შეტყობინებებს ვიღებთ მხოლოდ ჩვენ მიერ შექმნილი iframe-ებისგან (event.source-ით); sandbox-ის წარმოშობა "null"-ია, ამიტომ origin-ს ვერ ვამოწმებთ
addEventListener('message', ev => {
  const r = exFrames.get(ev.source), m = ev.data;
  if (!r || !m || typeof m !== 'object') return;
  if (m.t === 'ready') ev.source.postMessage({ t: 'init', ex: { id: r.x.id, type: r.x.type, starter: r.x.starter, stdin: r.x.stdin || [], checks: r.x.checks }, code: lsGet(r.key) ?? r.x.starter, theme: themeNow() }, '*');
  else if (m.t === 'height' && Number.isFinite(m.h)) r.frame.style.height = Math.min(1400, Math.max(320, m.h + 4)) + 'px';
  else if (m.t === 'code' && typeof m.code === 'string' && m.code.length <= 20000) lsSet(r.key, m.code === r.x.starter ? null : m.code);
});
new MutationObserver(() => { for (const [w, r] of exFrames) { if (w.closed) exFrames.delete(w); else w.postMessage({ t: 'theme', theme: themeNow() }, '*'); } })
  .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
function initExercises(a) {
  const l = S.lessons.find(x => x.id == a) || S.lessons[0]; if (!l || !l.exercises || !l.exercises.length) return;
  for (const w of exFrames.keys()) if (w.closed) exFrames.delete(w);
  $$('.exs .ex').forEach(box => {
    const x = l.exercises[+box.dataset.i], q = s => box.querySelector(s), hint = q('.exhint'), sol = q('.exsol'), sb = q('[data-sol]');
    q('[data-open]').onclick = () => {
      const f = document.createElement('iframe');
      f.className = 'exframe'; f.title = 'კოდის რედაქტორი: ' + x.title; f.setAttribute('sandbox', 'allow-scripts'); f.referrerPolicy = 'no-referrer';
      q('.exbox').replaceChildren(f);
      exFrames.set(f.contentWindow, { x, key: `cda-ex:${l.id}:${x.id}`, frame: f });
      f.src = '/sandbox/editor.html';
    };
    q('[data-hint]').onclick = () => { hint.hidden = !hint.hidden; hint.textContent = x.hint ? 'მინიშნება: ' + x.hint : 'ამ სავარჯიშოს მინიშნება არ აქვს.'; };
    sb.onclick = async () => {
      if (!sol.hidden) { sol.hidden = true; sb.textContent = 'ამოხსნის ჩვენება'; return; }
      try { const d = await api(`lesson/${l.id}/exercise/${encodeURIComponent(x.id)}/solution`); sol.textContent = d.solution; sol.hidden = false; sb.textContent = 'ამოხსნის დამალვა'; } catch (e) { toast(e.message); }
    };
  });
}

// სიგანე/სიმაღლე JS-ით (CSP-ის გამო inline style არ გვაქვს)
function fillBars() {
  $$('[data-w]').forEach(e => { e.style.width = e.dataset.w + '%'; });
  $$('[data-h]').forEach(e => { e.style.height = e.dataset.h + '%'; });
}

// ვიდეოს ველები ადმინისთვის: თუ ბმული შეიცვალა, მაგრამ სათაური/არხი ძველივე დარჩა, ისინი გასუფთავდება (სხვა ვიდეოს არ უნდა მიეწეროს)
function videoPayload(f, orig) {
  const t = x => x.trim();
  const same = (u, ou, a, oa) => t(u) === (ou || '') ? t(a) : (t(a) === (oa || '') ? '' : t(a));
  return { video_url: t(f.v), video_title: same(f.v, orig.video_url, f.t, orig.video_title), video_channel: same(f.v, orig.video_url, f.c, orig.video_channel),
           video2_url: t(f.v2), video2_title: same(f.v2, orig.video2_url, f.t2, orig.video2_title), video2_channel: same(f.v2, orig.video2_url, f.c2, orig.video2_channel) };
}

async function startQuiz(l) {
  const area = $('#qarea');
  let r;
  try { r = await api('quiz/start', { lesson_id: l.id }); } catch (x) { toast(x.message); return; }
  area.innerHTML = `<form id="qz"><div class="qs2">${r.questions.map((x, i) => `<fieldset class="qq"><legend>${i + 1}. ${esc(x.q)}</legend>${x.o.map((o, j) => `<label class="opt"><input type="radio" name="q${i}" value="${j}" required>${esc(o)}</label>`).join('')}<div class="why" id="w${i}"></div></fieldset>`).join('')}</div>
    <button class="btn sm" id="qb">შემოწმება</button> <span id="qr" role="status"></span></form>`;
  const qz = $('#qz');
  qz.onsubmit = async e => {
    e.preventDefault();
    const answers = r.questions.map((_, i) => +(qz.querySelector(`input[name=q${i}]:checked`) || {}).value);
    try {
      const res = await api('quiz', { attempt_id: r.attempt_id, answers });
      qz.querySelectorAll('input').forEach(i => { i.disabled = true; });
      res.results.forEach((rs, i) => {
        const labs = qz.querySelectorAll(`input[name=q${i}]`);
        labs.forEach(inp => { const lab = inp.closest('.opt'); lab.classList.remove('ok', 'bad'); if (res.reveal) { if (+inp.value === rs.correct) lab.classList.add('ok'); else if (inp.checked) lab.classList.add('bad'); } });
        $('#w' + i).textContent = res.reveal ? (rs.ok ? '✓ ' : '✗ ') + (rs.e || '') : (rs.ok ? '✓ სწორია' : '✗ არასწორია');
      });
      $('#qb').remove();
      const best = S.scores[l.id];
      if (!best || res.score * best[1] > best[0] * res.total) S.scores[l.id] = [res.score, res.total];
      l.qinfo = { ...(l.qinfo || {}), retry_at: res.retry_at };
      let msg = `შედეგი: ${res.score}/${res.total}. `;
      if (res.passed) {
        S.passed.add(l.id); msg += 'ქვიზი გავლილია! ახლა გაკვეთილის დასრულება შეგიძლია.';
        const dn = $('#dn'); if (dn && !S.done.has(l.id)) { dn.disabled = false; dn.removeAttribute('title'); dn.textContent = 'დავასრულე გაკვეთილი'; }
      } else if (res.retry_at) msg += `საჭიროა ${res.pass_pct}%. ზემოთ ჩანს სწორი პასუხები და განმარტებები. ახლა ${res.pause_minutes} წუთი პაუზაა: გადაიკითხე გაკვეთილის შესაბამისი ნაწილები, ახალი კითხვებით ${fmtTime(res.retry_at)}-ის შემდეგ სცადე.`;
      else msg += `საჭიროა ${res.pass_pct}%. გადაიკითხე გაკვეთილი და სცადე ახალი კითხვებით (პაუზამდე დაგრჩა ${res.tries_before_pause} მცდელობა).`;
      $('#qr').textContent = msg;
      if (!res.retry_at) { const b = document.createElement('button'); b.className = 'btn sm line'; b.textContent = res.passed ? 'ქვიზის გამეორება' : 'ახალი მცდელობა'; b.onclick = () => startQuiz(l); qz.append(' ', b); }
      toast(`ქვიზი: ${res.score}/${res.total}`);
    } catch (x) { toast(x.message); }
  };
}

function bind(p, a) {
  const sent = (r, email, to) => { S.until = Date.now() + (r.resend_in || S.cfg.resendSeconds || 60) * 1000; S.flash = r.message || ''; location.hash = to + encodeURIComponent(email); };
  const cooldown = (btn, sec) => {
    if (!btn) return; const label = btn.dataset.l || btn.textContent; btn.dataset.l = label; let left = Math.max(0, Math.ceil(sec));
    const tick = () => { if (!document.body.contains(btn)) return; if (left <= 0) { btn.disabled = false; btn.textContent = label; return; } btn.disabled = true; btn.textContent = `${label} (${left} წმ)`; left--; setTimeout(tick, 1000); };
    tick();
  };
  const pg = $('#pick-go');
  if (pg) pg.onclick = () => {
    const t = $('#pick'); if (!t) return;
    t.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
    t.focus({ preventScroll: true });
  };
  const pt = $('#pt');
  if (pt) pt.onclick = () => { const i = $('#p'), show = i.type === 'password'; i.type = show ? 'text' : 'password'; pt.textContent = show ? 'დამალვა' : 'ჩვენება'; };
  // „ახალი კოდი“ ღილაკი დადასტურების და აღდგენის გვერდზე (სერვერი ხელახალ გაგზავნას 60 წამამდე და საათში 5-მდე ზღუდავს)
  const rn = $('#rn');
  if (rn) {
    const emailEl = $('#ce') || $('#re'), kind = $('#cf') ? 'verify/resend' : 'password/forgot';
    cooldown(rn, (S.until - Date.now()) / 1000);
    rn.onclick = async () => {
      try { const r = await api(kind, { email: emailEl.value.trim() }); $('#er').textContent = ''; cooldown(rn, r.resend_in || 60); S.until = Date.now() + (r.resend_in || 60) * 1000; toast('თუ ანგარიში არსებობს, ახალი კოდი გამოგიგზავნეთ'); }
      catch (x) { $('#er').textContent = x.message; if (x.retry) cooldown(rn, Math.min(x.retry, 3600)); }
    };
  }
  const rv = $('#rv');
  if (rv) rv.onclick = async () => { try { sent(await api('verify/resend', { email: S.user.email }), S.user.email, '#/confirm/'); } catch (x) { toast(x.message); } };
  const rsf = $('#rsf');
  if (rsf) rsf.onsubmit = async e => { e.preventDefault(); const em = $('#re').value.trim(); try { sent(await api('verify/resend', { email: em }), em, '#/confirm/'); } catch (x) { $('#er').textContent = x.message; } };
  const ff = $('#ff');
  if (ff) ff.onsubmit = async e => { e.preventDefault(); const em = $('#fe').value.trim(); try { sent(await api('password/forgot', { email: em }), em, '#/reset/'); } catch (x) { $('#er').textContent = x.message; } };
  const rf = $('#rf');
  if (rf) rf.onsubmit = async e => { e.preventDefault(); try { await api('password/reset', { email: $('#re').value.trim(), code: $('#rc').value.trim(), password: $('#p').value }); toast('პაროლი შეიცვალა. ახლა შედი ახალი პაროლით.'); location.hash = '#/login'; } catch (x) { $('#er').textContent = x.message; } };
  const cf = $('#cf');
  if (cf) cf.onsubmit = async e => { e.preventDefault(); try { await api('verify', { email: $('#ce').value.trim(), code: $('#cc').value.trim(), password: $('#p').value }); await boot('#/course'); toast('ელფოსტა დადასტურებულია, შენ შესული ხარ'); } catch (x) { $('#er').textContent = x.message; } };
  if (p === 'verify') api('cert/' + encodeURIComponent(a || '-')).then(c => { $('#vc').innerHTML = `<div class="note"><p><b>✓ დადასტურებული სერტიფიკატი.</b></p>${c.name ? `<p>სახელი: <b>${esc(c.name)}</b></p>` : '<p>მფლობელის სახელი ამ ჩანაწერიდან ამოღებულია (ანგარიში წაშლილია), სერტიფიკატი კი დადასტურებულია.</p>'}<p>კურსი: ${esc(c.course)}</p><p>გაცემის თარიღი: ${fmtDate(c.date)}</p></div>`; })
    .catch(x => { $('#vc').innerHTML = `<div class="note"><p><b>სერტიფიკატი ვერ მოიძებნა.</b></p><p>${esc(x.message)} შეამოწმე ნომერი.</p></div>`; });
  const af = $('#af');
  if (af) {
    af.onsubmit = async e => { e.preventDefault(); try {
      if (p === 'register' && S.cfg.requireVerify) { const em = $('#e').value.trim(); sent(await api('register', { name: $('#n').value, email: em, terms: $('#tm').checked }), em, '#/confirm/'); return; }
      await api(p === 'register' ? 'register' : 'login', { name: $('#n')?.value, email: $('#e').value, password: $('#p').value, terms: $('#tm') ? $('#tm').checked : undefined });
      await boot('#/course'); } catch (x) { $('#er').textContent = x.message; } };
  }
  $$('[data-plan]').forEach(b => b.onclick = async () => { try { await api('orders', { plan: b.dataset.plan }); S.pending = b.dataset.plan; toast('განაცხადი გაიგზავნა'); location.hash = '#/pricing'; route(); } catch (x) { toast(x.message); } });
  const cur = () => S.lessons.find(x => x.id == a) || S.lessons[0];
  const dn = $('#dn');
  if (dn) dn.onclick = async () => { const l = cur();
    try { const d = !S.done.has(l.id); await api('progress', { lesson_id: l.id, done: d }); d ? S.done.add(l.id) : S.done.delete(l.id); route(); toast(d ? 'გაკვეთილი დასრულებულია' : 'მონიშვნა მოიხსნა'); } catch (x) { toast(x.message); } };
  const sv = $('#sv');
  if (sv) sv.onclick = async () => { const l = cur(); try { await api('admin/lesson', { id: l.id, ...videoPayload({ v: $('#vu').value, t: $('#vt').value, c: $('#vc').value, v2: $('#v2').value, t2: $('#v2t').value, c2: $('#v2c').value }, l), pdf_url: $('#pu').value.trim() }); await load(); toast('შენახულია'); route(); } catch (x) { toast(x.message); } };
  const qs = $('#qstart');
  if (qs) qs.onclick = () => startQuiz(cur());
  const tks = $('#tks');
  if (tks) tks.onclick = async () => { const t = $('#tk').value.trim(); if (!t) return; try { await api('questions', { text: t, kind: 'task', lesson_id: cur().id }); toast('დავალება გაიგზავნა'); location.hash = '#/qa'; } catch (x) { toast(x.message); } };
  if (p === 'qa' && S.user && level() >= 1) { loadQ($('#ql')); $('#qs').onclick = async () => { const t = $('#qt').value.trim(); if (!t) return; try { await api('questions', { text: t, lesson_id: +a || undefined }); $('#qt').value = ''; toast('კითხვა გაიგზავნა'); loadQ($('#ql')); } catch (x) { toast(x.message); } }; }
  const pf = $('#pf');
  if (pf) pf.onsubmit = async e => { e.preventDefault(); try { await api('password', { old: $('#op').value, next: $('#np').value }); pf.reset(); $('#er').textContent = ''; toast('პაროლი შეიცვალა'); } catch (x) { $('#er').textContent = x.message; } };
  const nf = $('#nf');
  if (nf) nf.onchange = async () => { try { await api('notify', { on: nf.checked }); S.user.notify = nf.checked ? 1 : 0; toast('შენახულია'); } catch (x) { toast(x.message); nf.checked = !nf.checked; } };
  const lo = $('#lo');
  if (lo) lo.onclick = async () => { try { await api('logout_all', {}); toast('გახვედი ყველა მოწყობილობიდან'); location.hash = '#/login'; await boot(); } catch (x) { toast(x.message); } };
  const df = $('#df');
  if (df) df.onsubmit = async e => { e.preventDefault(); if (!confirm('ანგარიში და მისი მონაცემები სამუდამოდ წაიშლება. გაგრძელება?')) return;
    try { await api('account/delete', { password: $('#dp').value }); toast('ანგარიში წაიშალა'); location.hash = '#/'; await boot(); } catch (x) { $('#er2').textContent = x.message; } };
  if (p === 'certificate') loadCert(a ? decodeURIComponent(a) : '');
  if (p === 'admin' && S.user?.role === 'admin') loadAdmin();
}

async function loadCert(cid = '') {
  const box = $('#cert'), cq = cid ? '?course=' + encodeURIComponent(cid) : '';
  try {
    const st = await api('certificate/status' + cq);
    if (!st.plan_ok) { box.innerHTML = '<h1 class="s">სერტიფიკატი</h1><div class="note"><p>სერტიფიკატი Pro და Mentor გეგმებშია.</p></div><a class="btn" href="#/pricing">გეგმები</a>'; return; }
    if (!st.eligible && !st.issued) {
      const mark = ok => ok ? '✓' : '○';
      box.innerHTML = `<h1 class="s">სერტიფიკატი</h1><p class="lead">${st.capstone === 'not_required' ? 'სერტიფიკატის მისაღებად დაასრულე ყველა გაკვეთილი:' : 'სერტიფიკატის მისაღებად ორი რამ არის საჭირო:'}</p>
        <ul class="chk-list"><li>${mark(st.done >= st.total)} ყველა გაკვეთილი დასრულებული: <b>${st.done}/${st.total}</b></li>
        ${st.capstone === 'not_required' ? '' : `<li>${mark(st.capstone === 'approved')} შემაჯამებელი პროექტი მენტორის მიერ დადასტურებული${st.capstone === 'pending' ? ' <span class="badge">განხილვაშია</span>' : ''}</li>`}</ul>
        ${st.capstone === 'none' ? `<div class="panel"><h2>შემაჯამებელი პროექტი</h2><p>აღწერე შენი პროექტი ან ჩასვი ბმული. მენტორი განიხილავს და დაადასტურებს.</p><textarea id="cp" rows="6" maxlength="4000" aria-label="შემაჯამებელი პროექტი"></textarea><div class="err" id="er" role="alert"></div><div class="row"><button class="btn" id="cps">გაგზავნა</button></div></div>` : ''}
        ${st.capstone === 'pending' ? '<div class="note"><p>პროექტი გაგზავნილია. მენტორის დადასტურების შემდეგ სერტიფიკატი აქ გამოჩნდება; დადასტურებისას ელფოსტაზეც შეგატყობინებთ.</p></div>' : ''}`;
      const cps = $('#cps');
      if (cps) cps.onclick = async () => { const t = $('#cp').value.trim(); if (!t) { $('#er').textContent = 'ჩაწერე პროექტის აღწერა.'; return; }
        try { await api('questions', { text: t, kind: 'capstone' }); toast('პროექტი გაიგზავნა'); loadCert(cid); } catch (x) { $('#er').textContent = x.message; } };
      return;
    }
    const c = await api('certificate' + cq), url = location.origin + '/#/verify/' + c.id;
    box.innerHTML = `<div class="cert"><div class="in2"><img src="img/logo.png" alt="" width="56"><p><b>CDA — Cyber &amp; Digital Academy</b></p><h1>სერტიფიკატი</h1><p>კურსის წარმატებით დასრულების დამადასტურებელი დოკუმენტი</p><p>ამით ადასტურებს, რომ</p><div class="nm">${esc(c.name)}</div><p>წარმატებით დაასრულა სასწავლო პროგრამა</p><p><b>${esc(c.course)}</b></p><p>${c.stages} ეტაპი, ${c.lessons} გაკვეთილი, დაახლოებით ${hrs(c.minutes)}, შემაჯამებელი პროექტი</p><div class="sg"><span>თარიღი: ${fmtDate(c.date)}</span><span>ნომერი: ${esc(c.id)}</span></div><p class="vurl">გადამოწმება: ${esc(url)}</p></div></div>
    <div class="row noprint"><button class="btn" id="pr">ბეჭდვა / PDF-ად შენახვა</button></div>`;
    $('#pr').onclick = () => print();
  } catch (x) { box.innerHTML = `<h1 class="s">სერტიფიკატი</h1><div class="note"><p>${esc(x.message)}</p></div><a class="btn" href="#/pricing">გეგმები</a>`; }
}

// კითხვები: მოსწავლისთვის საკუთარი, ადმინისთვის ყველა (ფილტრით)
async function loadQ(box, course = '') {
  if (!box) return;
  const { questions } = await api('questions' + (course && S.user.role === 'admin' ? '?course=' + encodeURIComponent(course) : '')), admin = S.user.role === 'admin';
  const list = admin ? questions.filter(q => S.qf === 'all' || (S.qf === 'task' ? q.kind !== 'question' : !q.answer)) : questions;
  const html = list.length ? list.map(q => `<div class="q"><small>${admin ? esc(q.name) + ', ' : ''}${fmtDate(q.created)}</small>${q.kind === 'task' ? '<span class="badge t">დავალება</span>' : q.kind === 'capstone' ? '<span class="badge t">შემაჯამებელი პროექტი</span>' : ''}${q.status === 'approved' ? '<span class="badge">✓ დადასტურებული</span>' : ''}${admin && q.plan !== 'free' ? `<span class="badge">${esc(planOf(q.plan).name)}</span>` : ''}${q.lesson_title ? `<span class="badge">${esc(q.lesson_title)}</span>` : ''}<p>${esc(q.text)}</p>
    ${admin && q.kind !== 'question' ? `<div class="row"><button class="btn sm ${q.status === 'approved' ? 'line' : ''}" data-ap="${q.id}" data-st="${q.status === 'approved' ? '' : 'approved'}">${q.status === 'approved' ? 'დადასტურების მოხსნა' : 'დადასტურება'}</button></div>` : ''}
    ${q.answer ? `<div class="a"><b>მენტორი:</b> ${esc(q.answer)}</div>${admin ? `<details><summary>პასუხის შეცვლა</summary><textarea id="a${q.id}" rows="2" aria-label="პასუხი">${esc(q.answer)}</textarea><div class="row"><button class="btn sm" data-id="${q.id}">შენახვა</button></div></details>` : ''}`
      : admin ? `<div class="row"><textarea id="a${q.id}" rows="2" placeholder="პასუხი" aria-label="პასუხი"></textarea><button class="btn sm" data-id="${q.id}">პასუხი</button></div>` : '<small>პასუხი მალე იქნება</small>'}</div>`).join('') : `<p>${admin ? 'ამ ფილტრით არაფერია.' : 'ჯერ არაფერია. დასვი პირველი კითხვა.'}</p>`;
  box.innerHTML = html;
  $$('[data-ap]').forEach(b => b.onclick = async () => { try { await api('admin/task_status', { id: +b.dataset.ap, status: b.dataset.st }); toast('შენახულია'); loadAdmin(); } catch (x) { toast(x.message); } });
  $$('[data-id]').forEach(b => b.onclick = async () => { try { await api('admin/answer', { id: +b.dataset.id, answer: $('#a' + b.dataset.id).value }); toast('შენახულია'); loadAdmin(); } catch (x) { toast(x.message); } });
}

// ---------------------------------------------------------------- ადმინისტრატორი
const ACT = { login: 'შესვლა', login_fail: 'წარუმატებელი შესვლა', register: 'რეგისტრაცია', password_change: 'პაროლის შეცვლა', logout_all: 'გასვლა ყველგან', account_delete: 'ანგარიშის წაშლა',
  admin_plan: 'გეგმის შეცვლა', admin_order_approve: 'განაცხადის დადასტურება', admin_order_reject: 'განაცხადის უარყოფა', admin_resetpw: 'პაროლის გადაყენება', admin_user_delete: 'მომხმარებლის წაშლა',
  admin_answer: 'პასუხი', admin_task_approve: 'დავალების დადასტურება', admin_task_unapprove: 'დადასტურების მოხსნა', certificate_issued: 'სერტიფიკატის გაცემა', admin_lesson: 'მასალის ბმული', admin_export: 'CSV ექსპორტი', admin_backup: 'ბაზის ასლი', make_admin: 'ადმინის დანიშვნა', email_verified: 'ელფოსტის დადასტურება', password_reset: 'პაროლის აღდგენა', code_locked: 'კოდი დაიბლოკა (5 არასწორი მცდელობა)', login_unverified: 'შესვლა დაუდასტურებელით' };
const ADMIN_TABS = [['overview', 'მიმოხილვა'], ['orders', 'განაცხადები'], ['users', 'მოსწავლეები'], ['qs', 'კითხვები და დავალებები'], ['lessons', 'მასალები'], ['audit', 'ჟურნალი']];
const confirmMsg = 'ნამდვილად გინდა?';

async function loadAdmin() {
  const box = $('#ad'); if (!box) return;
  const cstat = c => !c.has_content ? 'მალე (შიგთავსი არ არის)' : c.status === 'soon' ? 'მალე (შიგთავსით, მხოლოდ ადმინისთვის)' : 'ხელმისაწვდომია';   // კურსის არჩევის სია ყოველთვის ჩანს: ყველა კურსი courses.py-იდან
  $('#acw').innerHTML = `<div><label for="acs">კურსი</label><select id="acs">${S.courses.map(c => `<option value="${esc(c.id)}" ${c.id === S.ac ? 'selected' : ''}>${esc(c.title)} — ${cstat(c)}</option>`).join('')}</select></div>`;
  $('#acs').onchange = e => { S.ac = e.target.value; S.au.page = 0; loadAdmin(); };
  const cur = S.courses.find(c => c.id === S.ac);
  if (cur && !cur.has_content) {   // შიგთავსის გარეშე კურსი: ცარიელი ცხრილების ნაცვლად ახსნა
    $('#tabs').innerHTML = '';
    box.innerHTML = `<div class="note"><p><b>${esc(cur.title)}</b>: ამ კურსს ჯერ შიგთავსი არ აქვს, ამიტომ აქ ჩვენი მონაცემები ჯერ არ არის (მოსწავლეები, ქვიზები, მასალები). კურსის შიგთავსის ფაილის შესაქმნელად გამოიყენე <code>tools/new_course.py</code>.</p></div>`;
    return;
  }
  const ac = encodeURIComponent(S.ac);
  let s; try { s = await api('admin/stats?course=' + ac); } catch (x) { box.innerHTML = `<div class="note" role="alert"><p><b>ადმინის მონაცემების ჩატვირთვა ვერ მოხერხდა.</b> ${esc(x.message)}</p></div>`; return; }
  $('#tabs').innerHTML = ADMIN_TABS.map(([k, n]) => `<button role="tab" class="${S.tab === k ? 'on' : ''}" data-tab="${k}">${n}${k === 'orders' && s.orders ? `<span class="cnt">${s.orders}</span>` : ''}${k === 'qs' && s.open ? `<span class="cnt">${s.open}</span>` : ''}</button>`).join('');
  $$('[data-tab]').forEach(b => b.onclick = () => { S.tab = b.dataset.tab; loadAdmin(); });
  try { await adminTabs[S.tab](box, s); } catch (x) { console.error(x); toast(x.message); box.innerHTML = `<div class="note" role="alert"><p><b>ადმინის მონაცემების ჩატვირთვა ვერ მოხერხდა.</b> ${esc(x && x.message || String(x))}</p></div>`; }
  fillBars();
}

const adminTabs = {
  async overview(box, s) {
    const paying = plans().filter(p => p.level).reduce((n, p) => n + (s.by[p.id] || 0), 0), mx = Math.max(1, ...s.signups);
    box.innerHTML = `<div class="stats">${[['მოსწავლე', s.users], ['გადამხდელი', paying], ['თვიური შემოსავალი', s.mrr + ' ₾'], ['ახალი 7 დღეში', s.new7], ['აქტიური 7 დღეში', s.active7], ['საშუალო პროგრესი', s.completion + '%'], ['ქვიზის საშუალო', s.quiz_avg == null ? '—' : s.quiz_avg + '%']].map(([k, v]) => `<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('')}</div>
    <div class="two"><div class="panel"><h2>ახალი რეგისტრაციები</h2><p class="why">ბოლო 8 კვირა, კვირების მიხედვით (ბოლო მარჯვნივ)</p>
      <div class="bars">${s.signups.map(v => `<div>${v}<i data-h="${Math.round(v / mx * 90)}"></i></div>`).join('')}</div>
      <h2>გეგმების განაწილება</h2><table><tbody>${plans().map(p => `<tr><td>${esc(p.name)}</td><td>${s.by[p.id] || 0}</td></tr>`).join('')}</tbody></table>
      <div class="row"><button class="btn sm line" id="bk">ბაზის ასლის შექმნა</button></div></div>
      <div class="panel"><h2>პროგრესი ეტაპების მიხედვით</h2><div class="scroll"><table><tr><th>ეტაპი</th><th>დაიწყო</th><th>დასრულების დონე</th></tr>${s.stages.map(g => {
        const pc = s.users && g.lessons ? Math.round(g.done * 100 / (g.lessons * s.users)) : 0;
        return `<tr><td>${g.stage}. ${esc(g.title)}</td><td>${g.learners}</td><td><div class="mini">${bar(pc)}<small>${pc}%</small></div></td></tr>`; }).join('')}</table></div></div></div>`;
    $('#bk').onclick = async () => { try { const r = await api('admin/backup', {}); toast('ასლი შეიქმნა: ' + r.name); } catch (x) { toast(x.message); } };
  },
  async orders(box) {
    const o = await api('admin/orders' + (S.oall ? '?all=1' : ''));
    const st = { pending: 'მოლოდინში', approved: 'დადასტურდა', rejected: 'უარყოფილია' }, cl = { pending: '', approved: 'ok', rejected: 'bad' };
    box.innerHTML = `<label class="chk"><input type="checkbox" id="oa" ${S.oall ? 'checked' : ''}><span>ისტორიის ჩვენება (ბოლო 200)</span></label>` + (o.orders.length ? `<div class="scroll"><table><tr><th>სახელი</th><th>ელფოსტა</th><th>გეგმა</th><th>თარიღი</th>${S.oall ? '<th>სტატუსი</th>' : ''}<th></th></tr>${o.orders.map(x => `<tr><td>${esc(x.name || 'წაშლილი მომხმარებელი')}</td><td>${esc(x.email || '—')}</td><td>${esc(planOf(x.plan).name)} (${planOf(x.plan).price} ₾)</td><td>${fmtDate(x.created)}</td>${S.oall ? `<td><span class="badge ${cl[x.status] || ''}">${st[x.status] || esc(x.status)}</span></td>` : ''}<td>${x.status === 'pending' ? `<button class="btn sm" data-o="${x.id}" data-act="approve">დადასტურება (30 დღე)</button> <button class="btn sm line" data-o="${x.id}" data-act="reject">უარყოფა</button>` : fmtDate(x.decided_at)}</td></tr>`).join('')}</table></div><p class="why">დადასტურება გეგმას მომხმარებელს 30 დღით ააქტიურებს. გააკეთე ეს გადახდის მიღების შემდეგ.</p>` : '<p>განაცხადები არ არის.</p>');
    $('#oa').onchange = e => { S.oall = e.target.checked; loadAdmin(); };
    $$('[data-o]').forEach(b => b.onclick = async () => { try { await api('admin/order', { id: +b.dataset.o, action: b.dataset.act }); toast('შესრულდა'); loadAdmin(); } catch (x) { toast(x.message); } });
  },
  async users(box) {
    box.innerHTML = `<div class="tools"><div><label for="sf">ძებნა</label><input id="sf" class="search" placeholder="სახელი ან ელფოსტა" value="${esc(S.au.q)}"></div>
      <div><label for="pf2">გეგმა</label><select id="pf2"><option value="">ყველა</option>${plans().map(p => `<option value="${p.id}" ${S.au.plan === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></div>
      <a class="btn sm line" id="csv" href="/api/admin/users.csv">CSV ექსპორტი</a></div><div class="scroll"><table id="ut"></table></div><div class="pager" id="pg"></div>`;
    const draw = async () => {
      const qs = new URLSearchParams({ q: S.au.q, plan: S.au.plan, page: S.au.page, course: S.ac }), d = await api('admin/users?' + qs);
      $('#csv').href = '/api/admin/users.csv?' + new URLSearchParams({ q: S.au.q, plan: S.au.plan, course: S.ac });
      $('#ut').innerHTML = `<tr><th>სახელი და ელფოსტა</th><th>გეგმა</th><th>ვადა</th><th>პროგრესი</th><th>ბოლო შესვლა</th><th></th></tr>` + (d.users.length ? d.users.map(u => {
        const pc = d.lessons ? Math.round(u.done * 100 / d.lessons) : 0;
        return `<tr><td><b>${esc(u.name)}</b>${u.role === 'admin' ? ' <span class="badge">ადმინი</span>' : ''}<br><small class="why">${esc(u.email)}</small></td>
        <td><select data-pl="${u.id}" aria-label="გეგმა">${plans().map(p => `<option value="${p.id}" ${p.id === u.plan ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></td>
        <td>${u.plan !== 'free' ? (u.plan_expires ? fmtDate(u.plan_expires) + (u.plan_expires < Date.now() ? ' (ვადაგასული)' : '') : 'უვადო') : '—'}</td>
        <td><div class="mini">${bar(pc)}<small>${u.done}/${d.lessons}</small></div></td><td>${fmtDate(u.last_login)}</td>
        <td><input class="d" type="number" min="0" max="3650" value="30" data-d="${u.id}" aria-label="დღეები"> <button class="btn sm" data-u="${u.id}">შენახვა</button> <button class="btn sm line" data-r="${u.id}">პაროლი</button>${u.role === 'admin' ? '' : ` <button class="btn sm line" data-x="${u.id}" data-n="${esc(u.email)}">წაშლა</button>`}</td></tr>`; }).join('') : '<tr><td colspan="6">ვერაფერი მოიძებნა.</td></tr>');
      const pages = Math.max(1, Math.ceil(d.total / d.per));
      $('#pg').innerHTML = `<span class="why">სულ: ${d.total}</span>${d.page > 0 ? '<button class="btn sm line" id="pv">წინა</button>' : ''}<span>${d.page + 1} / ${pages}</span>${d.page + 1 < pages ? '<button class="btn sm line" id="nx">შემდეგი</button>' : ''}`;
      if ($('#pv')) $('#pv').onclick = () => { S.au.page--; draw(); };
      if ($('#nx')) $('#nx').onclick = () => { S.au.page++; draw(); };
      fillBars();
      $$('[data-u]').forEach(b => b.onclick = async () => { try { await api('admin/plan', { id: +b.dataset.u, plan: $(`[data-pl="${b.dataset.u}"]`).value, days: +$(`[data-d="${b.dataset.u}"]`).value }); toast('შენახულია'); draw(); } catch (x) { toast(x.message); } });
      $$('[data-r]').forEach(b => b.onclick = async () => { if (!confirm('პაროლი შეიცვლება და მომხმარებელი გამოვა სისტემიდან. გაგრძელება?')) return; try { const r = await api('admin/resetpw', { id: +b.dataset.r }); prompt('დროებითი პაროლი (გადაეცი მოსწავლეს და სთხოვე შეცვლა):', r.password); } catch (x) { toast(x.message); } });
      $$('[data-x]').forEach(b => b.onclick = async () => { if (!confirm(`წაიშლება ${b.dataset.n} და მისი ყველა მონაცემი. ეს შეუქცევადია. გაგრძელება?`)) return; try { await api('admin/user_delete', { id: +b.dataset.x }); toast('წაიშალა'); draw(); } catch (x) { toast(x.message); } });
    };
    let t; $('#sf').oninput = e => { clearTimeout(t); t = setTimeout(() => { S.au.q = e.target.value.trim(); S.au.page = 0; draw(); }, 250); };
    $('#pf2').onchange = e => { S.au.plan = e.target.value; S.au.page = 0; draw(); };
    await draw();
  },
  async qs(box) {
    box.innerHTML = `<div class="tools"><div><label for="qf">ჩვენება</label><select id="qf"><option value="open" ${S.qf === 'open' ? 'selected' : ''}>უპასუხო</option><option value="task" ${S.qf === 'task' ? 'selected' : ''}>დავალებები</option><option value="all" ${S.qf === 'all' ? 'selected' : ''}>ყველა</option></select></div></div><div id="ql"></div>`;
    $('#qf').onchange = e => { S.qf = e.target.value; loadQ($('#ql'), S.ac); };
    await loadQ($('#ql'), S.ac);
  },
  async lessons(box) {
    const { lessons } = await api('admin/lessons?course=' + encodeURIComponent(S.ac));
    box.innerHTML = `<p class="why">ვიდეოს ბმულები (https; YouTube/Vimeo ჩვეულებრივი ბმულიც ვარგა), სათაური და არხი (გამოჩნდება ვიდეოს ქვეშ), სათადარიგო ვიდეო და PDF. ბმულის შეცვლისას ძველი სათაური/არხი, თუ ხელით არ შეცვალე, იშლება. კურსის განახლებისას ეს მონაცემები არ იშლება.</p><div class="scroll"><table><tr><th>გაკვეთილი</th><th>ვიდეო</th><th>სათაური</th><th>არხი</th><th>სათადარიგო ვიდეო</th><th>სათადარიგოს სათაური</th><th>სათადარიგოს არხი</th><th>PDF</th><th></th></tr>${lessons.map(l => `<tr data-r="${l.id}"><td>${l.stage}.${l.pos} ${esc(l.title)}</td><td><input class="wide" data-f="v" value="${esc(l.video_url)}" aria-label="ვიდეო"></td><td><input class="wide" data-f="t" maxlength="200" value="${esc(l.video_title)}" aria-label="ვიდეოს სათაური"></td><td><input data-f="c" maxlength="200" value="${esc(l.video_channel)}" aria-label="არხი"></td><td><input class="wide" data-f="v2" value="${esc(l.video2_url)}" aria-label="სათადარიგო ვიდეო"></td><td><input class="wide" data-f="t2" maxlength="200" value="${esc(l.video2_title)}" aria-label="სათადარიგოს სათაური"></td><td><input data-f="c2" maxlength="200" value="${esc(l.video2_channel)}" aria-label="სათადარიგოს არხი"></td><td><input class="wide" data-f="p" value="${esc(l.pdf_url)}" aria-label="PDF"></td><td><button class="btn sm" data-l="${l.id}">შენახვა</button></td></tr>`).join('')}</table></div>`;
    $$('[data-l]').forEach(b => b.onclick = async () => {
      const id = +b.dataset.l, row = $(`[data-r="${id}"]`), g = k => row.querySelector(`[data-f="${k}"]`).value, orig = lessons.find(x => x.id === id);
      try { await api('admin/lesson', { id, ...videoPayload({ v: g('v'), t: g('t'), c: g('c'), v2: g('v2'), t2: g('t2'), c2: g('c2') }, orig), pdf_url: g('p').trim() }); toast('შენახულია'); await load(); } catch (x) { toast(x.message); }
    });
  },
  async audit(box) {
    const { events } = await api('admin/audit');
    box.innerHTML = `<p class="why">უსაფრთხოებისა და ადმინისტრირების ბოლო 200 მოვლენა. ბევრი წარუმატებელი შესვლა ერთი ელფოსტით ან IP-ით პაროლის გამოცნობის მცდელობაა.</p><div class="scroll"><table><tr><th>დრო</th><th>მოვლენა</th><th>მომხმარებელი</th><th>დეტალი</th><th>IP</th></tr>${events.map(e => `<tr><td>${fmtTime(e.created)}</td><td><span class="badge ${e.action === 'login_fail' ? 'bad' : ''}">${esc(ACT[e.action] || e.action)}</span></td><td>${esc(e.email || '—')}</td><td>${esc(e.detail)}</td><td>${esc(e.ip)}</td></tr>`).join('')}</table></div>`;
  }
};

async function boot(go) { try { await load(); } catch (e) { toast('სერვერთან კავშირი ვერ დამყარდა'); } S.loaded = true; if (go) location.hash = go; route(); }
addEventListener('hashchange', route);
boot();
