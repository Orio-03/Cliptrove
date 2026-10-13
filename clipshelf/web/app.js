(() => {
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const META = D.meta, TOKEN = META.token || '';
const AUDIO = !!META.ffmpeg;  // extra tracks (Chat, Mic...) can be played: ClipShelf pulls them out of the clip
const $ = id => document.getElementById(id);

const P = {
  play: '<path d="M7 4.6v14.8a.6.6 0 0 0 .9.5l11.6-7.4a.6.6 0 0 0 0-1L7.9 4.1a.6.6 0 0 0-.9.5z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/>',
  prev: '<path d="M18 5.5v13L8.5 12z" fill="currentColor" stroke="none"/><path d="M6 5.5v13"/>',
  next: '<path d="M6 5.5v13l9.5-6.5z" fill="currentColor" stroke="none"/><path d="M18 5.5v13"/>',
  chevl: '<path d="m15 5-7 7 7 7"/>',
  chevr: '<path d="m9 5 7 7-7 7"/>',
  back: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 4v4.5H8"/><text x="12.5" y="15.5" font-size="7.5" font-weight="700" text-anchor="middle" fill="currentColor" stroke="none">5</text>',
  fwd: '<path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"/><path d="M20.5 4v4.5H16"/><text x="11.5" y="15.5" font-size="7.5" font-weight="700" text-anchor="middle" fill="currentColor" stroke="none">5</text>',
  vol: '<path d="M11 5 6 9H3v6h3l5 4z" fill="currentColor"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>',
  mute: '<path d="M11 5 6 9H3v6h3l5 4z" fill="currentColor"/><path d="m22 9-6 6M16 9l6 6"/>',
  full: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  loop: '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" fill="currentColor"/>',
  staro: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  save: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  pad: '<path d="M6.5 8h11a4.5 4.5 0 0 1 4.3 5.8l-.6 2a2.8 2.8 0 0 1-4.6 1.2L14.4 15H9.6L7.4 17a2.8 2.8 0 0 1-4.6-1.2l-.6-2A4.5 4.5 0 0 1 6.5 8z"/><path d="M7.5 10.5v3M6 12h3"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5M14 11v5"/>',
  film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  power: '<path d="M12 3v8"/><path d="M6.3 6.8a8 8 0 1 0 11.4 0"/>',
};
const ic = n => `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || ''}</svg>`;
document.querySelectorAll('[data-ic]').forEach(el => el.insertAdjacentHTML('afterbegin', ic(el.dataset.ic)));

const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
const pad = n => String(n).padStart(2, '0');
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function fmtDate(iso) {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return '—';
  return `${d.getDate()} ${MON[d.getMonth()]} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fmtAgo(ts) {
  const s = (Date.now() - ts) / 1000;
  if (s < 3600) return 'just now';
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  if (d < 31) return d === 1 ? 'yesterday' : `${d} days ago`;
  if (d < 365) return `${Math.floor(d / 30.4)} mo ago`;
  return `${Math.floor(d / 365)} yr ago`;
}
function fmtLen(s) {
  s = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
function fmtExact(s) {
  const t = Math.round(Math.max(0, s || 0) * 10), m = Math.floor(t / 600), r = t - m * 600;
  return `${m}:${pad(Math.floor(r / 10))}.${r % 10}`;
}
const fmtSize = bytes => (bytes / 1048576).toFixed(1) + ' MB';
function hue(s) { let h = 0; for (const ch of String(s)) h = (h * 31 + ch.codePointAt(0)) >>> 0; return h % 360; }
function initials(g) {
  const w = String(g).replace(/[™®©]/g, '').split(/[\s\-_:.]+/).filter(Boolean);
  if (!w.length) return '?';
  return (w.length > 1 ? w[0][0] + w[1][0] : w[0].slice(0, 2)).toUpperCase();
}
const store = {  // settings kept in this browser (older ones were saved as "ggclips.*")
  get(k, d) {
    try { let v = localStorage.getItem('clipshelf.' + k); if (v === null) v = localStorage.getItem('ggclips.' + k); return v === null ? d : v; }
    catch (e) { return d; }
  },
  set(k, v) { try { localStorage.setItem('clipshelf.' + k, v); } catch (e) {} },
};
let toastTimer;
function toast(msg, err) {
  const t = $('toast');
  t.textContent = msg; t.className = 'toast' + (err ? ' err' : ''); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, err ? 4500 : 2800);
}
async function post(path, body) {
  const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}
async function getJSON(path) {
  const r = await fetch(path + (path.includes('?') ? '&' : '?') + 't=' + encodeURIComponent(TOKEN));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}
const trackUrl = (c, n) => `/audio/${c.id}/${n}?t=${encodeURIComponent(TOKEN)}`;
const level = t => (t && !t.muted ? (t.volume ?? 1) : 0);  // a track's volume in the clip's mix

// ---------- motion helpers ----------
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
const canAnimate = () => !reduceMotion.matches && !!document.startViewTransition && !document.hidden;
let vtSeq = 0;
// Run a page change as a smooth transition (kind picks the animation); falls back to an instant change.
function vt(kind, update) {
  if (!canAnimate()) { update(); return Promise.resolve(); }
  const seq = ++vtSeq;
  document.documentElement.dataset.vt = kind;
  const t = document.startViewTransition(update);
  t.ready.catch(() => {});  // a transition interrupted by the next click is fine; the page still updates
  return t.finished.catch(() => {}).finally(() => { if (seq === vtSeq) delete document.documentElement.dataset.vt; });
}
window.csImg = img => { img.classList.add('in'); const t = img.closest('.thumb'); if (t) t.classList.add('ready'); };
window.csImgFail = img => { const t = img.closest('.thumb'); if (t) t.classList.add('ready'); img.remove(); };
// The highlight that slides under the active tab / filter
function placeInd(box) {
  if (!box || !box.offsetParent) return;
  let ind = box.querySelector(':scope > .seg-ind');
  const fresh = !ind;
  if (fresh) { ind = document.createElement('span'); ind.className = 'seg-ind'; box.prepend(ind); box.classList.add('has-ind'); }
  const on = box.querySelector('.on');
  if (fresh) ind.style.transition = 'none';
  ind.style.opacity = on ? '1' : '0';
  if (on) { ind.style.width = on.offsetWidth + 'px'; ind.style.transform = `translateX(${on.offsetLeft}px)`; }
  if (fresh) requestAnimationFrame(() => { ind.style.transition = ''; });
}
function replay(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }

// ---------- data ----------
const clips = D.clips, byId = new Map();
const shownTitle = c => c.nick || c.title;
const UNSORTED = 'Unsorted';
function indexClip(c) { c.search = [c.nick, c.title, c.game, c.file, fmtDate(c.recorded), c.srcLabel].join(' ').toLowerCase(); }
for (const c of clips) {
  c.ts = Date.parse(c.recorded) || 0;
  c.len = c.trimmed ? c.end - c.start : c.full;
  indexClip(c);
  byId.set(c.id, c);
}
const COVER = new Map(D.games.map(g => [g.name, g.cover]));
const GAMES = new Set(clips.map(c => c.game));
const filterPref = store.get('filter', 'all');
const state = {view: 'home', game: '', filter: filterPref === 'nick' ? 'titled' : filterPref, sort: store.get('sort', 'new'), catSort: store.get('catSort', 'recent'), q: []};
// What a clip's trim / title / star came from, in words
const trimWord = c => (c.trimSrc === 'gg' ? 'Trimmed in GG' : 'Trimmed');
const titleWord = c => (c.src === 'gg' ? 'GG title' : 'Title');

// Clips that have Chat/Mic: keep them playing in step with the video they belong to.
function syncTracks(video, els, force) {
  const t = video.currentTime, running = !video.paused && !video.seeking && video.readyState >= 3;
  for (const el of els) {
    if (el.readyState < 1) continue;
    if (el.playbackRate !== video.playbackRate) el.playbackRate = video.playbackRate;
    const inside = t < (el.duration || Infinity) - 0.05;
    if (inside && (force || Math.abs(el.currentTime - t) > 0.12)) el.currentTime = t;
    if (running && inside) { if (el.paused) el.play().catch(() => {}); }
    else if (!el.paused) el.pause();
  }
}
// Chat/Mic for the home page and hover previews (plain audio elements; volumes up to 100%)
function attachTracks(video, c) {
  if (!AUDIO || c.tracks.length < 2) return null;
  const els = c.tracks.slice(1).map((t, k) => { const a = new Audio(); a.preload = 'auto'; a.lvl = level(t); a.src = trackUrl(c, k + 1); return a; });
  const sync = force => syncTracks(video, els, force);
  const evs = {seeked: () => sync(true), play: () => sync(true), playing: () => sync(true), pause: () => sync(false), waiting: () => sync(false), seeking: () => sync(false), ratechange: () => sync(false)};
  for (const k in evs) video.addEventListener(k, evs[k]);
  els.forEach(a => a.addEventListener('canplay', () => { applyPreviewVolumes(); sync(true); }, {once: true}));
  const timer = setInterval(() => sync(false), 250);
  return {els, destroy() {
    clearInterval(timer);
    for (const k in evs) video.removeEventListener(k, evs[k]);
    els.forEach(a => { a.pause(); a.removeAttribute('src'); a.load(); });
  }};
}

// ---------- preview volume (home page + hover previews), default 20% ----------
const pvol = {vol: clamp(+store.get('pvol', '0.2') || 0, 0, 1), muted: store.get('pmuted', '0') === '1'};
function setPreviewVolume(video, tracks, c) {
  const blocked = video.dataset.blocked === '1';
  video.volume = clamp(pvol.vol * level(c.tracks[0]), 0, 1);
  video.muted = pvol.muted || blocked;
  if (tracks) for (const a of tracks.els) { a.volume = clamp(pvol.vol * a.lvl, 0, 1); a.muted = video.muted; }
}
function applyPreviewVolumes() {
  if (hero.cur) {
    if (!hero.video.muted && !hero.audio && !hero.video.paused) hero.audio = attachTracks(hero.video, hero.cur);
    setPreviewVolume(hero.video, hero.audio, hero.cur);
  }
  if (pv) setPreviewVolume(pv.v, pv.audio, pv.c);
  document.querySelectorAll('.vctl').forEach(updateVolCtl);
}
function playWithSound(video) {
  video.play().catch(err => {
    if (err && err.name === 'NotAllowedError' && !video.muted) {
      // The browser only allows sound after you've clicked something on the page
      video.dataset.blocked = '1';
      video.muted = true;
      video.play().catch(() => {});
      document.querySelectorAll('.vctl').forEach(updateVolCtl);
    }
  });
}
function volCtl() {
  const el = document.createElement('div');
  el.className = 'vctl';
  el.title = 'Preview volume';
  el.innerHTML = '<button type="button" aria-label="Mute or unmute"></button><input type="range" min="0" max="100" step="1" aria-label="Preview volume"><span class="vval"></span>';
  const unblock = () => document.querySelectorAll('video[data-blocked="1"]').forEach(v => { v.dataset.blocked = ''; });
  el.querySelector('button').onclick = () => {
    const blocked = document.querySelector('video[data-blocked="1"]');
    unblock();
    pvol.muted = blocked ? false : !pvol.muted;
    if (!pvol.muted && pvol.vol === 0) pvol.vol = 0.2;
    store.set('pmuted', pvol.muted ? '1' : '0'); store.set('pvol', String(pvol.vol));
    applyPreviewVolumes();
  };
  el.querySelector('input').oninput = e => {
    unblock();
    pvol.vol = +e.target.value / 100;
    pvol.muted = pvol.vol === 0;
    store.set('pvol', String(pvol.vol)); store.set('pmuted', pvol.muted ? '1' : '0');
    applyPreviewVolumes();
  };
  ['click', 'pointerdown', 'mousedown', 'keydown'].forEach(ev => el.addEventListener(ev, e => e.stopPropagation()));
  updateVolCtl(el);
  return el;
}
function updateVolCtl(el) {
  const silent = pvol.muted || pvol.vol === 0 || !!document.querySelector('video[data-blocked="1"]');
  el.querySelector('button').innerHTML = ic(silent ? 'mute' : 'vol');
  el.querySelector('input').value = Math.round(pvol.vol * 100);
  el.querySelector('.vval').textContent = silent ? 'Muted' : Math.round(pvol.vol * 100) + '%';
}

// ---------- header, banner and navigation ----------
const root = document.documentElement, banner = $('banner');
function setThemeIcon() { $('bTheme').innerHTML = ic(root.dataset.theme === 'dark' ? 'sun' : 'moon'); }
$('bTheme').onclick = () => { root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark'; store.set('theme', root.dataset.theme); setThemeIcon(); };
$('bRefresh').onclick = () => location.reload();  // opening the page re-reads every clip source
let bannerKind = '';
function showBanner(html, kind) { banner.innerHTML = html; banner.hidden = !html; bannerKind = html ? kind : ''; }
if (!META.ffmpeg) showBanner('ffmpeg wasn’t found, so Chat/Mic audio, thumbnails for clips from folders and saving edited copies are off. '
  + 'Install it (for example <span class="mono">winget install Gyan.FFmpeg</span>) and restart ClipShelf.', 'ffmpeg');
banner.addEventListener('click', e => { if (e.target.closest('[data-reload]')) location.reload(); });
// Check in with ClipShelf: notices new clips, a restart, or ClipShelf having stopped
let misses = 0;
async function ping() {
  let next = 20000;
  try {
    const r = await getJSON('/api/ping');
    misses = 0;
    if (r.session !== META.session && !cur) { location.reload(); return; }  // ClipShelf was restarted
    const scan = r.scan || {};
    if (scan.pending > 0) {
      next = 2500;
      const total = Math.max(scan.total || 0, scan.pending), done = total - scan.pending;
      showBanner(`Reading new clips… ${done.toLocaleString()} of ${total.toLocaleString()}`, 'scan');
    } else if (r.version !== META.version) {
      if (bannerKind !== 'new') showBanner('Your clips have changed. <button class="btn sm primary" type="button" data-reload>Show the latest</button>', 'new');
    } else if (bannerKind === 'scan' || bannerKind === 'stopped') showBanner('', '');
  } catch (e) {
    if (++misses === 2) showBanner('ClipShelf has stopped. Start it again from its shortcut or ClipShelf.bat, then refresh this page.', 'stopped');
  }
  setTimeout(ping, next);
}
setTimeout(ping, META.scan && META.scan.pending ? 1500 : 20000);
function parseHash() {
  const h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
  if (h === 'all') return {view: 'game', game: ''};
  if (h.startsWith('game/') && GAMES.has(h.slice(5))) return {view: 'game', game: h.slice(5)};
  if (h === 'log') return {view: 'log', game: ''};
  if (h === 'edited') return {view: 'edited', game: ''};
  if (h === 'settings') return {view: 'settings', game: ''};
  if (h === 'analytics') return {view: 'analytics', game: ''};
  return {view: 'home', game: ''};
}
const DEPTH = {home: 0, log: 0, edited: 0, settings: 0, analytics: 0, game: 1};
const scrollMemo = new Map();
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';  // the page restores scroll itself, after the transition starts
let curHash = null;
const tileCover = game => $('tiles').querySelector(`a.tile[href="#/game/${encodeURIComponent(game)}"] > .cover`);
function applyRoute(to) {
  state.view = to.view; state.game = to.game;
  const views = {home: $('homeView'), game: $('gameView'), edited: $('editedView'), log: $('logView'), settings: $('settingsView'), analytics: $('statsView')};
  for (const [v, el] of Object.entries(views)) el.hidden = v !== state.view;
  const tab = state.view === 'game' ? 'home' : state.view;
  $('tabs').querySelectorAll('a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  $('bSettings').classList.toggle('on', state.view === 'settings');
  stopPreview();
  render();
  heroSync();
  placeInd($('tabs'));
  placeInd($('filters'));
  if (!document.startViewTransition && !reduceMotion.matches) replay(views[state.view], 'view-in');
}
function restoreScroll(y) {
  if (y > 0 && state.view === 'game') {
    while (document.documentElement.scrollHeight < y + innerHeight && shown < list.length) more();
  }
  window.scrollTo({top: y, behavior: 'instant'});
}
// Going into a game slides forward and its cover grows into the page's cover; going back reverses it.
function route(first) {
  const to = parseHash(), from = {view: state.view, game: state.game};
  const hash = location.hash || '#/';
  if (from.view === 'settings' && to.view !== 'settings' && setDirty) { location.reload(); return; }  // show the new library
  if (curHash !== null) scrollMemo.set(curHash, scrollY);
  curHash = hash;
  if (first === true) { applyRoute(to); return; }
  const dir = DEPTH[to.view] > DEPTH[from.view] ? 'forward' : DEPTH[to.view] < DEPTH[from.view] ? 'back' : 'fade';
  const y = dir === 'forward' ? 0 : scrollMemo.get(hash) || 0;
  let source = null, target = null;
  if (canAnimate()) {
    source = dir === 'forward' && to.game ? tileCover(to.game) : dir === 'back' && from.game ? $('ghead').querySelector('.cover') : null;
    if (source && inView(source)) source.style.viewTransitionName = 'game-cover'; else source = null;
  }
  vt(dir, () => {
    if (source) source.style.viewTransitionName = '';
    applyRoute(to);
    restoreScroll(y);
    if (source) {
      target = dir === 'forward' ? $('ghead').querySelector('.cover') : tileCover(from.game);
      if (target && inView(target)) target.style.viewTransitionName = 'game-cover'; else target = null;
    }
  }).then(() => { if (target) target.style.viewTransitionName = ''; });
}
window.addEventListener('hashchange', route);
let scrollRaf = 0;
window.addEventListener('scroll', () => {
  if (scrollRaf) return;
  scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; document.querySelector('.top').classList.toggle('scrolled', scrollY > 4); });
}, {passive: true});
window.addEventListener('resize', () => { placeInd($('tabs')); placeInd($('filters')); });
if (document.fonts) document.fonts.ready.then(() => { placeInd($('tabs')); placeInd($('filters')); });
function render() {
  if (state.view === 'home') renderHome();
  else if (state.view === 'game') renderGame();
  else if (state.view === 'edited') renderEdited();
  else if (state.view === 'settings') renderSettings();
  else if (state.view === 'analytics') renderStats();
  else renderLog();
}
let qTimer;
$('q').addEventListener('input', () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => {
    state.q = $('q').value.toLowerCase().split(/\s+/).filter(Boolean);
    if (state.q.length && ['home', 'settings', 'analytics'].includes(state.view)) location.hash = '#/all';
    else render();
  }, 150);
});

// ---------- home: highlighted clips (your 5 newest, playing one after another) ----------
const hero = {clips: [...clips].sort((a, b) => b.ts - a.ts).slice(0, 5), i: 0, items: [], offs: [], video: null, prog: null, audio: null, cur: null, s: 0, e: 0};
function buildHero() {
  const el = $('hero');
  if (!hero.clips.length) { el.hidden = true; return; }
  el.innerHTML = '<div class="hero-amb" aria-hidden="true"><i></i><i></i></div>'
    + hero.clips.map((c, i) => `<div class="hitem" data-i="${i}">${c.thumb ? `<img src="${esc(c.thumb)}" alt="" onload="csImg(this)" onerror="this.remove()">` : ''}</div>`).join('')
    + '<div class="hinfo" id="hinfo"></div><div class="hvol" id="hvol"></div>'
    + `<button class="harrow l" data-d="-1" title="Previous">${ic('chevl')}</button><button class="harrow r" data-d="1" title="Next">${ic('chevr')}</button>`
    + `<div class="hdots">${hero.clips.map((c, i) => `<button data-i="${i}" title="${esc(shownTitle(c))}"></button>`).join('')}</div>`;
  hero.items = [...el.querySelectorAll('.hitem')];
  $('hvol').appendChild(volCtl());
  const v = hero.video = document.createElement('video');
  v.playsInline = true; v.preload = 'auto';
  hero.prog = document.createElement('div'); hero.prog.className = 'hprog';
  v.addEventListener('playing', () => { v.classList.add('on'); applyPreviewVolumes(); });
  v.addEventListener('timeupdate', () => {
    const c = hero.cur; if (!c || !(hero.e > 0)) return;
    const p = clamp((v.currentTime - hero.s) / Math.max(0.1, hero.e - hero.s), 0, 1);
    hero.prog.style.width = p * 100 + '%';
    const dot = $('hero').querySelector('.hdots button.on');
    if (dot) dot.style.setProperty('--p', p);
    if (v.currentTime >= hero.e - 0.08) heroShow(hero.i + 1);
  });
  v.addEventListener('ended', () => heroShow(hero.i + 1));
  v.addEventListener('error', () => { const c = hero.cur; if (c && v.getAttribute('src')) setTimeout(() => { if (hero.cur === c) heroShow(hero.i + 1); }, 1500); });
  el.addEventListener('click', e => {
    const item = e.target.closest('.hitem'), arrow = e.target.closest('.harrow'), dot = e.target.closest('.hdots button'), watch = e.target.closest('[data-watch]');
    if (arrow) heroShow(hero.i + +arrow.dataset.d);
    else if (dot) heroShow(+dot.dataset.i);
    else if (watch || (item && +item.dataset.i === hero.i)) openClip(hero.clips[hero.i].id, hero.clips, hero.items[hero.i]);
    else if (item) heroShow(+item.dataset.i);
  });
  heroShow(0);
}
function layoutHero() {
  const el = $('hero'), W = el.clientWidth;
  if (!W || !hero.items.length) return;
  const compact = W < 860;
  const iw = compact ? 0 : Math.round(clamp(W * 0.2, 260, 340));
  const vw = compact ? W : Math.round(clamp(W * 0.48, 420, 820)), hh = Math.round(vw * 9 / 16);
  el.classList.toggle('compact', compact);
  el.style.setProperty('--vw', vw + 'px'); el.style.setProperty('--hh', hh + 'px'); el.style.setProperty('--iw', iw + 'px');
  el.style.height = (compact ? hh + $('hinfo').offsetHeight : hh) + 'px';
  const n = hero.items.length, cx = -iw / 2, CW = (vw + iw) / 2;
  hero.items.forEach((it, i) => {
    let o = ((i - hero.i) % n + n) % n;
    if (o > n / 2) o -= n;
    let x = cx, s = 1, z = 5, show = true;
    if (o !== 0) {
      const sg = Math.sign(o), s1 = 0.8, s2 = 0.64;
      const out1 = sg * CW + sg * 0.28 * vw * s1;
      if (Math.abs(o) === 1) { s = s1; x = out1 - sg * vw * s1 / 2; z = 4; }
      else { s = s2; x = out1 + sg * 0.2 * vw * s2 - sg * vw * s2 / 2; z = 3; }
      show = !compact && Math.abs(o) <= 2;
    }
    const prev = hero.offs[i];
    it.classList.toggle('instant', prev !== undefined && Math.abs(prev - o) > 2);  // wrapping round: jump instead of flying across
    it.style.transform = `translateX(${x}px) scale(${s})`;
    it.style.zIndex = z;
    it.style.opacity = show ? 1 : 0;
    it.style.pointerEvents = show ? '' : 'none';
    it.classList.toggle('center', o === 0);
    it.classList.toggle('side', o !== 0);
    hero.offs[i] = o;
  });
  $('hinfo').style.transform = compact ? '' : `translateX(${cx + vw / 2}px)`;
  $('hvol').style.transform = `translateX(${cx - vw / 2 + 12}px)`;
  if (!el.classList.contains('ready')) requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('ready')));
}
function heroShow(i) {
  const n = hero.clips.length;
  if (!n) return;
  hero.i = ((i % n) + n) % n;
  const c = hero.clips[hero.i], v = hero.video;
  $('hero').querySelectorAll('.hdots button').forEach((b, k) => { b.classList.toggle('on', k === hero.i); b.style.setProperty('--p', 0); });
  // Soft glow behind the carousel, cross-fading to the new clip
  const amb = $('hero').querySelectorAll('.hero-amb i');
  hero.amb = hero.amb ? 0 : 1;
  if (c.thumb) amb[hero.amb].style.backgroundImage = `url("${c.thumb}")`;
  amb[hero.amb].classList.toggle('on', !!c.thumb);
  amb[1 - hero.amb].classList.remove('on');
  const cover = COVER.get(c.game);
  $('hinfo').innerHTML = `<span class="hlabel">${ic('play')} Recent clip</span>`
    + `<a class="hgame" href="#/game/${encodeURIComponent(c.game)}">${cover ? `<img src="${esc(cover)}" alt="" onerror="this.remove()">` : `<span class="gicon" style="--h:${hue(c.game)}">${esc(initials(c.game))}</span>`}<span>${esc(c.game)}</span></a>`
    + `<div class="htitle${!c.custom && !c.nick ? ' auto' : ''}">${esc(shownTitle(c))}</div>`
    + (c.nick && (c.custom || c.src === 'gg') ? `<div class="hmeta">${titleWord(c)}: ${esc(c.title)}</div>` : '')
    + `<div class="hmeta">${fmtDate(c.recorded)}${c.len > 0 ? ` · ${fmtLen(c.len)}` : ''}</div>`
    + `<div class="tags">${c.nick ? '<span class="tag nick">Nickname</span>' : ''}${c.starred ? `<span class="tag star">${ic('star')} Starred</span>` : ''}${c.trimmed ? `<span class="tag">${trimWord(c)}</span>` : ''}</div>`
    + `<div class="hbtns"><button class="btn primary" data-watch>${ic('play')} Watch</button><a class="btn" href="#/game/${encodeURIComponent(c.game)}">More ${esc(c.game)}</a></div>`;
  replay($('hinfo'), 'swap');
  layoutHero();
  if (hero.audio) { hero.audio.destroy(); hero.audio = null; }
  v.pause();
  v.classList.remove('on');
  hero.items[hero.i].append(v, hero.prog);
  hero.prog.style.width = '0';
  hero.cur = c; hero.s = c.trimmed ? c.start : 0; hero.e = (c.trimmed ? c.end : c.full) || 0;
  v.addEventListener('loadedmetadata', () => {
    if (hero.cur !== c) return;
    hero.e = Math.min(hero.e || v.duration, v.duration);
    v.currentTime = hero.s;
    heroSync();
  }, {once: true});
  v.src = c.video;
  setPreviewVolume(v, null, c);
  const nextClip = hero.clips[(hero.i + 1) % n];
  if (AUDIO && nextClip !== c && nextClip.tracks.length > 1) post('/api/prefetch', {id: nextClip.id}).catch(() => {});
}
function heroSync() {
  const v = hero.video;
  if (!v || !hero.cur) return;
  const active = state.view === 'home' && !cur && !document.hidden;
  if (active && v.readyState >= 1) {
    if (v.paused) { setPreviewVolume(v, hero.audio, hero.cur); playWithSound(v); }
  } else if (!active && !v.paused) v.pause();
}
document.addEventListener('visibilitychange', heroSync);
let resizeRaf = 0;
window.addEventListener('resize', () => {
  cancelAnimationFrame(resizeRaf);
  resizeRaf = requestAnimationFrame(() => { layoutHero(); if (state.view === 'analytics') renderStats(true); });
});

// ---------- home: games ----------
function gameStats() {
  const m = new Map();
  for (const c of clips) {
    let s = m.get(c.game);
    if (!s) m.set(c.game, s = {name: c.game, count: 0, titled: 0, starred: 0, last: 0, thumb: ''});
    s.count++;
    if (c.custom || c.nick) s.titled++;
    if (c.starred) s.starred++;
    if (c.ts >= s.last) { s.last = c.ts; if (c.thumb) s.thumb = c.thumb; }
  }
  return [...m.values()];
}
// Cover art, or (offline / no art) a tile made from the game's newest clip
function coverHTML(s, extraClass = '') {
  const url = COVER.get(s.name);
  const gen = `<div class="gen" style="--h:${hue(s.name)}"${url ? ` data-thumb="${esc(s.thumb)}"` : ''}>${!url && s.thumb ? `<img loading="lazy" src="${esc(s.thumb)}" alt="" onload="csImg(this)" onerror="this.remove()">` : ''}<span>${esc(s.name)}</span></div>`;
  return `<div class="cover ${extraClass}">${gen}${url ? `<img loading="lazy" src="${esc(url)}" alt="" onload="csImg(this)" onerror="csCoverFail(this)">` : ''}</div>`;
}
window.csCoverFail = img => {
  const gen = img.parentNode.querySelector('.gen');
  if (gen && gen.dataset.thumb) gen.insertAdjacentHTML('afterbegin', `<img loading="lazy" src="${esc(gen.dataset.thumb)}" alt="" onload="csImg(this)" onerror="this.remove()">`);
  img.remove();
};
const CAT_SORTS = {recent: (a, b) => b.last - a.last, clips: (a, b) => b.count - a.count, name: (a, b) => a.name.localeCompare(b.name)};
function renderHome() {
  const empty = !clips.length;
  $('welcome').hidden = !empty;
  for (const id of ['homeHead', 'tiles', 'homeFoot']) $(id).hidden = empty;
  if (empty) return;
  const stats = gameStats().sort(CAT_SORTS[state.catSort] || CAT_SORTS.recent);
  const total = stats.reduce((n, s) => n + s.count, 0), titled = stats.reduce((n, s) => n + s.titled, 0), starred = stats.reduce((n, s) => n + s.starred, 0);
  const four = [...stats].sort((a, b) => (COVER.get(b.name) ? 1 : 0) - (COVER.get(a.name) ? 1 : 0) || b.last - a.last).slice(0, 4);
  const tags = s => `<div class="tags">${s.titled ? `<span class="tag">${s.titled} titled</span>` : ''}${s.starred ? `<span class="tag star">${ic('star')} ${s.starred}</span>` : ''}</div>`;
  const rise = i => `class="tile rise" style="--d:${Math.min(i, 16) * 28}ms"`;
  $('tiles').innerHTML = `<a ${rise(0)} href="#/all"><div class="cover"><div class="mosaic">${four.map(s => `<div>${coverHTML(s)}</div>`).join('')}</div><div class="all-label">All games</div></div>`
    + `<div class="tname">All games</div><div class="tmeta">${total.toLocaleString()} clips</div>${tags({titled, starred})}</a>`
    + stats.map((s, i) => `<a ${rise(i + 1)} href="#/game/${encodeURIComponent(s.name)}" title="${esc(s.name)}">${coverHTML(s)}<div class="tname">${esc(s.name)}</div>`
      + `<div class="tmeta">${s.count.toLocaleString()} ${s.count === 1 ? 'clip' : 'clips'} · ${fmtAgo(s.last)}</div>${tags(s)}</a>`).join('');
  $('catCount').textContent = `${stats.length} games`;
}
$('catSort').value = CAT_SORTS[state.catSort] ? state.catSort : 'recent';
$('catSort').onchange = () => { state.catSort = $('catSort').value; store.set('catSort', state.catSort); renderHome(); };

// ---------- a game's clips (or all clips) ----------
const grid = $('grid');
function matches(c) {
  if (state.filter === 'titled' && !(c.custom || c.nick)) return false;
  if (state.filter === 'starred' && !c.starred) return false;
  if (state.game && c.game !== state.game) return false;
  return state.q.every(t => c.search.includes(t));
}
const SORTS = {
  new: (a, b) => b.ts - a.ts,
  old: (a, b) => a.ts - b.ts,
  long: (a, b) => b.len - a.len || b.ts - a.ts,
  short: (a, b) => a.len - b.len || b.ts - a.ts,
  title: (a, b) => shownTitle(a).localeCompare(shownTitle(b)) || b.ts - a.ts,
  game: (a, b) => a.game.localeCompare(b.game) || b.ts - a.ts,
};
let list = [], shown = 0;
const PAGE = 48;
function renderGame() {
  const name = state.game, own = clips.filter(c => !name || c.game === name);
  const s = gameStats().find(x => x.name === name) || {name: 'All games', thumb: (own[0] || {}).thumb || ''};
  const titled = own.filter(c => c.custom || c.nick).length, starred = own.filter(c => c.starred).length;
  const last = own.reduce((m, c) => Math.max(m, c.ts), 0);
  $('ghead').innerHTML = (name ? coverHTML(s) : '')
    + `<div><h1>${esc(name || 'All games')}</h1><div class="gstats"><span>${own.length.toLocaleString()} clips</span>`
    + (titled ? `<span class="tag">${titled} titled</span>` : '') + (starred ? `<span class="tag star">${ic('star')} ${starred}</span>` : '')
    + (last ? `<span>· last played ${fmtAgo(last)}</span>` : '') + '</div>'
    + (name === UNSORTED ? '<p class="hint dim" style="margin:8px 0 0">Clips whose game couldn’t be worked out from their name or folder. Open one to put it under a game.</p>' : '')
    + '</div>';
  // Blurred art behind the header: the game's cover, or the newest clip
  const newest = own.reduce((a, c) => (!a || c.ts > a.ts ? c : a), null);
  const art = (name && COVER.get(name)) || (newest && newest.thumb) || '';
  $('gbannerArt').style.backgroundImage = art ? `url("${art}")` : 'none';
  renderClips();
}
function renderClips() {
  stopPreview();
  list = clips.filter(matches).sort(SORTS[state.sort] || SORTS.new);
  grid.textContent = '';
  shown = 0;
  more();
  $('count').textContent = `${list.length.toLocaleString()} ${list.length === 1 ? 'clip' : 'clips'}`;
  $('noResults').hidden = list.length > 0;
}
function more() {
  if (state.view !== 'game' || shown >= list.length) return;
  const frag = document.createDocumentFragment();
  list.slice(shown, shown + PAGE).forEach((c, i) => frag.appendChild(cardEl(c, i)));
  grid.appendChild(frag);
  shown = Math.min(list.length, shown + PAGE);
  requestAnimationFrame(() => { if ($('sentinel').getBoundingClientRect().top < innerHeight + 900) more(); });
}
new IntersectionObserver(es => { if (es[0].isIntersecting) more(); }, {rootMargin: '900px'}).observe($('sentinel'));
function cardEl(c, i) {
  const el = document.createElement('article');
  el.className = 'card'; el.dataset.id = c.id; el.tabIndex = 0;
  if (i !== undefined) { el.classList.add('rise'); el.style.setProperty('--d', Math.min(i, 12) * 30 + 'ms'); }
  const auto = !c.custom && !c.nick;
  el.innerHTML = `<div class="thumb${c.thumb ? '' : ' ready'}">${c.thumb ? `<img loading="lazy" decoding="async" src="${esc(c.thumb)}" alt="" onload="csImg(this)" onerror="csImgFail(this)">` : ''}`
    + `<span class="play-ic">${ic('play')}</span>`
    + (c.starred ? `<span class="badge star" title="${c.ggStar ? 'Starred in GG' : 'Starred'}">${ic('star')}</span>` : '')
    + (c.trimmed ? `<span class="badge cut" title="${trimWord(c)}">${ic('scissors')}</span>` : '')
    + (c.len > 0 ? `<span class="badge len">${fmtLen(c.len)}</span>` : '') + '</div>'
    + `<div class="info"><div class="ginfo"><i class="gdot" style="--h:${hue(c.game)}"></i><span>${esc(c.game)}</span>`
    + (c.nick ? '<span class="tag nick" title="You gave this clip a nickname">Nickname</span>' : c.edited && /\(18MB\)/.test(c.file) ? '<span class="tag">18 MB</span>' : '') + '</div>'
    + `<div class="ctitle${auto ? ' auto' : ''}" title="${esc(shownTitle(c))}">${esc(shownTitle(c))}</div>`
    + `<div class="csub">${c.edited ? `${fmtSize(c.size)} · saved ${fmtDate(c.made)}` : `${c.nick && c.src === 'gg' ? `GG: ${esc(c.title)} · ` : ''}${fmtDate(c.recorded)}`}</div></div>`;
  el.addEventListener('mouseenter', () => hoverStart(el));
  el.addEventListener('mouseleave', () => hoverEnd(el));
  return el;
}
grid.addEventListener('click', e => { const card = e.target.closest('.card'); if (card) openClip(card.dataset.id, list, card.querySelector('.thumb')); });
grid.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || cur) return;
  const card = e.target.closest('.card');
  if (card) { e.preventDefault(); openClip(card.dataset.id, list, card.querySelector('.thumb')); }
});
function refreshCard(c) { const old = grid.querySelector(`.card[data-id="${c.id}"]`); if (old) old.replaceWith(cardEl(c)); }
function syncFilterButtons() { $('filters').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.f === state.filter)); placeInd($('filters')); }
$('filters').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  state.filter = b.dataset.f; store.set('filter', state.filter);
  syncFilterButtons(); renderClips();
};
$('sort').onchange = () => { state.sort = $('sort').value; store.set('sort', state.sort); renderClips(); };

// Hover a clip to preview it (with sound at the preview volume)
const canHover = matchMedia('(hover: hover)').matches;
let pv = null, pvTimer = 0;
function hoverStart(card) {
  if (!canHover || cur) return;
  clearTimeout(pvTimer);
  pvTimer = setTimeout(() => startPreview(card), 450);
}
function hoverEnd(card) {
  clearTimeout(pvTimer);
  if (pv && pv.card === card) stopPreview();
}
function startPreview(card) {
  stopPreview();
  const c = byId.get(card.dataset.id);
  if (!c || !card.isConnected) return;
  const thumb = card.querySelector('.thumb');
  const v = document.createElement('video');
  v.className = 'pv'; v.playsInline = true; v.preload = 'auto';
  const bar = document.createElement('div'); bar.className = 'pbar';
  const ctl = volCtl();
  const s = c.trimmed ? c.start : 0, e = (c.trimmed ? c.end : c.full) || 0;
  thumb.append(v, bar, ctl);
  card.classList.add('previewing');
  pv = {card, c, v, bar, ctl, audio: null, audioTimer: 0};
  v.addEventListener('loadedmetadata', () => { v.currentTime = s; setPreviewVolume(v, null, c); playWithSound(v); }, {once: true});
  v.addEventListener('playing', () => v.classList.add('on'));
  v.addEventListener('timeupdate', () => {
    const end = e > 0 ? Math.min(e, v.duration || e) : v.duration;  // length not known yet: the whole video
    if (!(end > 0)) return;
    if (v.currentTime >= end - 0.08) v.currentTime = s;
    bar.style.width = clamp((v.currentTime - s) / Math.max(0.1, end - s), 0, 1) * 100 + '%';
  });
  v.src = c.video;
  // Only fetch Chat/Mic once you've stayed on the clip for a moment
  pv.audioTimer = setTimeout(() => { if (pv && pv.c === c) { pv.audio = attachTracks(v, c); setPreviewVolume(v, pv.audio, c); } }, 700);
}
function stopPreview() {
  clearTimeout(pvTimer);
  if (!pv) return;
  const p = pv; pv = null;
  clearTimeout(p.audioTimer);
  if (p.audio) p.audio.destroy();
  p.v.pause(); p.v.removeAttribute('src'); p.v.load();
  p.v.remove(); p.bar.remove(); p.ctl.remove();
  p.card.classList.remove('previewing');
}

// ---------- edited clips (everything in "Edited Clips") ----------
let edits = [], edList = [], edSort = store.get('edSort', 'new');
const ED_SORTS = {new: (a, b) => b.ts - a.ts, old: (a, b) => a.ts - b.ts, big: (a, b) => b.size - a.size, name: (a, b) => a.title.localeCompare(b.title)};
function setEdits(items) {
  for (const e of edits) byId.delete(e.id);
  edits = items || [];
  for (const e of edits) {
    e.ts = Date.parse(e.made) || 0;
    e.len = e.full;
    e.search = [e.title, e.game, e.file, e.sourceTitle].join(' ').toLowerCase();
    byId.set(e.id, e);
  }
  $('edPill').textContent = edits.length || '';
}
async function refreshEdited() {
  try { setEdits((await getJSON('/api/edited')).items); } catch (e) { return; }
  if (state.view === 'edited') renderEdited();
}
function renderEdited() {
  stopPreview();
  edList = edits.filter(e => state.q.every(t => e.search.includes(t))).sort(ED_SORTS[edSort] || ED_SORTS.new);
  const g = $('edGrid');
  g.textContent = '';
  const frag = document.createDocumentFragment();
  edList.forEach((e, i) => frag.appendChild(cardEl(e, i)));
  g.appendChild(frag);
  $('edCount').textContent = edits.length ? `${edList.length} of ${edits.length}` : '';
  $('edEmpty').hidden = edList.length > 0;
  $('edEmpty').textContent = edits.length ? 'No edited clips match your search.' : 'No edited clips yet. Open a clip, trim it and press Save copy.';
}
$('edGrid').addEventListener('click', e => { const card = e.target.closest('.card'); if (card) openClip(card.dataset.id, edList, card.querySelector('.thumb')); });
$('edGrid').addEventListener('keydown', e => {
  if (e.key !== 'Enter' || cur) return;
  const card = e.target.closest('.card');
  if (card) { e.preventDefault(); openClip(card.dataset.id, edList, card.querySelector('.thumb')); }
});
$('edSort').value = ED_SORTS[edSort] ? edSort : 'new';
$('edSort').onchange = () => { edSort = $('edSort').value; store.set('edSort', edSort); renderEdited(); };
$('edFolder').onclick = () => post('/api/reveal', {folder: true}).catch(err => toast(err.message, true));
setEdits(D.edits);

// ---------- change log ----------
const KIND = {title: 'GG title', file: 'File renamed', new: 'New titled clip', removed: 'Removed from GG', nickname: 'Nickname'};
function changeText(ch) {
  const old = v => v ? `<span class="old">${esc(v)}</span>` : '<span class="dim">none</span>';
  const after = v => v ? `<b>${esc(v)}</b>` : '<span class="dim">removed</span>';
  if (ch.kind === 'title' || ch.kind === 'nickname') return `${old(ch.before)}<span class="arrow">→</span>${after(ch.after)}`;
  if (ch.kind === 'file') return `${old(ch.before)}<span class="arrow">→</span><span class="mono">${esc(ch.after)}</span>`;
  if (ch.kind === 'new') return `<b>${esc(ch.after)}</b>`;
  return old(ch.before);
}
function renderLog() {
  $('logCount').textContent = D.changes.length || '';
  if (state.view !== 'log') return;
  const body = $('logBody');
  if (!D.changes.length) {
    body.innerHTML = `<p class="empty">Tracking since ${fmtDate(META.started)}. When you give a clip a nickname here, or change a clip’s title in SteelSeries GG, it shows up in this list.</p>`;
    return;
  }
  const rows = D.changes
    .map(ch => ({ch, s: [ch.game, ch.before, ch.after, ch.file, KIND[ch.kind]].join(' ').toLowerCase()}))
    .filter(r => state.q.every(t => r.s.includes(t)))
    .reverse();
  if (!rows.length) { body.innerHTML = '<p class="empty">No changes match your search.</p>'; return; }
  body.innerHTML = `<div class="tablewrap"><table><thead><tr><th>When</th><th>What</th><th>Clip</th><th>Change</th></tr></thead><tbody>`
    + rows.map(({ch}) => `<tr><td class="when">${fmtDate(ch.when)}</td><td><span class="kind ${esc(ch.kind)}">${esc(KIND[ch.kind] || ch.kind)}</span></td>`
      + `<td><div class="clipcell"><span class="gicon" style="--h:${hue(ch.game || '')}">${esc(initials(ch.game || '?'))}</span><div>${esc(ch.game)}<br>`
      + (ch.id && byId.has(ch.id) ? `<button class="link-btn mono" data-open="${ch.id}">${esc(ch.file)}</button>` : `<span class="mono dim">${esc(ch.file)}</span>`)
      + `</div></div></td><td>${changeText(ch)}</td></tr>`).join('')
    + `</tbody></table></div>`;
}
$('logBody').addEventListener('click', e => { const b = e.target.closest('[data-open]'); if (b) openClip(b.dataset.open, [byId.get(b.dataset.open)], null); });

// ---------- analytics ----------
// A day counts as "played" when it has at least one clip of the game. Desktop recordings and unsorted clips
// aren't games, so they're left out. Charts are drawn here; the predictions come from ClipShelf (/api/analytics).
const DAY_MS = 86400000;
const NOT_GAMES = new Set(['desktop', 'unsorted', 'unknowngame']);
const normName = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '');
const SERIES = ['#07f2cc', '#7b8cff', '#ffb547', '#ff6b9a', '#4cc9f0', '#b98cff'];
const OTHER = 'Other games';
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const RANGE_WORD = {30: 'the 30 days before', 90: 'the 3 months before', 365: 'the 12 months before'};
// Days are numbered in your local calendar (read them back with the getUTC* methods)
const dayOf = ts => { const d = new Date(ts); return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY_MS; };
const dateOf = n => new Date(n * DAY_MS);
const weekday = n => (dateOf(n).getUTCDay() + 6) % 7;  // 0 = Monday
function fmtDayNo(n, withYear = true) { const d = dateOf(n); return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}` + (withYear ? ` ${d.getUTCFullYear()}` : ''); }
const isoDay = s => { const [y, m, d] = s.split('-').map(Number); return Date.UTC(y, m - 1, d) / DAY_MS; };
const pctText = p => (p > 0 && p < 0.01 ? '<1%' : `${Math.round(p * 100)}%`);
const st = {range: store.get('stRange', '365'), metric: store.get('stMetric', 'days'), focus: '', pred: null, predLoading: false, colors: new Map()};

function statClips() {
  const out = [];
  for (const c of clips) {
    if (!c.ts || NOT_GAMES.has(normName(c.game))) continue;
    const d = new Date(c.ts);
    out.push({game: c.game, day: dayOf(c.ts), wd: (d.getDay() + 6) % 7, hour: d.getHours()});
  }
  return out;
}
function longestStreak(days) {
  let best = 0, run = 0, prev = null;
  for (const d of [...days].sort((a, b) => a - b)) { run = prev !== null && d === prev + 1 ? run + 1 : 1; best = Math.max(best, run); prev = d; }
  return best;
}
// A small tooltip that follows the pointer inside a box
function tipFor(box) {
  let t = box.querySelector(':scope > .ctip');
  if (!t) { t = document.createElement('div'); t.className = 'ctip'; box.appendChild(t); }
  return {
    show(html, clientX, clientY) {
      t.innerHTML = html;
      t.classList.add('on');
      const r = box.getBoundingClientRect(), x = clientX - r.left, y = clientY - r.top, w = t.offsetWidth, h = t.offsetHeight;
      t.style.left = clamp(x + 16 + w > r.width ? x - w - 16 : x + 16, 0, Math.max(0, r.width - w)) + 'px';
      t.style.top = (y - h - 12 < 0 ? y + 18 : y - h - 12) + 'px';
    },
    hide() { t.classList.remove('on'); },
  };
}
function artHTML(game) {
  const url = COVER.get(game);
  return `<span class="art" style="--h:${hue(game)}">${esc(initials(game))}${url ? `<img src="${esc(url)}" alt="" loading="lazy" onerror="this.remove()">` : ''}</span>`;
}

function renderStats(still) {
  const all = statClips(), today = dayOf(Date.now());
  const first = all.reduce((m, x) => Math.min(m, x.day), today);
  const r = st.range === 'all' ? 'all' : String([30, 90, 365].includes(+st.range) ? +st.range : 90);
  const from = r === 'all' ? first : today - (+r - 1);
  const list = all.filter(x => x.day >= from && x.day <= today);
  $('stRange').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.r === r));
  $('stMetric').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.m === st.metric));
  $('stSpan').textContent = all.length ? `${fmtDayNo(from)} – ${fmtDayNo(today)}` : '';
  placeInd($('stRange')); placeInd($('stMetric'));
  $('statsView').classList.toggle('still', !!still);
  renderKpis(list, all, from, today, r);
  renderChart(list, from, today, r);
  renderTop(list);
  renderWhen(list);
  renderCal(all, today);
  if (!still) renderPredictions();
}
$('stRange').onclick = e => { const b = e.target.closest('button'); if (!b) return; st.range = b.dataset.r; store.set('stRange', st.range); renderStats(); };
$('stMetric').onclick = e => { const b = e.target.closest('button'); if (!b) return; st.metric = b.dataset.m; store.set('stMetric', st.metric); renderStats(); };

