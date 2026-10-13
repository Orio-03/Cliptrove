// Browser test: clicks through Cliptrove in headless Chrome like a new user would, and fails on any page error.
//
//   node tests/e2e/e2e.mjs <cliptrove url> <clips folder> <screenshot folder>
//
// Cliptrove must be running with an empty data folder (so the first-start setup shows).
import { mkdirSync, writeFileSync } from 'node:fs';
import { launch, sleep } from './browser.mjs';

const [base, clipsDir, shotsDir] = process.argv.slice(2);
mkdirSync(shotsDir, { recursive: true });
const b = await launch();
const results = [];
let step = 0;

async function check(name, fn) {
  step++;
  try {
    await fn();
    results.push(`ok    ${name}`);
  } catch (err) {
    results.push(`FAIL  ${name}: ${err.message}`);
  }
  writeFileSync(`${shotsDir}/${String(step).padStart(2, '0')}-${name.replace(/\W+/g, '-')}.png`, await b.shot());
}
const js = s => b.evaluate(s);
async function until(what, expr, ms = 15000) {
  for (let t = 0; t < ms; t += 250) {
    if (await js(expr)) return;
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${what}`);
}
const text = sel => b.call(s => (document.querySelector(s) || {}).innerText || '', sel);
const click = sel => b.call(s => {
  const e = document.querySelector(s);
  if (!e) throw new Error('missing ' + s);
  e.click();
  return true;
}, sel);
const lastToast = () => text('#toast');

await b.go(base, 3000);

await check('first start shows the setup', async () => {
  await until('the setup', `!document.getElementById('setup').hidden && !!document.querySelector('.app[data-app="other"]')`);
});

await check('setup with a clips folder', async () => {
  // Only "Something else" (a plain folder), whatever else this PC has
  // (each click redraws the list, so look the ticked ones up again every time)
  await js(`(() => { for (let i = 0; i < 20; i++) { const on = document.querySelector('.app.on'); if (!on) break; on.click(); } return true; })()`);
  if (await js(`document.querySelectorAll('.app.on').length`)) throw new Error("couldn't untick the apps found on this PC");
  await click('.app[data-app="other"]');
  await click('#setupNext');
  await until('the folder step', `!!document.querySelector('.where[data-app="other"] input')`);
  await b.call(folder => {
    const i = document.querySelector('.where[data-app="other"] input');
    i.value = folder;
    i.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }, clipsDir);
  await click('#setupNext');
  await until('the last step', `document.getElementById('setupNext').textContent === 'Finish'`);
  await click('#setupNext');
  await until('setup to finish and the page to reload', `document.getElementById('setup').hidden`, 30000);
  await until('the library', `document.querySelectorAll('#tiles a.tile').length === 4`, 30000);  // 3 games + All games
});

await check('setup does not come back', async () => {
  await b.go(base, 3000);
  if (!(await js(`document.getElementById('setup').hidden`))) throw new Error('setup showed again');
});

await check('a game page lists its clips', async () => {
  await click('a.tile[href="#/game/Neon%20Drift"]');
  await until('clip cards', `document.querySelectorAll('#grid .card').length === 6`);
});

await check('the player plays a clip', async () => {
  await click('#grid .card .thumb');
  await until('the player', `!document.getElementById('player').hidden`);
  await until('the video', `document.getElementById('vid').readyState >= 2`, 20000);
  await until('the Mic track', `document.querySelectorAll('#mixer .track').length === 2`);
  if (await js(`!document.getElementById('stageMsg').hidden`)) throw new Error(await text('#stageMsg'));
});

await check('nickname and star', async () => {
  await click('#bRename');
  await js(`(() => { const i = document.getElementById('renameInput'); i.value = 'E2E clutch'; return true; })()`);
  await js(`document.getElementById('renameForm').requestSubmit()`);
  await until('the nickname', `document.getElementById('pTitle').textContent === 'E2E clutch'`);
  await click('#bStar');
  await until('the star', `document.getElementById('bStar').classList.contains('on')`);
});

await check('closing the player', async () => {
  await js(`document.querySelector('[data-close]').click()`);
  await until('the player to close', `document.getElementById('player').hidden`);
});

await check('a wrong folder in Settings is explained', async () => {
  await b.go(base + '#/settings', 3000);
  await until('the settings', `!!document.getElementById('setAddForm')`);
  await js(`(() => { document.getElementById('setAddPath').value = '/no/such/folder'; document.getElementById('setAddForm').requestSubmit(); return true; })()`);
  await until('an error message', `document.getElementById('toast').innerText.includes("Can't find the folder")`);
});

await check('analytics draws its charts', async () => {
  await b.go(base + '#/analytics', 3000);
  await js(`document.querySelector('#stRange [data-r="all"]').click()`);
  await until('chart bars', `document.querySelectorAll('#stChart rect.s').length > 0`);
  await until('the Up next panel', `document.getElementById('stNextBody').innerText.length > 20`);
});

await check('the edited tab', async () => {
  await b.go(base + '#/edited', 2500);
  await until('the edited view', `!document.getElementById('editedView').hidden`);
});

await check('quit stops Cliptrove', async () => {
  await b.go(base + '#/settings', 3000);
  await until('the quit button', `!!document.querySelector('[data-act="quit"]')`);
  await click('[data-act="quit"]');  // the "are you sure?" dialog is accepted automatically
  await until('the stopped message', `document.getElementById('banner').innerText.includes('stopped')`);
  for (let t = 0; t < 5000; t += 250) {
    if (await fetch(base + 'api/ping').then(() => false, () => true)) return;
    await sleep(250);
  }
  throw new Error('still answering 5 seconds after quitting');
});

b.close();
const problems = b.problems.filter(p => !/fonts\.g|steamstatic|Failed to load resource/.test(p));
console.log(results.join('\n'));
if (problems.length) console.log('\nPage errors:\n' + problems.join('\n'));
const failed = results.some(r => r.startsWith('FAIL')) || problems.length > 0;
console.log(failed ? '\nBrowser test FAILED' : '\nBrowser test passed');
process.exit(failed ? 1 : 0);
