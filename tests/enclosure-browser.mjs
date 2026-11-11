import {chromium} from 'playwright';
import {existsSync} from 'node:fs';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import {jointStack} from '../enclosure-contract.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = process.env.ARTIFACT_DIR || path.join(root, 'test-results/enclosure');
await mkdir(output, {recursive: true});
const assembly = JSON.parse(await readFile(path.join(root, 'data/enclosure-assembly.json'), 'utf8'));
const manifest = JSON.parse(await readFile(path.join(root, 'data/enclosure-checksums.json'), 'utf8'));
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
const errors = [], pageErrors = [], warnings = [], failures = [], external = [];
const report = {status: 'RUNNING', scope: '526-part nominal enclosure; source motor CAD fit failed; actual hardware unverified/blocked', checks: []};
const check = message => report.checks.push(message);
const ready = page => page.locator('html[data-enclosure-state="ready"]').waitFor({timeout: 60000});
const snapshot = page => page.evaluate(() => window.enclosureInspection.snapshot());
function observe(page) {
  page.on('pageerror', error => pageErrors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); if (message.type() === 'warning') warnings.push(message.text()); });
  page.on('requestfailed', request => failures.push({url: request.url(), error: request.failure()?.errorText}));
  page.on('response', response => { if (response.status() >= 400) failures.push(String(response.status())); });
  page.on('request', request => { if (!request.url().startsWith(new URL(baseURL).origin) && !request.url().startsWith('data:')) external.push(request.url()); });
}
try {
  const chrome = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  browser = await chromium.launch({headless: true, ...(existsSync(chrome) ? {executablePath: chrome} : {})});
  report.browser = await browser.version();
  const context = await browser.newContext({viewport: {width: 1440, height: 1100}, reducedMotion: 'reduce', acceptDownloads: true});
  const page = await context.newPage();
  observe(page);
  await page.goto(new URL('enclosure.html', baseURL).href);
  await ready(page);
  await page.locator('#enclosure-canvas[data-rendered="true"]').waitFor();
  let state = await snapshot(page);
  assert.equal(state.partCount, 526);
  assert.equal(state.renderedMeshCount, 526);
  assert.equal(state.referenceCount, 11);
  assert.equal(state.fastenerCount, 200);
  assert.ok(state.drawCalls >= 526 && state.triangles >= 792528);
  assert.equal(state.autoRotate, false);
  assert.equal(await page.locator('audio,video').count(), 0);
  report.initial_render = state;
  await page.screenshot({path: path.join(output, 'enclosure-desktop.png'), fullPage: true});
  check('Desktop actually renders 526 world-coordinate CAD meshes, with 11 marked references and no automatic motion/audio');
  for (const joint of assembly.joints) {
    await page.locator('#enclosure-part').selectOption(joint.fastener);
    assert.equal(await page.locator('#enclosure-fastener-id').textContent(), joint.fastener);
    const displayed = await page.locator('#enclosure-mates [data-mate]').evaluateAll(nodes => nodes.map(node => node.dataset.mate));
    assert.deepEqual(displayed, jointStack(joint));
    state = await snapshot(page);
    assert.deepEqual([...state.materialHighlights].sort(), [...displayed].sort());
    assert.equal(state.selectedMaterialColor, 0xb7802c);
  }
  check('All 200 screws select their exact ordered physical stack and change the actual mesh highlight materials');
  await page.locator('[data-focus="electronics"]').click();
  assert.equal((await snapshot(page)).selected, 'E_BOARD_SCREW_PCB_0');
  assert.match(await page.locator('#enclosure-length').textContent(), /10 mm（首下）.*13 mm/);
  await page.screenshot({path: path.join(output, 'enclosure-pcb-fixing.png'), fullPage: true});
  await page.locator('#enclosure-mates [data-mate="E_REF_BOARD_PCB"]').click();
  assert.match(await page.locator('#enclosure-part-kind').textContent(), /参照形状/);
  await page.locator('#enclosure-part').selectOption('E_REF_BOARD_MPU');
  assert.match(await page.locator('#enclosure-part-title').textContent(), /仮定/);
  await page.locator('#enclosure-part').selectOption('E_REF_MOTOR_Z');
  assert.match(await page.locator('#enclosure-part-title').textContent(), /適合は未解決/);
  check('Board under-head length, reference-board assumptions and unresolved motor-reference status stay visible');
  await page.locator('#enclosure-search').fill('NO_MATCH_IN_ROSTER');
  assert.equal(await page.locator('#enclosure-part option').count(), 1);
  assert.match(await page.locator('#enclosure-part').textContent(), /該当する部品はありません/);
  await page.locator('#enclosure-search').fill('E_CAP_SCREW_');
  assert.equal(await page.locator('#enclosure-part option').count(), 8);
  await page.locator('#enclosure-part').selectOption('E_CAP_SCREW_PPP');
  assert.equal((await snapshot(page)).selected, 'E_CAP_SCREW_PPP');
  check('Part search, empty search and all eight cover-retainer identities work');
  await page.locator('#enclosure-reset').click();
  for (const percentage of [0, 50, 100]) {
    await page.locator('#enclosure-explode').focus();
    await page.keyboard.press('Home');
    if (percentage === 100) await page.keyboard.press('End');
    if (percentage === 50) for (let i = 0; i < 50; i += 1) await page.keyboard.press('ArrowRight');
    await page.locator('#enclosure-fit').click();
    state = await snapshot(page);
    assert.equal(state.explode, percentage);
    assert.ok(state.projectedBounds.every(value => value >= -0.98 && value <= 0.98));
  }
  await page.screenshot({path: path.join(output, 'enclosure-exploded.png'), fullPage: true});
  await page.locator('#enclosure-section').check();
  assert.equal((await snapshot(page)).section, true);
  await page.locator('#enclosure-reset').click();
  assert.equal((await snapshot(page)).explode, 0);
  assert.equal((await snapshot(page)).section, false);
  assert.equal((await snapshot(page)).focus, 'all');
  await page.locator('#enclosure-section').check();
  await page.screenshot({path: path.join(output, 'enclosure-section.png'), fullPage: true});
  await page.locator('#enclosure-section').uncheck();
  check('0/50/100% explode stays within the viewport; clipping and reset preserve the unchanged CAD model');
  await page.locator('#enclosure-part').selectOption('E_HOLDER_PCB');
  await page.locator('#enclosure-canvas').scrollIntoViewIfNeeded();
  const pick = (await snapshot(page)).screwPickPoint;
  await page.mouse.click(pick.x, pick.y);
  assert.equal((await snapshot(page)).selected, pick.id);
  check('Real 3D raycasting selects the visible frame/corner screw and its receiver');
  await page.locator('#enclosure-canvas').focus();
  const before = (await snapshot(page)).camera;
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('+');
  assert.notDeepEqual((await snapshot(page)).camera, before);
  await page.keyboard.press('Home');
  assert.ok((await snapshot(page)).projectedBounds.every(value => value >= -0.98 && value <= 0.98));
  assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
  const cdp = await context.newCDPSession(page);
  const ax = await cdp.send('Accessibility.getFullAXTree');
  assert.ok(ax.nodes.filter(node => !node.ignored && ['button','combobox','slider','checkbox','link','searchbox'].includes(node.role?.value))
    .every(node => Boolean(node.name?.value?.trim())));
  check('Keyboard camera, reduced motion and accessible control names work in isolated Chrome');
  const body = await page.locator('body').textContent();
  for (const pattern of [/29\.606056754452105/, /reference_motor_CAD_nominal_fit: failed/,
    /actual_hardware_compatibility: unverified\/blocked/, /whole_fit: false/, /1\.757 A > 1\.5 A/, /176 mm/]) assert.match(body, pattern);
  report.downloads = [];
  for (const file of ['enclosure-nominal.FCStd','enclosure-nominal.step','enclosure-nominal.zip']) {
    const [download] = await Promise.all([
      page.waitForEvent('download'), page.locator(`a[href="./downloads/${file}"]`).click(),
    ]);
    assert.equal(await download.failure(), null);
    const target = path.join(output, file);
    await download.saveAs(target);
    const sha = createHash('sha256').update(await readFile(target)).digest('hex');
    assert.equal(sha, manifest.files.find(row => row.path === `downloads/${file}`).sha256);
    report.downloads.push({path: `downloads/${file}`, sha256: sha});
  }
  check('Native, STEP and curated ZIP really download through the page, with exact manifest hashes');
  await page.goto(baseURL);
  await page.locator('html[data-viewer-state="ready"]').waitFor({timeout: 60000});
  await page.locator('a[href="./enclosure.html"]').click();
  await ready(page);
  assert.equal((await snapshot(page)).renderedMeshCount, 526);
  check('The existing public brake entry links to the new nominal enclosure without replacing the old viewer');
  await context.close();
  const mobile = await browser.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 1, hasTouch: true, isMobile: true});
  const phone = await mobile.newPage();
  observe(phone);
  await phone.goto(new URL('enclosure.html', baseURL).href);
  await ready(phone);
  assert.ok(await phone.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await phone.screenshot({path: path.join(output, 'enclosure-mobile.png'), fullPage: true});
  await phone.locator('[data-focus="electronics"]').tap();
  await phone.locator('#enclosure-explode').focus();
  await phone.keyboard.press('End');
  await phone.locator('#enclosure-fit').tap();
  assert.ok((await snapshot(phone)).projectedBounds.every(value => value >= -0.98 && value <= 0.98));
  await phone.locator('#enclosure-reset').tap();
  assert.equal((await snapshot(phone)).partCount, 526);
  await mobile.close();
  check('Mobile has no horizontal overflow and supports selection, full explosion, fit and reset');
  const negative = await browser.newContext();
  const broken = await negative.newPage();
  await broken.route('**/data/enclosure-meshes.json', route => route.fulfill({status: 404, body: 'Missing test model'}));
  await broken.goto(new URL('enclosure.html', baseURL).href);
  await broken.locator('html[data-enclosure-state="error"]').waitFor();
  assert.equal(await broken.locator('#enclosure-error').isVisible(), true);
  assert.match(await broken.locator('#enclosure-error-message').textContent(), /HTTP 404/);
  await broken.unroute('**/data/enclosure-meshes.json');
  await broken.locator('#enclosure-retry').click();
  await ready(broken);
  await negative.close();
  check('An intentionally missing model produces an explicit error and successful retry, not a blank canvas');
  assert.deepEqual(errors, []);
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(warnings, []);
  assert.deepEqual(failures, []);
  assert.deepEqual(external, []);
  Object.assign(report, {status: 'PASS', console_errors: errors, page_errors: pageErrors, console_warnings: warnings,
    network_failures: failures, external_requests: external, negative_missing_model_http_404_expected: true});
  report.inputs = [];
  for (const name of ['enclosure.html','enclosure.js','enclosure.css','enclosure-bootstrap.js','enclosure-contract.js',
    'index.html','styles.css','contract.js','data/enclosure-assembly.json','data/enclosure-meshes.json','data/enclosure-checksums.json','vendor/manifest.json']) {
    report.inputs.push({path: name, sha256: createHash('sha256').update(await readFile(path.join(root, name))).digest('hex')});
  }
  await writeFile(path.join(root, 'validation/enclosure-browser.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({status: report.status, checks: report.checks.length, console_errors: errors.length, warnings: warnings.length}, null, 2));
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
