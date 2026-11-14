import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdir, readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = process.env.ARTIFACT_DIR || path.join(root, 'test-results/motion');
await mkdir(output, {recursive: true});
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const server = spawn('python3', ['-B', 'scripts/serve_public.py', '--port', '0'], {cwd: root, stdio: ['ignore', 'pipe', 'pipe']});
let stderr = '';
server.stderr.on('data', chunk => { stderr += chunk; });
const base = await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(new Error('Motion preview did not start')), 10000);
  server.once('exit', code => { clearTimeout(timeout); reject(new Error(`Preview exited ${code}: ${stderr}`)); });
  server.stdout.on('data', chunk => {
    const url = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+\/pico-brake-mechanical-design\//)?.[0];
    if (url) { clearTimeout(timeout); resolve(url); }
  });
}).catch(error => { server.kill('SIGTERM'); throw error; });
const url = new URL('motion.html', base).href;
const report = {schema: 'c08-motion-browser-v1', status: 'RUNNING', scope: 'Isolated real browser and actual rendered transforms; no physical qualification',
  checks: [], errors: [], externalRequests: [], inputs: []};
const record = title => report.checks.push(title);
const snapshot = page => page.evaluate(() => window.c08Motion.snapshot());
const ready = page => page.waitForFunction(() => document.documentElement.dataset.motionState === 'ready' && window.c08Motion?.snapshot().renderedFrames > 0);
const approx = (a, b, label) => assert.ok(Math.abs(a - b) < 3e-5, `${label}: ${a} vs ${b}`);
const wait = page => page.waitForTimeout(100);
function observe(page) {
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') report.errors.push(message.text()); });
  page.on('request', request => {
    if (!request.url().startsWith(new URL(base).origin) && !request.url().startsWith('data:')) report.externalRequests.push(request.url());
  });
  page.on('response', response => { if (response.status() >= 400) report.errors.push(`${response.status()} ${new URL(response.url()).pathname}`); });
}
let browser;
try {
  browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  report.browser = await browser.version();
  const context = await browser.newContext({viewport: {width: 1366, height: 768}, reducedMotion: 'reduce'});
  const page = await context.newPage(); observe(page);
  await page.goto(url); await ready(page); await wait(page);
  let s = await snapshot(page);
  assert.equal(s.state.playing, false); assert.equal(s.autoRotate, false);
  assert.ok(s.drawCalls > 0 && s.triangles > 100000);
  assert.equal(s.transforms.HUB.role, 'rotating');
  approx(s.transforms.HUB.position[2], 0, 'initial hub z');
  approx(s.actualGap, .2, 'initial actual geometry gap');
  const idleHash = hash(await page.locator('canvas').screenshot());
  await page.waitForTimeout(250);
  assert.equal(hash(await page.locator('canvas').screenshot()), idleHash);
  record('Initial real geometry is paused with stable rendering under reduced-motion');
  const laptop = await page.evaluate(() => {
    const ids = ['viewport','play','progress','explode','assemble'];
    return Object.fromEntries(ids.map(id => {
      const r = document.getElementById(id).getBoundingClientRect();
      return [id,{top:r.top,bottom:r.bottom,left:r.left,right:r.right}];
    }));
  });
  assert.ok(laptop.viewport.top >= 0 && laptop.viewport.bottom <= 768, JSON.stringify(laptop));
  for (const id of ['play','progress','explode','assemble']) assert.ok(laptop[id].top >= 0 && laptop[id].bottom <= 768, `${id} off laptop screen`);
  await page.screenshot({path: path.join(output, 'laptop-model.png')});
  record('1366x768 shows the main model and playback/seek/explosion controls together');

  const rect = await page.locator('canvas').boundingBox();
  const cameraBefore = s.camera;
  await page.mouse.move(rect.x+rect.width*.5,rect.y+rect.height*.5);
  await page.mouse.down();await page.mouse.move(rect.x+rect.width*.65,rect.y+rect.height*.42,{steps:10});await page.mouse.up();
  await wait(page);
  s=await snapshot(page);
  assert.notDeepEqual(s.camera,cameraBefore);
  approx(s.pose.angle,20,'camera orbit must not rotate parts');
  const zoomBefore=s.zoom;
  await page.mouse.wheel(0,-180);await wait(page);
  assert.notEqual((await snapshot(page)).zoom,zoomBefore);
  await page.locator('canvas').focus();
  const keyCamera=(await snapshot(page)).camera;
  await page.keyboard.press('ArrowRight');await page.keyboard.press('+');await wait(page);
  assert.notDeepEqual((await snapshot(page)).camera,keyCamera);
  await page.keyboard.press('Home');await wait(page);
  record('Actual pointer drag, wheel and keyboard modify the camera, not the part rotation');

  await page.locator('[data-time="8"]').click();await wait(page);
  const before=await snapshot(page);
  const beforePixels=hash(await page.locator('canvas').screenshot());
  await page.locator('#play').click();
  await page.waitForTimeout(450);
  await page.locator('#play').click();await wait(page);
  const paused=await snapshot(page);
  assert.ok(paused.pose.angle>before.pose.angle);
  assert.equal(paused.state.playing,false);
  assert.notEqual(hash(await page.locator('canvas').screenshot()),beforePixels);
  assert.notDeepEqual(paused.transforms.REF_WHEEL.matrix,before.transforms.REF_WHEEL.matrix);
  assert.deepEqual(paused.transforms.WINDING.matrix,before.transforms.WINDING.matrix);
  assert.equal(paused.transforms.HUB.position[2],0);
  await page.waitForTimeout(250);
  assert.equal((await snapshot(page)).pose.angle,paused.pose.angle);
  assert.deepEqual((await snapshot(page)).camera,paused.camera);
  record('Actual marked parts rotate in playback; winding stays still; pause freezes matrices and camera');

  await page.locator('[data-time="16"]').click();await wait(page);
  s=await snapshot(page);
  assert.equal(s.schematicVisible,true);approx(s.schematicGap,18,'enlarged open gap');
  const openPixels=hash(await page.locator('canvas').screenshot());
  await page.screenshot({path:path.join(output,'contact-before.png')});
  await page.locator('[data-time="22"]').click();await wait(page);
  s=await snapshot(page);
  approx(s.schematicGap,0,'enlarged contact gap');approx(s.actualGap,0,'actual source mesh contact gap');
  approx(s.transforms.ARMATURE.position[2],.2,'armature travel');
  assert.equal(s.transforms.HUB.position[2],0);
  approx(s.springDisplacement.root,0,'spring root');approx(s.springDisplacement.tip,.2,'spring tip');
  assert.equal(s.contactHighlight,true);
  assert.notEqual(hash(await page.locator('canvas').screenshot()),openPixels);
  await page.screenshot({path:path.join(output,'contact-touching.png')});
  await page.locator('[data-view="section"]').click();await wait(page);
  assert.equal((await snapshot(page)).sectionVisible,true);
  assert.equal((await snapshot(page)).actualContactHighlight,true);
  assert.match(await page.locator('#view-label').textContent(),/実CAD.*0.20/);
  await page.screenshot({path:path.join(output,'actual-section-contact.png')});
  await page.locator('#progress').fill('21.5');await wait(page);
  s=await snapshot(page);assert.ok(s.actualGap>0);assert.equal(s.pose.braking,false);
  assert.equal(s.actualContactHighlight,false);
  await page.locator('#progress').fill('24');await page.locator('[data-view="model"]').click();await wait(page);
  assert.equal((await snapshot(page)).frictionArrowVisible,true);
  await page.locator('[data-time="30.8"]').click();await page.locator('[data-view="model"]').click();await wait(page);
  s=await snapshot(page);assert.equal(s.frictionArrowVisible,false);assert.equal(s.pose.speed,0);
  const stoppedAngle=s.pose.angle;
  await page.locator('[data-time="36"]').click();await wait(page);
  s=await snapshot(page);approx(s.actualGap,.2,'restored actual gap');approx(s.schematicGap,18,'restored schematic gap');
  assert.equal(s.pose.angle,stoppedAngle);assert.equal(s.state.playing,false);
  record('Large schematic and source-derived section show gap/contact/release; root and hub fixed; torque arrow only while braking');

  await page.locator('[data-time="8"]').click();await page.locator('#play').click();
  await page.locator('#explode').fill('60');await wait(page);
  s=await snapshot(page);assert.equal(s.state.playing,false);assert.equal(s.state.explode,60);assert.equal(s.state.time,4);
  assert.equal(await page.locator('#play').isDisabled(),true);
  assert.ok(Math.abs(s.transforms.WINDING.position[2])>1);
  await page.screenshot({path:path.join(output,'exploded.png')});
  await page.locator('#assemble').click();await wait(page);
  s=await snapshot(page);assert.equal(s.state.explode,0);assert.equal(s.state.playing,false);
  await page.locator('#explode').fill('40');
  await page.locator('[data-time="22"]').click();await wait(page);
  s=await snapshot(page);assert.equal(s.state.explode,0);assert.equal(s.state.playing,false);assert.equal(s.state.view,'schematic');
  await page.locator('#explode').fill('30');await page.locator('[data-view="section"]').click();await wait(page);
  s=await snapshot(page);assert.equal(s.state.explode,0);assert.equal(s.state.playing,false);
  await page.locator('[data-view="three"]').click();await wait(page);
  assert.deepEqual((await snapshot(page)).visibleAxes,['Z','X','Y']);
  await page.locator('#reset-motion').click();await wait(page);
  assert.equal((await snapshot(page)).state.time,4);
  record('Explosion pauses/reset motion; reassembly does not restart; jumps/sections resolve exploded-state conflicts; XYZ works');

  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.locator('#play').click();await page.waitForTimeout(100);
  await page.emulateMedia({reducedMotion:'reduce'});await wait(page);
  assert.equal((await snapshot(page)).state.playing,false);
  await page.locator('#progress').fill('39.95');await page.locator('#play').click();await page.waitForTimeout(350);
  assert.equal((await snapshot(page)).state.time,40);assert.equal((await snapshot(page)).state.playing,false);
  const cdp=await context.newCDPSession(page);
  const ax=await cdp.send('Accessibility.getFullAXTree');
  const controls=ax.nodes.filter(n=>!n.ignored&&['button','slider','combobox','checkbox','link'].includes(n.role?.value));
  assert.ok(controls.length>15);
  assert.ok(controls.every(n=>n.name?.value?.trim()));
  await page.locator('.video-panel > summary').click();
  await page.waitForFunction(()=>document.getElementById('explanation-video').readyState>=1);
  const video=await page.locator('video').evaluate(v=>({muted:v.muted,volume:v.volume,paused:v.paused,duration:v.duration}));
  assert.deepEqual(video,{muted:true,volume:0,paused:true,duration:40});
  record('No loop/restart; reduced-motion change pauses; accessibility names present; CG is initially paused and muted volume0');
  await context.close();

  for (const [width,height] of [[390,844],[320,568]]) {
    const mobile=await browser.newContext({viewport:{width,height},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
    const mp=await mobile.newPage();observe(mp);
    await mp.goto(url);await ready(mp);
    await mp.locator('[data-time="22"]').tap();await wait(mp);
    assert.equal((await snapshot(mp)).state.view,'schematic');
    const layout=await mp.evaluate(()=>{
      const r=document.querySelector('#viewport').getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth>innerWidth+1,top:r.top,bottom:r.bottom,height:innerHeight};
    });
    assert.equal(layout.overflow,false);
    assert.ok(layout.top>=-1 && layout.bottom<layout.height,JSON.stringify(layout));
    await mp.screenshot({path:path.join(output,`mobile-${width}-contact.png`)});
    await mp.locator('#explode').fill('50');await wait(mp);
    assert.equal((await snapshot(mp)).state.playing,false);
    const model=await mp.locator('#viewport').boundingBox();
    assert.ok(model.y>=-1 && model.y+model.height<=height);
    await mp.locator('#assemble').tap();await wait(mp);
    assert.equal((await snapshot(mp)).state.playing,false);
    const touch=await mobile.newCDPSession(mp);
    const r=await mp.locator('#motion-canvas').boundingBox();
    const x=r.x+r.width*.5,y=r.y+r.height*.45;
    const cameraBefore=(await snapshot(mp)).camera;
    await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y,id:1}]});
    for(let i=1;i<=5;i+=1) await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x+i*8,y:y-i*3,id:1}]});
    await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await wait(mp);
    assert.notDeepEqual((await snapshot(mp)).camera,cameraBefore);
    const z=(await snapshot(mp)).zoom;
    await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:x-30,y,id:1},{x:x+30,y,id:2}]});
    await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:x-60,y,id:1},{x:x+60,y,id:2}]});
    await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await wait(mp);
    assert.notEqual((await snapshot(mp)).zoom,z);
    await mobile.close();
  }
  record('390x844 and320x568 touch layouts keep the model visible; actual touch orbit and pinch zoom work');

  for (const fixture of ['missing-section','mesh-mismatch']) {
    const bad=await browser.newPage();
    if (fixture==='missing-section') await bad.route('**/data/motion-section.json',route=>route.fulfill({status:404,body:'missing'}));
    else await bad.route('**/data/meshes.json',route=>route.fulfill({status:200,contentType:'application/json',body:'{}'}));
    await bad.goto(url);await bad.locator('html[data-motion-state="error"]').waitFor();
    assert.equal(await bad.locator('#load-error').isVisible(),true);
    assert.equal(await bad.locator('#motion-controls').evaluate(node=>node.disabled),true);
    assert.equal(await bad.locator('#play').isDisabled(),true);
    assert.match(await bad.locator('#error-message').textContent(),fixture==='missing-section'?/HTTP 404/:/SHA-256/);
    await bad.close();
  }
  record('Missing slice and mismatched source meshes fail explicitly instead of showing a success-shaped blank scene');
  assert.deepEqual(report.errors,[]);
  assert.deepEqual(report.externalRequests,[]);
  report.status='PASS';
  const inputs=['motion.html','motion.css','motion.js','motion-scene.js','motion-contract.js','motion-bootstrap.js',
    'data/motion-section.json','data/assembly.json','data/meshes.json','media/c08-motion.mp4','media/c08-poster.png','vendor/manifest.json'];
  for (const file of inputs) report.inputs.push({path:file,sha256:hash(await readFile(path.join(root,file)))});
  await writeFile(path.join(root,'validation/motion-browser.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({status:report.status,checks:report.checks,errors:report.errors,externalRequests:report.externalRequests},null,2));
} catch (error) {
  report.status='FAIL';report.failure=error.stack;
  await writeFile(path.join(output,'failure.json'),JSON.stringify(report,null,2)+'\n');
  throw error;
} finally {
  if(browser)await browser.close();
  server.kill('SIGTERM');
}
