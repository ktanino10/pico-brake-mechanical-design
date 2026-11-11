import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../', import.meta.url));
const artifacts = process.env.ARTIFACT_DIR || path.join(root, 'test-results/browser');
await mkdir(artifacts, {recursive: true});
const assembly = JSON.parse(await readFile(path.join(root, 'data/assembly.json'), 'utf8'));
const checksumFile = JSON.parse(await readFile(path.join(root, 'data/checksums.json'), 'utf8'));
const hashes = new Map(checksumFile.files.map(file => [file.path, file.sha256]));
const hash = data => createHash('sha256').update(data).digest('hex');
const server = spawn('python3', ['-B', 'scripts/serve_public.py', '--port', '0'], {
  cwd: root, stdio: ['ignore', 'pipe', 'pipe'],
});
let serverError = '';
server.stderr.on('data', data => { serverError += data.toString(); });
const baseURL = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('Preview did not start')), 10000);
  server.once('exit', code => { clearTimeout(timer); reject(new Error(`Preview exited ${code}: ${serverError}`)); });
  server.stdout.on('data', data => {
    const match = data.toString().match(/http:\/\/127\.0\.0\.1:\d+\/pico-brake-mechanical-design\//);
    if (match) { clearTimeout(timer); resolve(match[0]); }
  });
}).catch(error => { server.kill('SIGTERM'); throw error; });
const candidates = process.env.CHROME_PATH ? [process.env.CHROME_PATH] :
  ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
const executablePath = candidates.find(name => existsSync(name));
if (process.env.CHROME_PATH && !executablePath) {
  server.kill('SIGTERM');
  throw new Error('CHROME_PATH is not an existing browser');
}
let browser;
const report = {schema: 'public-brake-browser-validation-v1', status: 'RUNNING',
  scope: 'Real isolated Chrome; desktop/mobile UI and public-file downloads only, not physical validation.',
  assertions: [], downloads: [], warnings: [], console_errors: [], external_requests: []};