function renderKpis(list, all, from, today, r) {
  const days = new Set(list.map(x => x.day)), per = new Map(), firstSeen = new Map();
  for (const x of all) if (!firstSeen.has(x.game) || x.day < firstSeen.get(x.game)) firstSeen.set(x.game, x.day);
  for (const x of list) { let s = per.get(x.game); if (!s) per.set(x.game, s = new Set()); s.add(x.day); }
  let top = null;
  for (const [g, s] of per) if (!top || s.size > top[1]) top = [g, s.size];
  const fresh = [...per.keys()].filter(g => firstSeen.get(g) >= from).length;
  let clipsCmp = '', daysCmp = '';
  if (r !== 'all') {
    const len = today - from + 1, prev = all.filter(x => x.day >= from - len && x.day < from);
    const cmp = (now, before) => {
      if (!before) return now ? `<small class="up">None in ${RANGE_WORD[r]}</small>` : '';
      const d = Math.round((now - before) / before * 100);
      return `<small class="${d > 0 ? 'up' : d < 0 ? 'down' : ''}">${d > 0 ? '↑ ' : d < 0 ? '↓ ' : ''}${Math.abs(d)}% vs ${RANGE_WORD[r]}</small>`;
    };
    clipsCmp = cmp(list.length, prev.length);
    daysCmp = cmp(days.size, new Set(prev.map(x => x.day)).size);
  }
  const card = (label, value, sub = '', txt = false) => `<div class="kpi"><span>${label}</span><b${txt ? ' class="txt"' : ''} title="${esc(value)}">${esc(value)}</b>${sub}</div>`;
  $('stKpis').innerHTML = card('Clips', list.length.toLocaleString(), clipsCmp)
    + card('Days with clips', days.size.toLocaleString(), daysCmp)
    + card('Games played', per.size.toLocaleString(), fresh && r !== 'all' ? `<small>${fresh} new to you</small>` : '')
    + card('Most played', top ? top[0] : '—', top ? `<small>${plural(top[1], 'day', 'days')}</small>` : '', true)
    + card('Longest streak', plural(longestStreak(days), 'day', 'days'), '<small>in a row with clips</small>');
}

