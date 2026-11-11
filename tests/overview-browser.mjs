import {chromium} from 'playwright';
import {existsSync} from 'node:fs';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = process.env.ARTIFACT_DIR || path.join(root, 'test-results/overview');
await mkdir(output, {recursive: true});
const layout = JSON.parse(await readFile(path.join(root, 'data/overview-layout.json'), 'utf8'));
const server = spawn('python3', ['-B', 'scripts/serve_public.py', '--port', '0'], {cwd: root, stdio: ['ignore', 'pipe', 'pipe']});
const baseURL = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Preview did not start')), 10000);
  server.once('exit', code => { clearTimeout(timer); reject(new Error(`Preview exited: ${code}`)); });
  server.stdout.on('data', data => {
    const match = data.toString().match(/http:\/\/127\.0\.0\.1:\d+\/pico-brake-mechanical-design\//);
    if (match) { clearTimeout(timer); resolve(match[0]); }
  });
}).catch(error => { server.kill('SIGTERM'); throw error; });
let browser;
const errors = [], warnings = [], failures = [], external = [];
const report = {status: 'RUNNING', scope: 'Reference enclosure/PCB overview; no physical approval or whole-machine CAD claim', checks: []};
const check = message => report.checks.push(message);
const ready = page => page.locator('html[data-overview-state="ready"]').waitFor({timeout: 60000});
const snapshot = page => page.evaluate(() => window.brakeOverview.snapshot());
function observe(page) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); if (message.type() === 'warning') warnings.push(message.text()); });
  page.on('requestfailed', request => failures.push(request.failure()?.errorText));
  page.on('response', response => { if (response.status() >= 400) failures.push(String(response.status())); });
  page.on('request', request => { if (!request.url().startsWith(new URL(baseURL).origin) && !request.url().startsWith('data:')) external.push(request.url()); });
}
try {
  const chrome = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  browser = await chromium.launch({headless: true, ...(existsSync(chrome) ? {executablePath: chrome} : {})});
  report.browser = await browser.version();
  const context = await browser.newContext({viewport: {width: 1440, height: 1100}, reducedMotion: 'reduce'});
  const page = await context.newPage(); observe(page);
  await page.goto(new URL('overview.html', baseURL).href);
  await ready(page);
  await page.locator('#overview-canvas[data-rendered="true"]').waitFor();
  let state = await snapshot(page);
  assert.equal(state.referenceItems, 72); assert.equal(state.brakeParts, 447);
  assert.ok(state.drawCalls > 0 && state.triangles > 0);
  assert.equal(state.autoRotate, false);
  assert.equal(await page.locator('audio,video').count(), 0);
  await page.screenshot({path: path.join(output, 'overview-desktop.png'), fullPage: true});
  check('Desktop renders 72 independent references with 447 unchanged brake parts, without automatic motion/audio');
  for (const part of layout.parts) {
    await page.locator('#overview-part-select').selectOption(part.id);
    assert.equal(await page.locator('#overview-part-id').textContent(), part.id);
    const displayed = await page.locator('#overview-mates [data-mate]').evaluateAll(nodes => nodes.map(n => n.dataset.mate));
    const highlighted = JSON.parse(await page.locator('canvas').getAttribute('data-highlighted'));
    assert.deepEqual(highlighted, displayed);
    if (part.kind === 'screw') assert.deepEqual(displayed, part.mates);
  }
  check('All 72 selections agree with highlighted counterparts; every reference screw resolves its mates');
  for (const step of layout.steps) {
    await page.locator(`button[data-step="${step.id}"]`).click();
    assert.equal((await snapshot(page)).step, step.id);
  }
  await page.locator('button[data-step="pcb"]').click();
  assert.equal(await page.locator('#overview-part-id').textContent(), 'REF_PCB_SCREW_CTRL_0');
  assert.deepEqual(await page.locator('#overview-mates [data-mate]').evaluateAll(nodes => nodes.map(n => n.dataset.mate)),
    ['REF_PCB_CTRL', 'REF_PCB_POST_CTRL_0', 'REF_CASE_TOP', 'REF_PCB_NUT_CTRL_0']);
  await page.screenshot({path: path.join(output, 'overview-pcb-fixing.png'), fullPage: true});
  check('Assembly-stage explanation and PCB → standoff → case → nut selection work');
  await page.locator('#overview-mates [data-mate="REF_PCB_CTRL"]').click();
  assert.equal(await page.locator('#overview-part-id').textContent(), 'REF_PCB_CTRL');
  for (const percentage of [0, 50, 100]) {
    await page.locator('#overview-explode').focus(); await page.keyboard.press('Home');
    if (percentage === 100) await page.keyboard.press('End');
    if (percentage === 50) for (let i=0; i<50; i+=1) await page.keyboard.press('ArrowRight');
    await page.locator('#overview-fit').click();
    assert.ok((await snapshot(page)).projectedBounds.every(n => n >= -0.98 && n <= 0.98));
  }
  await page.screenshot({path: path.join(output, 'overview-exploded.png'), fullPage: true});
  await page.locator('#case-transparent').uncheck();
  assert.equal((await snapshot(page)).transparentCase, false);
  await page.locator('#show-brakes').uncheck();
  assert.equal((await snapshot(page)).brakeParts, 0);
  await page.locator('#overview-reset').click();
  state = await snapshot(page);
  assert.equal(state.explode, 0); assert.equal(state.step, 'all'); assert.equal(state.brakeParts, 447);
  check('0/50/100% fits, enclosure transparency, brake visibility and reset work');
  await page.locator('#overview-top').click();
  await page.locator('#overview-canvas').scrollIntoViewIfNeeded();
  const pick = (await snapshot(page)).referenceScrewPickPoint;
  await page.mouse.click(pick.x, pick.y);
  assert.equal(await page.locator('#overview-part-id').textContent(), pick.id);
  check('A real 3D raycast selects the visible enclosure screw and its mating parts');
  await page.locator('#overview-canvas').focus();
  const before = (await snapshot(page)).camera;
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('+');
  assert.notDeepEqual((await snapshot(page)).camera, before);
  await page.keyboard.press('Home');
  assert.ok((await snapshot(page)).projectedBounds.every(n => n >= -0.98 && n <= 0.98));
  assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
  check('Keyboard camera and reduced-motion behavior work');
  const body = await page.locator('body').textContent();
  assert.match(body, /既存FCStd.*ブレーキ部だけ/);
  assert.match(body, /whole_fit: false/); assert.match(body, /actual_board_data: false/);
  assert.match(body, /1\.757 A > 1\.5 A/);
  check('Hypothetical dimensions, CAD exclusion and unchanged electrical/physical limits are visible');
  const cdp = await context.newCDPSession(page);
  const ax = await cdp.send('Accessibility.getFullAXTree');
  assert.ok(ax.nodes.filter(n => !n.ignored && ['button','combobox','slider','checkbox','link'].includes(n.role?.value))
    .every(n => Boolean(n.name?.value?.trim())));
  await page.goto(baseURL);
  await page.locator('html[data-viewer-state="ready"]').waitFor({timeout: 60000});
  await page.locator('a[href="./overview.html"]').click();
  await ready(page);
  check('Main brake page links to overview and all interactive controls have accessible names');
  await context.close();
  const mobile = await browser.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 1, hasTouch: true, isMobile: true});
  const phone = await mobile.newPage(); observe(phone);
  await phone.goto(new URL('overview.html', baseURL).href); await ready(phone);
  assert.ok(await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await phone.screenshot({path: path.join(output, 'overview-mobile.png'), fullPage: true});
  await phone.locator('button[data-step="pcb"]').tap();
  await phone.locator('#overview-explode').focus(); await phone.keyboard.press('End');
  await phone.locator('#overview-fit').tap();
  assert.ok((await snapshot(phone)).projectedBounds.every(n => n >= -0.98 && n <= 0.98));
  await phone.locator('#overview-reset').tap();
  check('Mobile has no horizontal overflow and supports stage, explode, fit and reset');
  await mobile.close();
  const negative = await browser.newContext();
  const failed = await negative.newPage();
  await failed.route('**/data/overview-layout.json', route => route.fulfill({status: 404, body: 'Missing test layout'}));
  await failed.goto(new URL('overview.html', baseURL).href);
  await failed.locator('html[data-overview-state="error"]').waitFor();
  assert.equal(await failed.locator('#overview-error').isVisible(), true);
  assert.match(await failed.locator('#overview-error-message').textContent(), /HTTP 404/);
  await failed.unroute('**/data/overview-layout.json');
  await failed.locator('#overview-retry').click(); await ready(failed);
  check('Missing layout shows a clear error and retry recovers after restoration');
  await negative.close();
  assert.deepEqual(errors, []); assert.deepEqual(warnings, []); assert.deepEqual(failures, []); assert.deepEqual(external, []);
  report.status='PASS'; Object.assign(report, {console_errors: errors, console_warnings: warnings, network_failures: failures, external_requests: external});
  report.inputs = [];
  for (const name of ['overview.html','overview.js','overview.css','overview-bootstrap.js','data/overview-layout.json',
    'index.html','styles.css','contract.js','data/assembly.json','data/meshes.json','vendor/manifest.json']) {
    report.inputs.push({path:name, sha256:createHash('sha256').update(await readFile(path.join(root,name))).digest('hex')});
  }
  await writeFile(path.join(root, 'validation/overview.json'), JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({status:report.status,checks:report.checks.length,console_errors:errors.length,warnings:warnings.length},null,2));
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