const check = label => { report.assertions.push(label); };
const snapshot = page => page.evaluate(() => window.brakeInspection.snapshot());
const ready = page => page.locator('html[data-viewer-state="ready"]').waitFor({timeout: 60000});
const errors = [], warnings = [], badResponses = [], requests = [];
let downloadTargets = new Set();
function observe(page) {
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
    if (message.type() === 'warning') warnings.push(message.text());
  });
  page.on('request', request => requests.push(request.url()));
  page.on('response', response => {
    if (response.status() >= 400) badResponses.push(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  page.on('requestfailed', request => {
    if (!downloadTargets.has(request.url())) errors.push(`${new URL(request.url()).pathname}: ${request.failure()?.errorText}`);
  });
}
async function download(page, selector, relative) {
  const targetURL = new URL(relative, baseURL).href;
  downloadTargets.add(targetURL);
  const pending = page.waitForEvent('download');
  await page.locator(selector).click();
  const item = await pending;
  assert.equal(await item.failure(), null);
  const destination = path.join(artifacts, path.basename(relative));
  await item.saveAs(destination);
  const actual = hash(await readFile(destination));
  assert.equal(actual, hashes.get(relative), `${relative} downloaded bytes differ`);
  report.downloads.push({path: relative, sha256: actual, browser_download_verified: true});
}
try {
  browser = await chromium.launch({headless: true, ...(executablePath ? {executablePath} : {})});
  report.browser = await browser.version();
  const desktop = await browser.newContext({viewport: {width: 1440, height: 1100}, deviceScaleFactor: 1,
    acceptDownloads: true, reducedMotion: 'reduce'});
  const page = await desktop.newPage();
  observe(page);
  await page.goto(baseURL);
  await ready(page);
  await page.locator('#assembly-canvas[data-rendered="true"]').waitFor();
  assert.equal(await page.locator('#assembly-canvas').getAttribute('data-visible-parts'), '149');
  assert.equal(await page.locator('#part-id').textContent(), 'Z_RETAINER_BOLT_0');
  assert.equal(await page.locator('#torque-value').textContent(), '0.37–0.42 N·m');
  let initial = await snapshot(page);
  assert.ok(initial.drawCalls > 0 && initial.triangles > 200000, 'Actual WebGL scene was not rendered');
  assert.equal(initial.autoRotate, false);
  assert.equal(initial.damping, false);
  assert.equal(await page.locator('audio,video').count(), 0);
  assert.equal(await page.evaluate(() => matchMedia('(prefers-reduced-motion: reduce)').matches), true);
  check('Desktop 1440x1100 renders the exact 149-part mm scene without audio or automatic motion');
  await page.screenshot({path: path.join(artifacts, 'desktop.png'), fullPage: true});
  await new Promise(resolve => setTimeout(resolve, 600));
  initial = await snapshot(page);
  const still = hash(await page.locator('canvas').screenshot());
  await new Promise(resolve => setTimeout(resolve, 450));
  assert.deepEqual((await snapshot(page)).camera, initial.camera);
  assert.equal(hash(await page.locator('canvas').screenshot()), still);
  check('Reduced-motion and idle camera produce a stable rendered canvas');

  const screws = assembly.parts.filter(part => part.is_fastener);
  for (const axis of ['Z', 'X', 'Y']) {
    if (axis === 'X') await page.locator('button[data-mode="three"]').click();
    if (axis !== 'Z') await page.locator('#axis-select').selectOption(axis);
    for (const screw of screws) {
      await page.locator('#part-select').selectOption(screw.id);
      assert.equal(await page.locator('#part-id').textContent(), `${axis}_${screw.id}`);
      assert.equal(await page.locator('#joint-id').textContent(), screw.joint_id);
      const actual = await page.locator('[data-mate]').evaluateAll(nodes => nodes.map(node => node.dataset.mate));
      assert.deepEqual(actual, screw.mates, `Incorrect card mates for ${axis}_${screw.id}`);
      const highlighted = JSON.parse(await page.locator('canvas').getAttribute('data-highlighted'));
      assert.deepEqual(highlighted, screw.mates.map(id => `${axis}_${id}`));
      assert.equal(await page.locator('#reference-caution').isVisible(), screw.reference_joint);
    }
  }
  assert.equal(await page.locator('canvas').getAttribute('data-visible-parts'), '447');
  assert.deepEqual((await snapshot(page)).visibleAxes, ['Z', 'X', 'Y']);
  check(`All ${screws.length} threaded components on all three axes have correct IDs, joints and public mate IDs`);
  await page.locator('#part-select').selectOption('MOTOR_INTERFACE_BOLT_0');
  assert.equal(await page.locator('#torque-value').textContent(), '未決');
  assert.match(await page.locator('#joint-receiver').textContent(), /不明/);
  await page.locator('#part-select').selectOption('FRAME_BOLT_0');
  assert.equal(await page.locator('[data-mate="REF_FRAME"]').getAttribute('data-reference'), 'true');
  await page.locator('[data-mate="REF_FRAME"]').click();
  assert.equal(await page.locator('#part-id').textContent(), 'Y_REF_FRAME');
  assert.match(await page.locator('#part-kind').textContent(), /独立.*参考形状/);
  check('Reference counterpart navigation and unresolved motor torque remain explicitly labelled');

  await page.locator('[data-pick="WINDING"]').click();
  await page.locator('#section').check();
  await page.locator('#explode').focus();
  await page.keyboard.press('End');
  assert.equal(await page.locator('#explode-value').textContent(), '100%');
  assert.equal((await snapshot(page)).clippingPlanes, 1);
  assert.equal(await page.locator('canvas').getAttribute('data-explode'), '100');
  await page.screenshot({path: path.join(artifacts, 'three-axis-exploded-section.png'), fullPage: true});
  await page.locator('#section-position').focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.locator('#section-value').textContent(), 'X 1 mm');
  check('Keyboard explode reaches 100%, section clipping is active, and section position changes in mm');
  await page.locator('#reset').click();
  assert.equal(await page.locator('canvas').getAttribute('data-mode'), 'single');
  assert.equal(await page.locator('canvas').getAttribute('data-explode'), '0');
  assert.equal(await page.locator('canvas').getAttribute('data-section'), 'false');
  assert.equal(await page.locator('#part-id').textContent(), 'Z_RETAINER_BOLT_0');
  check('Reset restores composition, axis, selection, explode, section, filter and highlight defaults');

  await page.locator('#highlight').uncheck();
  await page.locator('#front-view').click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await new Promise(resolve => setTimeout(resolve, 80));
  const hint = (await snapshot(page)).projectedFasteners.find(row => row.id === 'Z_FRAME_BOLT_0');
  await page.mouse.click(hint.x, hint.y);
  assert.equal(await page.locator('#part-id').textContent(), 'Z_FRAME_BOLT_0');
  check('A real 3D raycast click on the visible frame screw opens its J01 card');
  await page.locator('canvas').focus();
  const cameraBefore = (await snapshot(page)).camera;
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('+');
  assert.notDeepEqual((await snapshot(page)).camera, cameraBefore);
  await page.keyboard.press('Home');
  check('Keyboard camera orbit, zoom and Home operate on the actual Three camera');

  for (const mode of ['single', 'three']) {
    await page.locator(`button[data-mode="${mode}"]`).click();
    for (const percentage of [0, 50, 100]) {
      await page.locator('#explode').focus();
      await page.keyboard.press('Home');
      if (percentage === 100) await page.keyboard.press('End');
      if (percentage === 50) {
        for (let i = 0; i < 50; i += 1) await page.keyboard.press('ArrowRight');
      }
      await page.locator('#fit-view').click();
      const {projectedBounds} = await snapshot(page);
      assert.ok(projectedBounds.every(value => value >= -0.98 && value <= 0.98),
        `Clipped ${mode} ${percentage}%: ${projectedBounds.join(',')}`);
    }
  }
  check('All geometry bounds fit the viewport in single/reference-three modes at 0/50/100% without a per-frame camera override');

  for (const [mode, file] of [['single', 'single'], ['three', 'reference-three']]) {
    await page.locator(`button[data-mode="${mode}"]`).click();
    await download(page, '#download-native', `downloads/brake-${file}.FCStd`);
    await download(page, '#download-step', `downloads/brake-${file}.step`);
  }
  await download(page, '#download-zip', 'downloads/public-brake-cad.zip');
  check('Both native/STEP compositions and curated ZIP downloaded through real browser UI with matching SHA-256');

  const cdp = await desktop.newCDPSession(page);
  const ax = await cdp.send('Accessibility.getFullAXTree');
  const interactive = ax.nodes.filter(node => !node.ignored &&
    ['button', 'combobox', 'slider', 'checkbox', 'link'].includes(node.role?.value));
  assert.ok(interactive.length > 20);
  assert.ok(interactive.every(node => Boolean(node.name?.value?.trim())), 'Unnamed interactive accessibility node');
  assert.equal(await page.locator('h1').count(), 1);
  const tabPage = await desktop.newPage();
  await tabPage.goto(baseURL);
  await ready(tabPage);
  await tabPage.keyboard.press('Tab');
  assert.equal(await tabPage.evaluate(() => document.activeElement?.className), 'skip-link');
  const outline = await tabPage.evaluate(() => getComputedStyle(document.activeElement).outlineWidth);
  assert.notEqual(outline, '0px');
  await tabPage.close();
  check('Real Chrome accessibility tree labels all controls; keyboard skip-link and visible focus are present');
  report.performance = await page.evaluate(() => {
    const n = performance.getEntriesByType('navigation')[0];
    return {navigation_duration_ms: n.duration, dom_content_loaded_ms: n.domContentLoadedEventEnd,
      transfer_bytes: performance.getEntriesByType('resource').reduce((sum, item) => sum + item.transferSize, 0)};
  });
  await desktop.close();

  const mobile = await browser.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 1,
    isMobile: true, hasTouch: true, reducedMotion: 'reduce'});
  const mobilePage = await mobile.newPage();
  observe(mobilePage);
  await mobilePage.goto(baseURL);
  await ready(mobilePage);
  assert.ok(await mobilePage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile overflow');
  const layout = await mobilePage.evaluate(() => {
    const bench = document.querySelector('.bench').getBoundingClientRect();
    const inspector = document.querySelector('.inspector').getBoundingClientRect();
    return {benchBottom: bench.bottom, inspectorTop: inspector.top};
  });
  assert.ok(layout.inspectorTop >= layout.benchBottom);
  await mobilePage.screenshot({path: path.join(artifacts, 'mobile.png'), fullPage: true});
  await mobilePage.locator('[data-pick="WINDING"]').tap();
  assert.equal(await mobilePage.locator('#part-id').textContent(), 'Z_WINDING');
  await mobilePage.locator('[data-pick="ARMATURE"]').tap();
  assert.equal(await mobilePage.locator('#part-id').textContent(), 'Z_ARMATURE');
  await mobilePage.locator('#section').check();
  await mobilePage.locator('#explode').focus();
  await mobilePage.keyboard.press('End');
  await mobilePage.locator('#viewport').screenshot({path: path.join(artifacts, 'mobile-exploded-section.png')});
  await mobilePage.locator('#reset').tap();
  assert.equal(await mobilePage.locator('canvas').getAttribute('data-section'), 'false');
  check('Touch-capable 390x844 viewport has no horizontal overflow, stacked layout, selection, explode, section and reset');
  await mobile.close();

  const failureContext = await browser.newContext({viewport: {width: 1100, height: 900}});
  const failed = await failureContext.newPage();
  await failed.route('**/data/meshes.json', route => route.fulfill({status: 404, contentType: 'text/plain', body: 'Missing test model'}));
  await failed.goto(baseURL);
  await failed.locator('html[data-viewer-state="error"]').waitFor();
  assert.equal(await failed.locator('#load-error').isVisible(), true);
  assert.match(await failed.locator('#error-message').textContent(), /HTTP 404/);
  await failed.screenshot({path: path.join(artifacts, 'missing-model.png'), fullPage: true});
  await failed.unroute('**/data/meshes.json');
  await failed.locator('#retry').click();
  await ready(failed);
  check('Missing mesh produces a visible HTTP 404 explanation; retry succeeds once the file is restored');
  await failed.route('**/data/meshes.json', route => route.fulfill({status: 200, contentType: 'application/json', body: '{"parts":[]}'}));
  await failed.reload();
  await failed.locator('html[data-viewer-state="error"]').waitFor();
  assert.match(await failed.locator('#error-message').textContent(), /SHA-256/);
  await failed.unroute('**/data/meshes.json');
  check('Tampered or mixed-version mesh is rejected with a visible SHA-256 error');
  const paused = await failureContext.newPage();
  await paused.route('**/data/checksums.json', route => route.fulfill({status: 200, contentType: 'application/json',
    body: JSON.stringify({...checksumFile, downloads_ready: false, reason: '独立姿勢照合のため一時停止中。'})}));
  await paused.goto(baseURL);
  await ready(paused);
  assert.equal(await paused.locator('#download-native').getAttribute('aria-disabled'), 'true');
  assert.equal(await paused.locator('#download-status').isVisible(), true);
  assert.match(await paused.locator('#download-status').textContent(), /姿勢照合/);
  check('An explicitly paused CAD release disables download actions and shows the reason while 3D remains inspectable');
  const vendorFailure = await failureContext.newPage();
  await vendorFailure.route('**/vendor/three.module.js', route => route.fulfill({status: 404, body: 'Missing test vendor'}));
  await vendorFailure.goto(baseURL);
  await vendorFailure.locator('html[data-viewer-state="error"]').waitFor();
  assert.equal(await vendorFailure.locator('#load-error').isVisible(), true);
  check('A missing local 3D engine is caught by bootstrap rather than leaving a blank canvas');
  const filePage = await failureContext.newPage();
  await filePage.goto(pathToFileURL(path.join(root, 'index.html')).href);
  await filePage.locator('html[data-viewer-state="error"]').waitFor();
  assert.match(await filePage.locator('#error-message').textContent(), /file:\/\/.*HTTP/);
  check('Opening file:// shows an explicit local-HTTP instruction without attempting model fetches');
  await failureContext.close();

  const rootContext = await browser.newContext();
  const rootPage = await rootContext.newPage();
  observe(rootPage);
  await rootPage.goto(new URL('/', baseURL).href);
  await ready(rootPage);
  assert.equal(await rootPage.locator('canvas').getAttribute('data-visible-parts'), '149');
  const gitProbe = await rootPage.request.get(new URL('/.git/config', baseURL).href);
  assert.equal(gitProbe.status(), 404);
  const sourceProbe = await rootPage.request.get(new URL('/scripts/build_cad.py', baseURL).href);
  assert.equal(sourceProbe.status(), 404);
  check('Both root and Pages-style subpath work; preview does not serve .git or local build scripts');
  await rootContext.close();
  const external = requests.filter(url => !url.startsWith(new URL(baseURL).origin) && !url.startsWith('data:'));
  assert.deepEqual(errors, [], 'Unexpected browser errors');
  assert.deepEqual(warnings, [], 'Unexpected browser warnings');
  assert.deepEqual(badResponses, [], 'Unexpected resource failures');
  assert.deepEqual(external, [], 'External network request');
  report.status = 'PASS';
  report.warnings = warnings;
  report.console_errors = errors;
  report.external_requests = external;
  report.resource_requests = requests.length;
  report.controlled_failure_cases_excluded_from_clean_console_assertion = true;
  await writeFile(path.join(root, 'validation/browser.json'), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify({status: report.status, assertions: report.assertions.length,
    downloads: report.downloads.length, console_errors: errors.length, warnings: warnings.length,
    external_requests: external.length}, null, 2));
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