function chartBuckets(from, today, r) {
  const unit = r === '30' ? 'day' : r === 'all' && today - from > 540 ? 'month' : 'week';
  const out = [];
  if (unit === 'day') {
    for (let d = from; d <= today; d++) out.push({a: d, b: d, label: fmtDayNo(d, false), tip: `${WDAYS[weekday(d)]} ${fmtDayNo(d)}`});
  } else if (unit === 'week') {
    for (let s = from - weekday(from); s <= today; s += 7) out.push({a: s, b: s + 6, label: fmtDayNo(s, false), tip: `Week of ${fmtDayNo(s)}`});
  } else {
    const d0 = dateOf(from);
    for (let y = d0.getUTCFullYear(), m = d0.getUTCMonth(); ; m === 11 ? (m = 0, y++) : m++) {
      const a = Date.UTC(y, m, 1) / DAY_MS;
      if (a > today) break;
      out.push({a, b: Date.UTC(y, m + 1, 1) / DAY_MS - 1, label: m === 0 || !out.length ? `${MON[m]} ’${String(y).slice(2)}` : MON[m], tip: `${MONTHS[m]} ${y}`});
    }
  }
  return {unit, buckets: out};
}
function niceStep(max) {
  const raw = max / 4, p = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  for (const k of [1, 2, 2.5, 5, 10]) if (k * p >= raw) return Math.max(1, k * p);
  return 10 * p;
}
function renderChart(list, from, today, r) {
  const box = $('stChart'), metric = st.metric, add = n => (metric === 'days' ? 1 : n);
  const byDay = new Map(), totals = new Map();
  for (const x of list) { let m = byDay.get(x.day); if (!m) byDay.set(x.day, m = new Map()); m.set(x.game, (m.get(x.game) || 0) + 1); }
  for (const m of byDay.values()) for (const [g, n] of m) totals.set(g, (totals.get(g) || 0) + add(n));
  const top = [...totals].sort((a, b) => b[1] - a[1]).slice(0, SERIES.length).map(([g]) => g);
  st.colors = new Map(top.map((g, i) => [g, SERIES[i]]));
  const rest = [...totals].filter(([g]) => !st.colors.has(g)).reduce((n, [, v]) => n + v, 0);
  const series = top.concat(rest ? [OTHER] : []);
  const color = s => st.colors.get(s) || 'var(--line-2)';
  if (st.focus && !series.includes(st.focus)) st.focus = '';
  const {unit, buckets} = chartBuckets(from, today, r);
  const vals = buckets.map(b => {
    const v = new Map(series.map(s => [s, 0]));
    for (let d = b.a; d <= b.b; d++) {
      const m = byDay.get(d);
      if (m) for (const [g, n] of m) { const s = st.colors.has(g) ? g : OTHER; v.set(s, v.get(s) + add(n)); }
    }
    return v;
  });
  const W = Math.max(280, box.clientWidth), H = box.clientHeight || 280, M = {l: 38, r: 6, t: 8, b: 26};
  const max = Math.max(1, ...vals.map(v => [...v.values()].reduce((a, b) => a + b, 0)));
  const step = niceStep(max), ceil = Math.ceil(max / step) * step;
  const y = v => M.t + (H - M.t - M.b) * (1 - v / ceil);
  const band = (W - M.l - M.r) / buckets.length, bw = Math.max(2, Math.min(42, band * 0.68));
  let axes = '';
  for (let v = step; v <= ceil + 1e-9; v += step) axes += `<line class="gl" x1="${M.l}" x2="${W - M.r}" y1="${y(v)}" y2="${y(v)}"/><text x="${M.l - 8}" y="${y(v) + 4}" text-anchor="end">${+v.toFixed(1)}</text>`;
  axes += `<text x="${M.l - 8}" y="${y(0) + 4}" text-anchor="end">0</text>`;
  const every = Math.max(1, Math.ceil(buckets.length / Math.max(2, Math.floor((W - M.l) / 66))));
  buckets.forEach((b, i) => { if (i % every === 0) axes += `<text x="${M.l + band * (i + 0.5)}" y="${H - 6}" text-anchor="middle">${esc(b.label)}</text>`; });
  let bars = '';
  vals.forEach((v, i) => {
    let acc = 0, segs = '';
    const x = (M.l + band * i + (band - bw) / 2).toFixed(1);
    for (const s of series) {
      const n = v.get(s);
      if (!n) continue;
      const y1 = y(acc + n), y0 = y(acc);
      segs += `<rect class="s${st.focus === s ? ' f' : ''}" data-s="${esc(s)}" x="${x}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, y0 - y1).toFixed(1)}" rx="2" fill="${color(s)}"/>`;
      acc += n;
    }
    if (segs) bars += `<g class="col" style="animation-delay:${Math.min(i, 40) * 12}ms">${segs}</g>`;
  });
  const label = `${metric === 'days' ? 'Days played' : 'Clips'} per ${unit}`;
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)} for your top games">`
    + `<rect class="hl" x="0" y="${M.t}" width="${band}" height="${H - M.t - M.b}" rx="6"/>${axes}`
    + `<line class="base" x1="${M.l}" x2="${W - M.r}" y1="${y(0)}" y2="${y(0)}"/>${bars}`
    + (list.length ? '' : `<text class="empty-msg" x="${W / 2}" y="${H / 2}" text-anchor="middle">No clips in this period</text>`) + '</svg>';
  box.classList.toggle('focus', !!st.focus);
  const svg = box.querySelector('svg'), hl = svg.querySelector('.hl'), tip = tipFor(box);
  const words = metric === 'days' ? ['day', 'days'] : ['clip', 'clips'];
  svg.onpointermove = e => {
    const rect = svg.getBoundingClientRect(), i = Math.floor(((e.clientX - rect.left) * W / rect.width - M.l) / band);
    if (i < 0 || i >= buckets.length) { tip.hide(); hl.classList.remove('on'); return; }
    hl.setAttribute('x', M.l + band * i);
    hl.classList.add('on');
    const v = vals[i], rows = series.filter(s => v.get(s)).sort((a, b) => v.get(b) - v.get(a));
    const total = rows.reduce((n, s) => n + v.get(s), 0);
    tip.show(`<b>${esc(buckets[i].tip)}</b>`
      + (rows.length ? rows.map(s => `<div class="r"><i class="sw" style="--c:${color(s)}"></i><span>${esc(s)}</span><em>${plural(v.get(s), ...words)}</em></div>`).join('') : '<span class="dim">No clips</span>')
      + (rows.length > 1 && metric === 'clips' ? `<em class="tot">${plural(total, 'clip', 'clips')} in all</em>` : ''), e.clientX, e.clientY);
  };
  svg.onpointerleave = () => { tip.hide(); hl.classList.remove('on'); };
  $('stLegend').innerHTML = series.map(s => `<button type="button" data-s="${esc(s)}" class="${st.focus === s ? 'on' : ''}" style="--c:${color(s)}"><i class="sw"></i><span>${esc(s)}</span><em>${(s === OTHER ? rest : totals.get(s)).toLocaleString()}</em></button>`).join('');
  $('stLegend').classList.toggle('focus', !!st.focus);
  $('stChartSub').textContent = list.length ? `${label}, your top ${plural(top.length, 'game', 'games')}${rest ? ' and the rest' : ''}. Click a game to pick it out.` : '';
}
$('stLegend').addEventListener('click', e => {
  const b = e.target.closest('button[data-s]');
  if (!b) return;
  st.focus = st.focus === b.dataset.s ? '' : b.dataset.s;
  $('stChart').classList.toggle('focus', !!st.focus);
  $('stChart').querySelectorAll('rect.s').forEach(r => r.classList.toggle('f', r.dataset.s === st.focus));
  $('stLegend').classList.toggle('focus', !!st.focus);
  $('stLegend').querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.s === st.focus));
});

function renderTop(list) {
  const per = new Map();
  for (const x of list) {
    let s = per.get(x.game);
    if (!s) per.set(x.game, s = {game: x.game, days: new Set(), clips: 0});
    s.days.add(x.day); s.clips++;
  }
  const rows = [...per.values()].sort((a, b) => b.days.size - a.days.size || b.clips - a.clips).slice(0, 8);
  const max = rows.length ? rows[0].days.size : 1;
  $('stTopSub').textContent = per.size ? `By days played, out of ${plural(per.size, 'game', 'games')} in this period` : '';
  $('stTop').innerHTML = rows.length ? '<div class="toplist">' + rows.map((s, i) => `<a class="toprow" href="#/game/${encodeURIComponent(s.game)}">`
    + `<span class="rk">${i + 1}</span>${artHTML(s.game)}<div style="min-width:0"><div class="nm" title="${esc(s.game)}">${esc(s.game)}</div>`
    + `<div class="meter" style="--c:${st.colors.get(s.game) || 'var(--line-2)'}"><i style="width:${(s.days.size / max * 100).toFixed(1)}%;animation-delay:${i * 40}ms"></i></div></div>`
    + `<div class="val"><b>${plural(s.days.size, 'day', 'days')}</b>${plural(s.clips, 'clip', 'clips')}</div></a>`).join('') + '</div>'
    : '<p class="empty">No clips in this period.</p>';
}

function renderWhen(list) {
  const box = $('stWhen'), grid = Array.from({length: 7}, () => new Array(24).fill(0));
  for (const x of list) grid[x.wd][x.hour]++;
  const max = Math.max(...grid.flat());
  if (!max) { box.innerHTML = '<p class="empty">No clips in this period.</p>'; $('stWhenSub').textContent = ''; return; }
  const W = Math.max(280, box.clientWidth), L = 34, gap = 3, cell = Math.max(6, Math.min(24, (W - L) / 24 - gap)), H = 7 * (cell + gap) + 18;
  const lvl = n => (n ? 1 + Math.min(3, Math.floor(n / max * 4)) : 0);
  let s = '';
  for (let d = 0; d < 7; d++) {
    s += `<text x="${L - 8}" y="${d * (cell + gap) + cell / 2 + 4}" text-anchor="end">${WDAYS[d].slice(0, 3)}</text>`;
    for (let h = 0; h < 24; h++) s += `<rect class="c l${lvl(grid[d][h])}" data-d="${d}" data-h="${h}" x="${L + h * (cell + gap)}" y="${d * (cell + gap)}" width="${cell}" height="${cell}"/>`;
  }
  for (const h of [0, 6, 12, 18]) s += `<text x="${L + h * (cell + gap)}" y="${H - 3}">${pad(h)}:00</text>`;
  const dayTotals = grid.map(row => row.reduce((a, b) => a + b, 0)), hourTotals = grid[0].map((_, h) => grid.reduce((n, row) => n + row[h], 0));
  const topDay = Math.max(...dayTotals);
  box.innerHTML = `<div class="heatbox"><svg class="heat" width="${L + 24 * (cell + gap)}" height="${H}" role="img" aria-label="Clips by weekday and hour">${s}</svg></div>`
    + '<div class="wdays">' + WDAYS.map((name, d) => `<div class="wday"><span>${name}</span><div class="meter"><i style="width:${(dayTotals[d] / topDay * 100).toFixed(1)}%;animation-delay:${d * 40}ms"></i></div><em>${plural(dayTotals[d], 'clip', 'clips')}</em></div>`).join('') + '</div>';
  const bestDay = dayTotals.indexOf(Math.max(...dayTotals)), bestHour = hourTotals.indexOf(Math.max(...hourTotals));
  $('stWhenSub').textContent = `Most clips on ${WDAYS[bestDay]}s, and around ${pad(bestHour)}:00`;
  const tip = tipFor(box.querySelector('.heatbox'));
  box.querySelector('svg').onpointermove = e => {
    const c = e.target.closest('rect.c');
    if (!c) { tip.hide(); return; }
    const d = +c.dataset.d, h = +c.dataset.h;
    tip.show(`<b>${WDAYS[d]}, ${pad(h)}:00–${pad((h + 1) % 24)}:00</b><span>${plural(grid[d][h], 'clip', 'clips')}</span>`, e.clientX, e.clientY);
  };
  box.querySelector('svg').onpointerleave = () => tip.hide();
}

function renderCal(all, today) {
  const box = $('stCal'), per = new Map();
  for (const x of all) {
    if (x.day <= today - 371 || x.day > today) continue;
    let m = per.get(x.day);
    if (!m) per.set(x.day, m = new Map());
    m.set(x.game, (m.get(x.game) || 0) + 1);
  }
  const end = today + (6 - weekday(today)), start = end - 53 * 7 + 1;  // 53 full weeks, Monday to Sunday
  const gap = 3, L = 30, T = 18, cell = clamp(Math.floor((box.clientWidth - L) / 53) - gap, 10, 17);
  const W = L + 53 * (cell + gap), H = T + 7 * (cell + gap);
  const count = d => { const m = per.get(d); return m ? [...m.values()].reduce((a, b) => a + b, 0) : 0; };
  const lvl = n => (!n ? 0 : n <= 2 ? 1 : n <= 5 ? 2 : n <= 10 ? 3 : 4);
  let s = '', month = -1, active = 0;
  for (let w = 0; w < 53; w++) {
    const first = start + w * 7, m = dateOf(first).getUTCMonth();
    if (m !== month && w < 51) { s += `<text x="${L + w * (cell + gap)}" y="11">${MON[m]}</text>`; month = m; }
    for (let d = 0; d < 7; d++) {
      const day = first + d;
      if (day > today) continue;
      const n = count(day);
      if (n) active++;
      s += `<rect class="c l${lvl(n)}" data-day="${day}" x="${L + w * (cell + gap)}" y="${T + d * (cell + gap)}" width="${cell}" height="${cell}"/>`;
    }
  }
  for (const [d, name] of [[0, 'Mon'], [2, 'Wed'], [4, 'Fri']]) s += `<text x="${L - 6}" y="${T + d * (cell + gap) + cell - 2}" text-anchor="end">${name}</text>`;
  box.innerHTML = `<svg class="heat" width="${W}" height="${H}" role="img" aria-label="Clips per day over the last 12 months">${s}</svg>`
    + `<div class="scale">Fewer ${[0, 1, 2, 3, 4].map(l => `<i class="l${l}"></i>`).join('')} More</div>`;
  $('stCalSub').textContent = `${plural(active, 'day', 'days')} with clips in the last 12 months`;
  const panel = box.closest('.panel'), tip = tipFor(panel);
  box.querySelector('svg').onpointermove = e => {
    const c = e.target.closest('rect.c');
    if (!c) { tip.hide(); return; }
    const day = +c.dataset.day, m = per.get(day);
    const games = m ? [...m].sort((a, b) => b[1] - a[1]).slice(0, 4) : [];
    tip.show(`<b>${WDAYS[weekday(day)]} ${fmtDayNo(day)}</b>` + (games.length
      ? games.map(([g, n]) => `<div class="r"><i class="sw" style="--c:${st.colors.get(g) || 'var(--line-2)'}"></i><span>${esc(g)}</span><em>${n}</em></div>`).join('')
      : '<span class="dim">No clips</span>'), e.clientX, e.clientY);
  };
  box.querySelector('svg').onpointerleave = () => tip.hide();
}

async function loadPredictions() {
  if (st.predLoading) return;
  st.predLoading = true;
  try { st.pred = await getJSON('/api/analytics'); } catch (e) { st.pred = {error: e.message}; }
  st.predLoading = false;
  if (state.view === 'analytics') renderPredictions();
}
function renderPredictions() {
  const body = $('stNextBody'), r = st.pred;
  if (!r) { body.innerHTML = '<div class="preds">' + '<div class="skel"></div>'.repeat(3) + '</div>'; loadPredictions(); return; }
  if (r.error) { body.innerHTML = `<p class="empty">Couldn’t work out predictions: ${esc(r.error)}</p>`; return; }
  if (!r.enough) {
    body.innerHTML = `<p class="empty">Not enough history yet. Predictions start once you have about 20 days with clips (you have ${r.activeDays}).</p>`;
    return;
  }
  const cards = r.predictions.slice(0, 6).map((p, i) => {
    const tag = GAMES.has(p.game) ? 'a' : 'div';
    return `<${tag} class="pred${i === 0 ? ' lead' : ''}"${tag === 'a' ? ` href="#/game/${encodeURIComponent(p.game)}"` : ''}>${artHTML(p.game)}`
      + `<div style="min-width:0"><div class="pred-top"><span class="pred-name" title="${esc(p.game)}">${esc(p.game)}</span><span class="pred-pct">${pctText(p.p)}</span></div>`
      + `<div class="meter"><i style="width:${Math.max(2, p.p * 100).toFixed(1)}%;animation-delay:${i * 60}ms"></i></div>`
      + `<ul>${p.why.map(w => `<li title="${esc(w)}">${esc(w)}</li>`).join('')}</ul></div></${tag}>`;
  }).join('');
  const bt = r.backtest;
  const proof = bt ? `<div class="proof">`
    + `<div><b>${pctText(bt.top1.model)}</b><span>of weeks, its top guess was a game you then played</span><small>Guessing the last game you played: ${pctText(bt.top1.recent)}</small></div>`
    + `<div><b>${pctText(bt.top3.model)}</b><span>of weeks, one of its top 3 was right</span><small>Your last 3 games: ${pctText(bt.top3.recent)}</small></div>`
    + `<div><b>${pctText(Math.max(0, bt.skill))}</b><span>more accurate chances than a flat guess</span><small>Brier skill score</small></div>`
    + `</div><p class="model-note">Tested on your ${bt.weeks} weeks with clips since ${fmtDayNo(isoDay(bt.from))}, with a version of the model that hadn’t seen them.</p>` : '';
  const quiet = r.quiet >= 14 ? `<p class="model-note">You haven’t saved a clip for ${r.quiet} days, so every chance is low until you’re back.</p>` : '';
  const maxW = Math.max(...r.weights.map(w => Math.abs(w.weight)), 0.01);
  const how = `<details class="how"><summary>How it works</summary><p>Each day with a clip of a game counts as a day you played it. For every game and every past day, a small `
    + `logistic-regression model learned how your recent habits relate to whether you played the game again within the next ${r.horizon} days, from `
    + `${r.trainedOn.rows.toLocaleString()} examples across your ${r.trainedOn.games} games. It looks at two things:</p>`
    + r.weights.map(w => `<div class="wrow"><span>${esc(w.label)}</span><div class="meter"><i style="width:${(Math.abs(w.weight) / maxW * 100).toFixed(0)}%"></i></div><em>${w.weight > 0 ? 'more likely' : 'less likely'}</em></div>`).join('')
    + `<p>Adding more inputs (like your usual gap between sessions) didn’t make it better on your own history, so it stays simple. It can’t foresee games you’ve never played.</p></details>`;
  body.innerHTML = `<div class="preds">${cards}</div>${quiet}${proof}${how}`;
}

// ---------- settings ----------
let setInfo = null, setDirty = false, setBusy = false;
async function loadSettings() {
  try { setInfo = await getJSON('/api/settings'); } catch (e) { toast(e.message, true); return; }
  if (state.view === 'settings') renderSettings(true);
}
const toggle = (id, on, disabled, label) => `<label class="switch" title="${esc(label)}"><input type="checkbox" id="${id}"${on ? ' checked' : ''}${disabled ? ' disabled' : ''} aria-label="${esc(label)}"><i></i></label>`;
const plural = (n, one, many) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
function renderSettings(fetched) {
  const body = $('setBody');
  if (!fetched) loadSettings().then(() => {});  // counts and suggestions change, so always get fresh ones
  if (!setInfo) { body.innerHTML = '<p class="empty">Loading…</p>'; return; }
  const s = setInfo, gg = s.gg;
  $('setTotal').textContent = `${plural(s.total, 'clip', 'clips')} in your library`;
  const ggOn = gg.enabled && gg.installed;
  const ggSub = !gg.installed ? 'Not installed on this PC'
    : !gg.enabled ? 'Turned off: GG’s clips are hidden here (nothing in GG changes)'
    : gg.error ? `Couldn’t read GG’s library: ${esc(gg.error)}`
    : plural(gg.clips, 'clip', 'clips') + (gg.folder ? ` in <span class="mono">${esc(gg.folder)}</span>` : '');
  const opts = cur => s.recorders.map(([k, v]) => `<option value="${k}"${k === cur ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const folders = s.folders.map((f, i) => `<div class="srow${f.exists ? '' : ' off'}" data-i="${i}"><span class="sic">${ic('folder')}</span>`
    + `<div class="stxt"><span class="mono" title="${esc(f.path)}">${esc(f.path)}</span><span class="sub${f.exists ? '' : ' bad'}">`
    + (!f.exists ? 'Can’t find this folder right now (an unplugged drive?)' : f.clips == null ? 'Not read yet' : plural(f.clips, 'clip', 'clips')) + '</span></div>'
    + `<select class="select" data-act="recorder" aria-label="Which recorder made these clips">${opts(f.recorder)}</select>`
    + `<button class="icon-btn sm" type="button" data-act="remove" title="Stop showing clips from this folder (the files stay where they are)">${ic('trash')}</button></div>`).join('');
  const sugg = s.suggestions.length ? `<div class="sugg"><h4>Found on this PC</h4>` + s.suggestions.map((g, i) => `<div class="srow" data-s="${i}"><span class="sic">${ic('folder')}</span>`
    + `<div class="stxt"><b>${esc(g.label)}</b><span class="mono" title="${esc(g.path)}">${esc(g.path)}</span><span class="sub">${g.videos >= 500 ? '500+ videos' : plural(g.videos, 'video', 'videos')}</span></div>`
    + `<button class="btn sm" type="button" data-act="suggest">${ic('plus')} Add</button></div>`).join('') + '</div>' : '';
  const scan = s.scan && s.scan.pending ? ` · reading ${plural(s.scan.pending, 'new file', 'new files')}…` : '';
  body.innerHTML = (setDirty ? `<div class="setdone">${ic('check')}<span>Saved. Your library now has ${plural(s.total, 'clip', 'clips')}${scan}.</span><a class="btn primary sm" href="#/">Show my clips</a></div>` : '')
    + `<section class="sblock"><h3>Clip sources</h3><p class="hint">ClipShelf shows clips from SteelSeries GG and from any folders you add. Your files are never moved or changed.</p>`
    + `<div class="srow${ggOn ? '' : ' off'}"><span class="sic">${ic('pad')}</span><div class="stxt"><b>SteelSeries GG</b><span class="sub${gg.error && ggOn ? ' bad' : ''}">${ggSub}</span></div>${toggle('setGG', ggOn, !gg.installed, 'Show clips from SteelSeries GG')}</div>`
    + folders
    + `<div class="addrow"><button class="btn primary" type="button" data-act="pick">${ic('plus')} Add a folder…</button>`
    + `<form class="addrow" id="setAddForm" style="margin:0;flex:1"><input class="input" id="setAddPath" placeholder="or paste a folder’s path, like D:\\Clips" autocomplete="off" spellcheck="false"><button class="btn" type="submit">Add</button></form></div>`
    + sugg + '</section>'
    + `<section class="sblock"><h3>Saving edits</h3><p class="hint">Edited copies and compressed 18 MB copies are saved here${s.exportDir.custom ? '' : ' (by default, “Edited Clips” in your first clips folder)'}.</p>`
    + `<div class="srow"><span class="sic">${ic('save')}</span><div class="stxt"><span class="mono" title="${esc(s.exportDir.path)}">${esc(s.exportDir.path)}</span></div>`
    + `<button class="btn sm" type="button" data-act="export-pick">Change…</button>${s.exportDir.custom ? '<button class="btn sm" type="button" data-act="export-default">Use default</button>' : ''}`
    + `<button class="btn sm" type="button" data-act="open-export">${ic('folder')} Open</button></div></section>`
    + `<section class="sblock"><h3>Start with Windows</h3><div class="srow"><span class="sic">${ic('power')}</span><div class="stxt"><b>Run ClipShelf in the background</b>`
    + `<span class="sub">${s.autostart.supported ? `Starts when you sign in, so your clips are always at <span class="mono">http://127.0.0.1:${s.port}</span>. No window, and it does almost nothing while you’re not using it.` : 'Only available on Windows.'}</span></div>`
    + `${toggle('setAuto', s.autostart.enabled, !s.autostart.supported, 'Start with Windows')}</div></section>`
    + `<section class="sblock"><h3>About</h3><div class="kv">`
    + `<span>ffmpeg</span><span class="mono" title="${esc(s.ffmpeg || '')}">${s.ffmpeg ? esc(s.ffmpeg) : 'Not found: Chat/Mic audio, thumbnails for folder clips and saving copies are off'}</span><span></span>`
    + `<span>Your data</span><span class="mono" title="${esc(s.dataDir)}">${esc(s.dataDir)}</span><button class="btn sm" type="button" data-act="open-data">${ic('folder')} Open</button>`
    + `<span>Cover pictures</span><span class="mono" title="${esc(s.coversDir)}">${esc(s.coversDir)}</span><button class="btn sm" type="button" data-act="open-covers">${ic('folder')} Open</button>`
    + `<span>Version</span><span>ClipShelf ${esc(s.appVersion)}</span><button class="btn sm" type="button" data-act="rescan">${ic('refresh')} Look for new clips</button>`
    + '</div></section>';
}
const setFolders = () => setInfo.folders.map(f => ({path: f.path, recorder: f.recorder, enabled: f.enabled}));
async function saveSettings(patch, msg) {
  if (setBusy) return;
  setBusy = true;
  $('setBody').classList.add('busy');
  try {
    setInfo = await post('/api/settings', patch);
    setDirty = true;
    toast(msg || 'Saved');
  } catch (err) { toast(err.message, true); }
  setBusy = false;
  $('setBody').classList.remove('busy');
  if (state.view === 'settings') renderSettings(true);
}
function addFolder(path, recorder) {
  const folders = setFolders();
  folders.push({path, recorder: recorder || 'auto'});
  saveSettings({folders}, 'Folder added');
}
async function pickFolder(initial) {
  toast('Pick a folder in the window that just opened (it may be behind your browser)');
  try { return (await post('/api/pick-folder', {initial: initial || ''})).path; }
  catch (err) { toast(err.message, true); return null; }
}
$('setBody').addEventListener('change', async e => {
  const t = e.target;
  if (t.id === 'setGG') return saveSettings({gg: {enabled: t.checked}}, t.checked ? 'Showing clips from SteelSeries GG' : 'GG’s clips are hidden');
  if (t.id === 'setAuto') {
    try {
      const r = await post('/api/autostart', {enabled: t.checked});
      setInfo.autostart.enabled = r.enabled;
      toast(r.enabled ? 'ClipShelf will start with Windows' : 'ClipShelf won’t start with Windows any more');
    } catch (err) { t.checked = !t.checked; toast(err.message, true); }
    return;
  }
  if (t.dataset.act === 'recorder') {
    const folders = setFolders();
    folders[+t.closest('[data-i]').dataset.i].recorder = t.value;
    saveSettings({folders}, 'Saved');
  }
});
$('setBody').addEventListener('click', async e => {
  const b = e.target.closest('button[data-act]');
  if (!b) return;
  const act = b.dataset.act;
  if (act === 'remove') {
    const folders = setFolders();
    folders.splice(+b.closest('[data-i]').dataset.i, 1);
    saveSettings({folders}, 'Folder removed (its files weren’t touched)');
  } else if (act === 'suggest') {
    const g = setInfo.suggestions[+b.closest('[data-s]').dataset.s];
    addFolder(g.path, g.recorder);
  } else if (act === 'pick') {
    const p = await pickFolder();
    if (p) addFolder(p);
  } else if (act === 'export-pick') {
    const p = await pickFolder(setInfo.exportDir.path);
    if (p) saveSettings({exportDir: p}, 'Edited copies will be saved there');
  } else if (act === 'export-default') {
    saveSettings({exportDir: ''}, 'Back to the default folder');
  } else if (act.startsWith('open-')) {
    post('/api/open', {what: act.slice(5)}).catch(err => toast(err.message, true));
  } else if (act === 'rescan') {
    b.disabled = true;
    try {
      const r = await post('/api/rescan', {});
      if (r.version !== META.version) setDirty = true;
      toast(`Done: ${plural(r.total, 'clip', 'clips')}`);
      await loadSettings();
    } catch (err) { toast(err.message, true); }
    b.disabled = false;
  }
});
$('setBody').addEventListener('submit', e => {
  if (e.target.id !== 'setAddForm') return;
  e.preventDefault();
  const p = $('setAddPath').value.trim().replace(/^"|"$/g, '');
  if (p) addFolder(p);
});

// ---------- player ----------
const vid = $('vid'), stage = $('stage'), tl = $('tl');
const E = {};
['tlSel', 'tlPlayed', 'hIn', 'hOut', 'tlHead', 'tlTip', 'tCur', 'tDur', 'tIn', 'tOut', 'tSel'].forEach(id => { E[id] = $(id); });
const MIN_SEL = 0.2;
let cur = null, navList = [], opener = null, sel = {a: 0, b: 0}, loop = false, lastT = 0, raf = 0, drag = null, masterMuted = false;
let mix = [], actx = null, master = null, vidGain = null, extras = [], syncTimer = 0, exJob = null, exNameTouched = false;
const dur = () => (isFinite(vid.duration) && vid.duration > 0 ? vid.duration : (cur && cur.full) || 1);

function openPlayer(id, from) {
  const c = byId.get(id);
  if (!c) return;
  stopPreview();
  if (cur) teardown(); else opener = document.activeElement;
  cur = c;
  if (from) navList = from;
  heroSync();
  $('player').hidden = false;
  document.body.classList.add('noscroll');
  fillInfo();
  sel = c.trimmed && c.end > c.start ? {a: c.start, b: c.end} : {a: 0, b: c.full || 0};
  lastT = sel.a;
  mix = buildMix(c);
  renderMixer();
  $('stageMsg').hidden = true;
  stage.classList.add('paused');
  vid.poster = c.thumb || '';
  vid.src = c.video;
  vid.addEventListener('loadedmetadata', () => {
    if (cur !== c) return;
    const d = dur();
    if (!c.full && isFinite(vid.duration)) {  // not read yet by ClipShelf: use what the video says
      c.full = vid.duration;
      if (!c.trimmed) { c.end = c.full; c.len = c.full; }
      fillInfo();
    }
    if (!(sel.b > 0) || sel.b > d) sel.b = d;
    if (sel.b - sel.a < MIN_SEL) sel = {a: 0, b: d};
    vid.playbackRate = +$('speed').value;
    seek(sel.a);
    drawTL();
    vid.play().catch(() => {});
  }, {once: true});
  setupAudio(c);
  exNameTouched = false;
  $('exName').value = c.nick || (c.custom ? c.title : '');
  $('exOverwrite').checked = true;  // edits to an edited clip overwrite it unless you untick this
  if (!exJob) $('exProg').hidden = true;
  $('exGo').disabled = !!exJob;
  updateExport();
  updateNav();
  drawTL();
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(tick);
  $('shell').focus({preventScroll: true});
}
function fillInfo() {
  const c = cur;
  $('pIcon').style.setProperty('--h', hue(c.game));
  $('pIcon').textContent = initials(c.game);
  $('pGame').textContent = c.game;
  $('pDate').textContent = 'Recorded ' + fmtDate(c.recorded);
  $('pTitle').textContent = shownTitle(c);
  $('pTitle').className = 'ptitle' + (!c.custom && !c.nick ? ' auto' : '');
  const lines = [];
  if (c.edited) {
    const src = c.source && byId.get(c.source);
    lines.push('<span class="tag">Edited copy</span>', `<span>Length <b>${fmtLen(c.full)}</b> · ${fmtSize(c.size)} · saved ${fmtDate(c.made)}</span>`);
    if (src) lines.push(`<button class="btn sm" type="button" data-open-src="${src.id}">${ic('play')} Made from: ${esc(shownTitle(src))}</button>`);
  } else {
    if (c.nick) lines.push('<span class="tag nick">Nickname</span>');
    if (c.nick && (c.custom || c.src === 'gg')) lines.push(`<span>${titleWord(c)}: <b>${esc(c.title)}</b></span>`);
    lines.push(`<span>Length <b>${c.full ? fmtLen(c.full) : '…'}</b>` + (c.trimmed ? ` · ${trimWord(c).toLowerCase()} to <b>${fmtLen(c.len)}</b>` : '')
      + (c.starred ? ' · <span style="color:var(--star)">★ starred</span>' : '') + '</span>');
    lines.push(`<span>From <b>${esc(c.srcLabel)}</b></span>`);
  }
  $('pMeta').innerHTML = lines.join('');
  $('pFile').textContent = c.file;
  $('pFile').title = c.folder ? `${c.folder}\\${c.file}` : c.file;
  $('bRename').hidden = !!c.edited;  // an edited clip's name is its file name
  $('bStar').hidden = !!c.edited;
  $('bStar').innerHTML = ic('staro');
  $('bStar').classList.toggle('on', !!c.starred);
  $('bStar').disabled = !!c.ggStar;
  $('bStar').title = c.ggStar ? 'Starred in SteelSeries GG (unstar it there)' : c.starred ? 'Unstar (S)' : 'Star this clip (S)';
  $('gameForm').hidden = c.src !== 'folder';
  if (c.src === 'folder' && document.activeElement !== $('gameInput')) {
    $('gameInput').value = c.game === UNSORTED && !c.gameSet ? '' : c.game;
    $('gameList').innerHTML = [...GAMES].filter(g => g !== UNSORTED).sort((a, b) => a.localeCompare(b)).map(g => `<option value="${esc(g)}">`).join('');
  }
  $('trimGG').textContent = c.trimSrc === 'gg' || (c.src === 'gg' && !c.trimmed) ? 'GG’s trim' : 'Saved trim';
  $('trimGG').disabled = !c.trimmed;
  $('trimSave').hidden = !!c.edited;
  $('trimHint').textContent = c.edited || !c.trimmed ? '' : c.trimSrc === 'gg' ? 'GG’s trim plays in previews' : 'your trim plays in previews';
  endRename();
}
function teardown() {
  vid.pause();
  for (const x of extras) {
    x.el.pause(); x.el.removeAttribute('src'); x.el.load();
    try { x.node.disconnect(); x.gain.disconnect(); } catch (e) {}
  }
  extras = [];
  clearInterval(syncTimer); syncTimer = 0;
  vid.removeAttribute('src'); vid.load();
}
function closePlayer() {
  if (!cur) return;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  teardown();
  cur = null;
  cancelAnimationFrame(raf);
  $('player').hidden = true;
  document.body.classList.remove('noscroll');
  if (opener && opener.focus) opener.focus({preventScroll: true});
  heroSync();
}
// Opening grows the clip's thumbnail into the player; closing shrinks it back into its card.
let flyBack = null, closing = false;
function openClip(id, from, sourceEl) {
  flyBack = sourceEl || null;
  if (cur || !sourceEl || !canAnimate()) { openPlayer(id, from); return; }
  sourceEl.style.viewTransitionName = 'clip-media';
  $('player').classList.add('morph');
  vt('open', () => {
    sourceEl.style.viewTransitionName = '';
    openPlayer(id, from);
    stage.style.viewTransitionName = 'clip-media';
  }).then(() => { stage.style.viewTransitionName = ''; $('player').classList.remove('morph'); });
}
function inView(el) { const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.width > 0; }
function closeClip() {
  if (!cur || closing) return;
  let target = flyBack;
  const card = target && target.closest('.card');
  if (card && card.dataset.id !== cur.id) target = card.closest('.grid').querySelector(`.card[data-id="${cur.id}"] .thumb`);  // moved on with Prev/Next
  if (target && (!target.isConnected || !inView(target))) target = null;
  if (canAnimate()) {
    stage.style.viewTransitionName = 'clip-media';
    vt('close', () => {
      stage.style.viewTransitionName = '';
      closePlayer();
      if (target) target.style.viewTransitionName = 'clip-media';
    }).then(() => { if (target) target.style.viewTransitionName = ''; });
  } else if (!reduceMotion.matches) {
    closing = true;
    $('player').classList.add('closing');
    setTimeout(() => { closing = false; $('player').classList.remove('closing'); closePlayer(); }, 160);
  } else closePlayer();
}
document.querySelectorAll('[data-close]').forEach(el => { el.onclick = closeClip; });

// Audio mixer. The video element plays the first track (Game); the other tracks (Chat, Mic) are pulled out
// of the clip by ClipShelf and played alongside it in sync, each with its own volume (up to 200%).
// GG clips always list Game, Chat and Mic; a track GG didn't record for that clip is shown as such.
const STD = ['game', 'chat', 'mic'];
function buildMix(c) {
  const rows = c.tracks.map((t, i) => ({name: t.name, vol: Math.round(clamp((t.volume ?? 1) * 100, 0, 200)), muted: !!t.muted, stream: i, state: i === 0 ? 'ok' : AUDIO ? 'wait' : 'off'}));
  if (c.src !== 'gg') return rows;  // saved copies have one mixed track; folder clips have whatever was recorded
  for (const name of ['Chat', 'Mic']) {
    if (!rows.some(r => r.name.toLowerCase() === name.toLowerCase())) rows.push({name, vol: 100, muted: false, stream: -1, state: 'missing'});
  }
  const rank = r => { const k = STD.indexOf(r.name.toLowerCase()); return k < 0 ? 9 : k; };
  return rows.sort((a, b) => rank(a) - rank(b) || a.stream - b.stream);
}
function ensureGraph() {
  if (!actx) {
    try {
      actx = new AudioContext();
      master = actx.createGain(); master.connect(actx.destination);
      vidGain = actx.createGain(); vidGain.connect(master);
      actx.createMediaElementSource(vid).connect(vidGain);
    } catch (e) { actx = null; return false; }
  }
  if (actx.state === 'suspended') actx.resume().catch(() => {});
  return true;
}
function setupAudio(c) {
  const graph = ensureGraph();
  updateMixHint();
  applyGains();
  if (!graph || !AUDIO) return;
  for (const row of mix) {
    if (row.stream < 1) continue;
    const el = new Audio();
    el.preload = 'auto';
    const node = actx.createMediaElementSource(el), gain = actx.createGain();
    node.connect(gain).connect(master);
    extras.push({el, node, gain, stream: row.stream});
    el.addEventListener('canplay', () => { if (cur !== c) return; row.state = 'ok'; updateTrack(row); applyGains(); syncTracks(vid, extras.map(x => x.el), true); }, {once: true});
    el.addEventListener('error', () => { if (cur !== c) return; row.state = 'error'; updateTrack(row); }, {once: true});
    el.src = trackUrl(c, row.stream);
  }
  applyGains();
  syncTimer = setInterval(() => syncTracks(vid, extras.map(x => x.el), false), 250);
}
['seeked', 'play', 'playing'].forEach(ev => vid.addEventListener(ev, () => syncTracks(vid, extras.map(x => x.el), true)));
['pause', 'waiting', 'seeking', 'ratechange'].forEach(ev => vid.addEventListener(ev, () => syncTracks(vid, extras.map(x => x.el), false)));
const gainOf = m => (m && !m.muted && m.stream >= 0 ? m.vol / 100 : 0);
const rowFor = stream => mix.find(r => r.stream === stream);
function applyGains() {
  if (actx) {
    vidGain.gain.value = gainOf(rowFor(0));
    for (const x of extras) x.gain.gain.value = gainOf(rowFor(x.stream));
    master.gain.value = masterMuted ? 0 : 1;
  } else {
    vid.volume = Math.min(1, gainOf(rowFor(0)));
    vid.muted = masterMuted;
  }
  $('bMute').innerHTML = ic(masterMuted ? 'mute' : 'vol');
  $('bMute').classList.toggle('on', masterMuted);
}
const TICON = {game: 'pad', chat: 'chat', mic: 'mic'};
const NOTE = {wait: 'loading…', missing: 'not recorded in this clip', error: 'couldn’t load', off: 'needs ffmpeg'};
function trackHTML(m, i) {
  const off = m.state === 'missing' || m.state === 'off' || m.state === 'error';
  const note = NOTE[m.state] || '';
  return `<div class="track${off ? ' off' : ''}" data-i="${i}">`
    + `<button class="mute-btn${m.muted && !off ? ' on' : ''}" data-act="mute" title="${m.muted ? 'Unmute' : 'Mute'} ${esc(m.name)}"${off ? ' disabled' : ''}>${ic(m.muted && !off ? 'mute' : TICON[m.name.toLowerCase()] || 'vol')}</button>`
    + `<div><div class="tname">${esc(m.name)}${note ? `<span class="dim">${note}</span>` : ''}</div>`
    + `<input type="range" min="0" max="200" step="1" value="${off ? 0 : m.vol}" aria-label="${esc(m.name)} volume"${off ? ' disabled' : ''}></div>`
    + `<span class="val">${off ? '—' : m.vol + '%'}</span></div>`;
}
function renderMixer() {
  $('mixer').innerHTML = mix.length ? mix.map(trackHTML).join('') : '<p class="note">This clip has no sound.</p>';
}
function updateTrack(row) {
  const i = mix.indexOf(row), el = $('mixer').querySelector(`[data-i="${i}"]`);
  if (!el) return;
  if (row.state === 'ok' && el.contains(document.activeElement)) { el.classList.remove('off'); const n = el.querySelector('.tname .dim'); if (n) n.remove(); return; }
  el.outerHTML = trackHTML(row, i);
}
$('mixer').addEventListener('input', e => {
  if (e.target.type !== 'range') return;
  const el = e.target.closest('.track'), m = mix[+el.dataset.i];
  m.vol = +e.target.value;
  el.querySelector('.val').textContent = m.vol + '%';
  applyGains();
  rememberMix(m);
});
$('mixer').addEventListener('click', e => {
  const b = e.target.closest('[data-act="mute"]'); if (!b) return;
  const m = mix[+b.closest('.track').dataset.i];
  m.muted = !m.muted;
  updateTrack(m); applyGains();
  rememberMix(m);
});
// Levels are remembered per clip (like GG does), and also used by hover previews and the home page.
let mixTimer = 0;
const isCustomMix = c => c.tracks.some(t => Math.abs(t.volume - (t.baseVolume ?? t.volume)) > 0.005 || t.muted !== (t.baseMuted ?? t.muted));
function updateMixHint() {
  const custom = cur && !cur.edited && isCustomMix(cur);
  $('mixHint').textContent = cur && cur.edited ? 'Game, Chat & Mic are mixed in this copy'
    : !META.ffmpeg && cur && cur.tracks.length > 1 ? 'Extra tracks need ffmpeg'
    : custom ? 'your levels for this clip' : cur && cur.src === 'gg' ? 'GG’s levels' : 'as recorded';
  $('mixReset').hidden = !custom;
  $('mixReset').textContent = cur && cur.src === 'gg' ? 'Reset to GG levels' : 'Reset levels';
}
function rememberMix(m) {
  if (!cur || m.stream < 0 || cur.edited) return;
  const c = cur, t = c.tracks[m.stream];
  if (!t) return;
  t.volume = m.vol / 100;
  t.muted = m.muted;
  updateMixHint();
  clearTimeout(mixTimer);
  mixTimer = setTimeout(() => {
    post('/api/mix', {id: c.id, tracks: c.tracks.map((x, i) => ({stream: i, vol: x.volume, muted: x.muted}))})
      .catch(err => toast('Couldn’t save the audio levels: ' + err.message, true));
  }, 500);
}
$('mixReset').onclick = () => {
  if (!cur) return;
  for (const t of cur.tracks) { t.volume = t.baseVolume ?? t.volume; t.muted = t.baseMuted ?? t.muted; }
  for (const m of mix) {
    const t = cur.tracks[m.stream];
    if (t) { m.vol = Math.round(clamp(t.volume * 100, 0, 200)); m.muted = t.muted; }
  }
  renderMixer(); applyGains();
  const first = mix.find(m => m.stream >= 0);
  if (first) rememberMix(first);  // saves the whole clip's levels, which are now the recorded ones again
  toast(cur.src === 'gg' ? 'Back to GG’s levels' : 'Back to the recorded levels');
};

// Timeline and playback
const pct = t => clamp(t / dur(), 0, 1) * 100 + '%';
function drawTL() {
  if (!cur) return;
  const t = vid.currentTime;
  E.tlSel.style.left = pct(sel.a);
  E.tlSel.style.width = clamp((sel.b - sel.a) / dur(), 0, 1) * 100 + '%';
  E.hIn.style.left = pct(sel.a);
  E.hOut.style.left = pct(sel.b);
  E.tlHead.style.left = pct(t);
  E.tlPlayed.style.width = pct(t);
  E.tCur.textContent = fmtLen(t);
  E.tDur.textContent = fmtLen(dur());
  E.tIn.textContent = fmtExact(sel.a);
  E.tOut.textContent = fmtExact(sel.b);
  E.tSel.textContent = fmtExact(sel.b - sel.a);
}
function seek(t) { t = clamp(t, 0, dur()); vid.currentTime = t; lastT = t; }
function tick() {
  if (!cur) return;
  const t = vid.currentTime;
  if (!vid.paused && !drag && lastT < sel.b - 0.01 && t >= sel.b) {
    if (loop) seek(sel.a); else { vid.pause(); seek(sel.b); }
  } else lastT = t;
  drawTL();
  raf = requestAnimationFrame(tick);
}
function togglePlay() {
  if (!cur) return;
  if (vid.paused) {
    if (vid.currentTime >= sel.b - 0.05) seek(sel.a);
    ensureGraph();
    vid.play().catch(() => {});
  } else vid.pause();
}
function toggleMute() { masterMuted = !masterMuted; applyGains(); }
function toggleFull() { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); else $('pmain').requestFullscreen().catch(() => {}); }
function setIn() { const t = vid.currentTime; if (t > sel.b - MIN_SEL) sel.b = dur(); sel.a = clamp(t, 0, sel.b - MIN_SEL); drawTL(); }
function setOut() { const t = vid.currentTime; if (t < sel.a + MIN_SEL) sel.a = 0; sel.b = clamp(t, sel.a + MIN_SEL, dur()); drawTL(); }
vid.addEventListener('play', () => { stage.classList.remove('paused'); $('bPlay').innerHTML = ic('pause'); });
vid.addEventListener('pause', () => { stage.classList.add('paused'); $('bPlay').innerHTML = ic('play'); });
vid.addEventListener('ended', () => { if (loop && cur) { seek(sel.a); vid.play().catch(() => {}); } });
// Spinner while the video loads (only shows if that takes more than a moment)
['loadstart', 'waiting', 'seeking'].forEach(ev => vid.addEventListener(ev, () => { if (vid.getAttribute('src')) stage.classList.add('loading'); }));
['playing', 'canplay', 'seeked', 'pause', 'error', 'emptied'].forEach(ev => vid.addEventListener(ev, () => stage.classList.remove('loading')));
vid.addEventListener('error', () => {
  if (!cur || !vid.getAttribute('src')) return;
  const code = vid.error && vid.error.code;
  $('stageMsg').textContent = code === 4 ? 'Your browser can’t play this clip’s video format (for example HEVC in Firefox). Try Chrome or Edge.'
    : 'This clip can’t be played. The file may have been moved or deleted.';
  $('stageMsg').hidden = false;
});
$('bPlay').innerHTML = ic('play');
$('bPlay').onclick = togglePlay;
stage.onclick = togglePlay;
stage.ondblclick = toggleFull;
$('bBack').onclick = () => seek(vid.currentTime - 5);
$('bFwd').onclick = () => seek(vid.currentTime + 5);
$('bLoop').onclick = () => { loop = !loop; $('bLoop').classList.toggle('on', loop); };
$('speed').onchange = () => { vid.playbackRate = +$('speed').value; };
$('bMute').onclick = toggleMute;
$('bFull').onclick = toggleFull;
$('setIn').onclick = setIn;
$('setOut').onclick = setOut;
$('trimFull').onclick = () => { sel = {a: 0, b: dur()}; drawTL(); };
$('trimGG').onclick = () => { if (cur && cur.trimmed) { sel = {a: cur.start, b: Math.min(cur.end, dur())}; seek(sel.a); drawTL(); } };
// Keep the selection as the clip's trim: previews and the home page then play just that part
$('trimSave').onclick = async () => {
  const c = cur;
  if (!c || c.edited) return;
  try {
    const r = await post('/api/trim', {id: c.id, start: sel.a, end: sel.b});
    Object.assign(c, r);
    c.len = c.trimmed ? c.end - c.start : c.full;
    refreshCard(c);
    if (cur === c) fillInfo();
    toast(!c.trimmed ? 'Trim removed: previews play the whole clip' : c.trimSrc === 'gg' ? 'Back to GG’s trim' : 'Trim kept: previews play just this part');
  } catch (err) { toast(err.message, true); }
};

const xToTime = x => { const r = tl.getBoundingClientRect(); return clamp((x - r.left) / r.width, 0, 1) * dur(); };
function dragMove(e) {
  const t = xToTime(e.clientX);
  if (drag === 'seek') seek(t);
  else if (drag === 'a') { sel.a = clamp(t, 0, sel.b - MIN_SEL); seek(sel.a); }
  else { sel.b = clamp(t, sel.a + MIN_SEL, dur()); seek(sel.b); }
  drawTL();
}
tl.addEventListener('pointerdown', e => {
  if (!cur || e.button !== 0) return;
  e.preventDefault();
  tl.setPointerCapture(e.pointerId);
  drag = e.target === E.hIn ? 'a' : e.target === E.hOut ? 'b' : 'seek';
  if (drag !== 'seek') vid.pause();
  dragMove(e);
});
tl.addEventListener('pointermove', e => {
  const r = tl.getBoundingClientRect();
  E.tlTip.style.left = clamp(e.clientX - r.left, 20, r.width - 20) + 'px';
  E.tlTip.textContent = fmtExact(xToTime(e.clientX));
  if (drag) dragMove(e);
});
const endDrag = () => { drag = null; };
tl.addEventListener('pointerup', endDrag);
tl.addEventListener('pointercancel', endDrag);

function neighbor(d) { const i = navList.indexOf(cur); return i < 0 ? null : navList[i + d] || null; }
function updateNav() { $('bPrev').disabled = !neighbor(-1); $('bNext').disabled = !neighbor(1); }
function step(d) {
  const n = neighbor(d);
  if (!n) return;
  if (!canAnimate()) { openPlayer(n.id); return; }
  stage.style.viewTransitionName = 'clip-media';
  vt(d > 0 ? 'next' : 'prev', () => openPlayer(n.id)).then(() => { stage.style.viewTransitionName = ''; });
}
$('bPrev').onclick = () => step(-1);
$('bNext').onclick = () => step(1);

// Star (ClipShelf's own; clips starred in GG stay starred)
async function toggleStar() {
  const c = cur;
  if (!c || c.edited || c.ggStar) return;
  try {
    const r = await post('/api/favorite', {id: c.id, on: !c.fav});
    Object.assign(c, r);
    refreshCard(c);
    if (cur === c) fillInfo();
    toast(c.fav ? 'Starred' : 'Star removed');
  } catch (err) { toast(err.message, true); }
}
$('bStar').onclick = toggleStar;

// Which game a clip from a folder belongs to
$('gameForm').onsubmit = async e => {
  e.preventDefault();
  const c = cur;
  if (!c || c.src !== 'folder') return;
  try {
    const r = await post('/api/game', {id: c.id, game: $('gameInput').value});
    const moved = r.game !== c.game;
    c.game = r.game; c.gameSet = r.gameSet;
    GAMES.add(c.game);
    indexClip(c);
    $('gameInput').blur();
    if (cur === c) fillInfo();
    refreshCard(c);
    toast(moved ? `Moved to ${c.game}` : 'Saved');
    $('shell').focus({preventScroll: true});
  } catch (err) { toast(err.message, true); }
};

// Nickname
function startRename() {
  if (!cur || cur.edited) return;
  $('titleView').hidden = true;
  $('renameForm').hidden = false;
  const inp = $('renameInput');
  inp.value = cur.nick || '';
  inp.placeholder = cur.custom ? cur.title : 'Give this clip a nickname';
  inp.focus(); inp.select();
}
function endRename() { $('titleView').hidden = false; $('renameForm').hidden = true; }
$('bRename').onclick = startRename;
$('renameCancel').onclick = endRename;
$('renameForm').onsubmit = async e => {
  e.preventDefault();
  const c = cur;
  try {
    const r = await post('/api/nickname', {id: c.id, nickname: $('renameInput').value});
    c.nick = r.nick || '';
    indexClip(c);
    if (r.change) { D.changes.push(r.change); renderLog(); }
    toast(c.nick ? 'Nickname saved' : 'Nickname removed');
    refreshCard(c);
    if (cur === c) {
      fillInfo();
      if (!exNameTouched) { $('exName').value = c.nick || (c.custom ? c.title : ''); updateExport(); }
      $('shell').focus({preventScroll: true});
    }
  } catch (err) { toast(err.message, true); }
};

// Save edited copy
function stemOf(f) { const b = f.replace(/\.[^.]+$/, ''); const m = /^(.+?__\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2})/.exec(b); return m ? m[1] : b; }
function safeName(s) { return s.replace(/[<>:"/\\|?*\x00-\x1f]/g, '').replace(/\s+/g, ' ').trim().replace(/^[ .]+|[ .]+$/g, '').slice(0, 100); }
const exportDirName = () => String(META.exportDir || 'Edited Clips').split(/[\\/]/).filter(Boolean).pop();
function updateExport() {
  $('exportBody').hidden = !AUDIO;
  $('exportNote').hidden = AUDIO;
  $('exportNote').textContent = 'Saving edited copies needs ffmpeg, which wasn’t found on this PC.';
  const small = exQuality === 'small', ed = !!(cur && cur.edited), over = ed && $('exOverwrite').checked;
  $('exOverRow').hidden = !ed;
  $('exTitle').textContent = ed ? 'Save changes' : 'Save edited copy';
  $('exGo').innerHTML = ic('save') + (over ? ' Save changes' : ' Save copy');
  $('exName').disabled = over;  // overwriting keeps the clip's name
  if (AUDIO && cur) {
    const tag = small ? ' (18MB)' : '', dir = exportDirName();
    if (over) {
      const target = cur.file.replace(/\.[^.]+$/, '').replace(/ \(18MB\)$/, '') + tag + '.mp4';
      $('exFile').textContent = target === cur.file ? `Overwrites ${dir}\\${cur.file}` : `Replaces ${cur.file} with ${target}`;
    } else {
      const name = safeName($('exName').value), base = cur.file.replace(/\.[^.]+$/, '').replace(/ \(18MB\)$/, '');
      const stem = !ed ? `${stemOf(cur.file)}__${name || 'edit'}` : name ? (cur.prefix ? `${cur.prefix}__${name}` : name) : `${base} (edit)`;
      $('exFile').textContent = `Saves to ${dir}\\${stem}${tag}.mp4`;
    }
  }
  $('exQuality').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.q === exQuality));
  $('exQNote').textContent = small
    ? 'Re-encoded to stay under 18 MB, so it’s easy to send (Discord and similar). Longer clips get a smaller picture.'
    : 'Same quality as the original recording.';
  $('exPreciseRow').hidden = small;  // compressed copies are always cut exactly
  placeInd($('exQuality'));
}
let exQuality = store.get('exq', 'original') === 'small' ? 'small' : 'original';
$('exQuality').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  exQuality = b.dataset.q; store.set('exq', exQuality);
  updateExport();
};
$('exName').addEventListener('input', () => { exNameTouched = true; updateExport(); });
$('exOverwrite').addEventListener('change', updateExport);
function setProg(p, html, err, actions = '') {
  $('exProg').hidden = false;
  $('exProg').classList.toggle('err', !!err);
  $('exBar').style.width = Math.round(p * 100) + '%';
  $('exText').innerHTML = html;
  $('exActions').innerHTML = actions;
}
$('exGo').onclick = async () => {
  if (!cur || exJob) return;
  $('exGo').disabled = true;
  setProg(0, 'Starting…');
  try {
    const r = await post('/api/export', {
      id: cur.id, start: sel.a, end: sel.b, precise: $('exPrecise').checked, loud: $('exLoud').checked, name: $('exName').value,
      quality: exQuality, volumes: cur.tracks.map((t, i) => gainOf(rowFor(i))),
      overwrite: !!(cur.edited && $('exOverwrite').checked),
    });
    exJob = r.job;
    pollJob(r.job);
  } catch (err) { setProg(0, esc(err.message), true); $('exGo').disabled = false; }
};
async function pollJob(job) {
  let misses = 0;
  for (;;) {
    await new Promise(r => setTimeout(r, 600));
    let j;
    try { j = await getJSON(`/api/job/${job}`); misses = 0; }
    catch (e) { if (++misses < 20) continue; j = {state: 'error', error: 'Lost contact with ClipShelf'}; }
    if (j.state === 'running') {
      setProg(j.progress || 0, `Saving… ${Math.round((j.progress || 0) * 100)}%` + (j.retry ? ' · making it a little smaller' : ''));
      continue;
    }
    exJob = null;
    $('exGo').disabled = false;
    if (j.state === 'done') {
      const done = () => setProg(1, `${ic('check')} ${j.overwrote ? 'Overwrote' : 'Saved'} <b>${esc(j.file)}</b>${j.size ? ` · ${fmtSize(j.size)}` : ''}`, false,
        `<button class="btn sm" type="button" data-reveal="${esc(j.file)}">${ic('folder')} Show in folder</button>`);
      done();
      toast(j.overwrote ? 'Changes saved' : 'Edited copy saved');
      const wasEdited = cur && cur.edited;
      await refreshEdited();
      if (j.overwrote && wasEdited && cur && cur.edited) {  // show the new version straight away
        const fresh = edits.find(e => e.file === j.file);
        if (fresh) { openPlayer(fresh.id, state.view === 'edited' ? edList : edits); done(); }
      }
    } else setProg(0, esc(j.error || 'Saving failed'), true);
    return;
  }
}
document.addEventListener('click', async e => {
  const place = e.target.closest('[data-open-place]');
  if (place) { post('/api/open', {what: place.dataset.openPlace}).catch(err => toast(err.message, true)); return; }
  const src = e.target.closest('[data-open-src]');
  if (src) { const c = byId.get(src.dataset.openSrc); if (c) openPlayer(c.id, [c]); return; }
  const b = e.target.closest('[data-reveal]'); if (!b) return;
  try { await post('/api/reveal', {file: b.dataset.reveal}); } catch (err) { toast(err.message, true); }
});
$('bReveal').onclick = async () => { try { await post('/api/reveal', {id: cur.id}); } catch (err) { toast(err.message, true); } };

// Keyboard
document.addEventListener('keydown', e => {
  const tag = e.target.tagName, type = e.target.type;
  const typing = tag === 'TEXTAREA' || (tag === 'INPUT' && type !== 'range' && type !== 'checkbox');
  if (!cur) {
    if (e.key === '/' && !typing) { e.preventDefault(); $('q').focus(); }
    return;
  }
  if (typing) {
    if (e.key === 'Escape') { e.preventDefault(); if (!$('renameForm').hidden) endRename(); $('shell').focus({preventScroll: true}); }
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if ((type === 'range' || tag === 'SELECT') && e.key.startsWith('Arrow')) return;
  if (tag === 'BUTTON' && (e.key === ' ' || e.key === 'Enter')) return;
  const actions = {
    ' ': togglePlay, k: togglePlay,
    arrowleft: () => seek(vid.currentTime - (e.shiftKey ? 1 : 5)),
    arrowright: () => seek(vid.currentTime + (e.shiftKey ? 1 : 5)),
    j: () => seek(vid.currentTime - 10), l: () => seek(vid.currentTime + 10),
    ',': () => { vid.pause(); seek(vid.currentTime - 1 / 30); },
    '.': () => { vid.pause(); seek(vid.currentTime + 1 / 30); },
    i: setIn, o: setOut, home: () => seek(sel.a), end: () => seek(sel.b),
    f: toggleFull, m: toggleMute, r: startRename, s: toggleStar,
    n: () => step(1), pagedown: () => step(1), p: () => step(-1), pageup: () => step(-1),
    escape: () => { if (!document.fullscreenElement) closeClip(); },
  };
  const act = actions[e.key.toLowerCase()];
  if (act) { e.preventDefault(); act(); }
});

// ---------- start ----------
$('sort').value = SORTS[state.sort] ? state.sort : 'new';
syncFilterButtons();
setThemeIcon();
renderLog();
buildHero();
route(true);
})();
