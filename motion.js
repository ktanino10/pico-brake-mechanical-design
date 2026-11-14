import {validateAssembly, validateMesh} from './contract.js';
import {DURATION, GAP_MM, initialMotionState, motionRole, poseAt, transition} from './motion-contract.js';
import {createMotionScene} from './motion-scene.js';

const $ = id => document.getElementById(id);
async function load(url, bytes = false) {
  const response = await fetch(url, {signal: AbortSignal.timeout(20000), cache: 'no-cache'});
  if (!response.ok) throw new Error(`${url} を読み込めません（HTTP ${response.status}）。公開ファイル一式を確認してください。`);
  return bytes ? response.arrayBuffer() : response.json();
}

function validateSection(data, assembly) {
  if (data?.schema !== 'public-c08-motion-section-v1' || data.units !== 'mm' || data.physical_ready !== false ||
      data.source_mesh_sha256 !== assembly.mesh.sha256 || data.gap_mm !== GAP_MM ||
      !Array.isArray(data.parts) || !data.parts.length) throw new Error('実CAD断面データの形式・版・未資格状態が不正です。');
  const parts = new Map(assembly.parts.map(p => [p.id,p]));
  const seen = new Set();
  for (const p of data.parts) {
    if (!parts.has(p.id) || seen.has(p.id) || !Array.isArray(p.positions) || !Array.isArray(p.indices) ||
        p.positions.length < 9 || p.positions.length % 3 || !p.positions.every(Number.isFinite) ||
        p.indices.length < 12 || p.indices.length % 3 ||
        !p.indices.every(i => Number.isInteger(i) && i >= 0 && i < p.positions.length/3)) throw new Error('実CAD断面の形状・部品対応が不正です。');
    const b = parts.get(p.id).bbox_mm;
    if (p.positions.some((v,i)=>v<b[i%3]-.12 || v>b[i%3+3]+.12)) throw new Error('実CAD断面が元部品の寸法と一致しません。');
    seen.add(p.id);
  }
  if (!seen.has('ARMATURE') || !seen.has('LINING_0')) throw new Error('接触する円盤・摩擦面の断面がありません。');
  return data;
}

export async function start(onError) {
  const [rawAssembly, bytes, rawSection] = await Promise.all([
    load('./data/assembly.json'), load('./data/meshes.json',true), load('./data/motion-section.json'),
  ]);
  const assembly = validateAssembly(rawAssembly);
  if (!crypto.subtle) throw new Error('形状のSHA-256確認にはHTTPSまたはlocalhostが必要です。');
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
  if (hash !== assembly.mesh.sha256) throw new Error('部品表と形状のSHA-256が一致しません。異なる版を混ぜずに取り直してください。');
  const meshes = validateMesh(JSON.parse(new TextDecoder().decode(bytes)),assembly);
  const section = validateSection(rawSection,assembly);
  for (const p of assembly.parts) motionRole(p);
  let state = initialMotionState(), frameHandle = 0, lastTime = null, failed = false, lastStage = '';
  let scene;
  const labels = $('scene-labels');
  const spans = Array.from({length:4},()=>{
    const span=document.createElement('span');span.hidden=true;labels.append(span);return span;
  });
  function error(reason) {
    failed=true;state.playing=false;cancelAnimationFrame(frameHandle);onError(reason);
  }
  function schedule() {
    if (!failed && !frameHandle) frameHandle=requestAnimationFrame(draw);
  }
  function syncUI() {
    const pose=poseAt(state.time);
    $('play').textContent=state.playing?'動作を一時停止':'動作を再生';
    $('play').disabled=state.explode>0;
    $('progress').value=String(state.time);
    $('progress').setAttribute('aria-valuetext',`${state.time.toFixed(1)}秒、${pose.stage}`);
    $('progress-value').textContent=`${state.time.toFixed(1)} / ${DURATION}秒`;
    $('explode').value=String(state.explode);$('explode-value').textContent=`${state.explode}%`;
    $('cutaway').checked=state.cutaway;
    $('cutaway').disabled=state.view!=='model';
    for (const b of document.querySelectorAll('[data-view]')) b.setAttribute('aria-pressed',String(b.dataset.view===state.view));
    const stage=state.explode ? '分解表示（作動ではありません）' : pose.stage;
    if (stage!==lastStage) { $('stage').textContent=stage;lastStage=stage; }
    $('stage-explanation').textContent=state.explode?'再生を停止しています。組み戻しても勝手に再生しません。':pose.explanation;
    $('state-notice').textContent=state.notice;
    $('power-state').textContent=state.explode?'作動を表示しない状態':`駆動${pose.drive?'ON':'OFF'} / 電磁石${pose.coil?'ON':'OFF'}`;
    const titles={model:'実CADの立体（視点はドラッグで回転）',three:'XYZ参考配置（機体の姿勢は固定）',
      section:'実CADの断面：名目すき間0.20mm',schematic:'模式断面：すき間・動きは説明用に拡大'};
    $('view-label').textContent=titles[state.view];
    $('scene-note').textContent=state.explode?'分解は位置関係の説明です。組立経路・干渉なしを保証しません。':
      state.view==='schematic'?'拡大模式図／青い円盤が灰色の摩擦面へ接触。ハブの軸位置は固定。':
      state.view==='section'?'元C08から切り出した厚さ1.2mmの接触部。変位倍率は1。':
      '説明用の時間・速度／実機未検証。固定部・巻線そのものは回転しません。';
    const part=assembly.parts.find(p=>p.id===$('focus-part').value);
    const role={fixed:'動かない側',rotating:'回転だけ・軸位置は固定',axial:'回転＋軸方向に動く',spring:'根元を保ち、先端が円盤に追随'}[motionRole(part)];
    $('part-description').textContent=`${part.label}：${role}。${part.is_reference?'独立参考形状で、現物適合の証明ではありません。':''}`;
  }
  function draw(now) {
    frameHandle=0;
    if (failed) return;
    try {
      if (state.playing) {
        if (lastTime!==null) state=transition(state,{type:'tick',delta:Math.min(.1,(now-lastTime)/1000)});
        lastTime=now;
        syncUI();
      } else lastTime=null;
      scene.apply(state);
      scene.render();
      const items=scene.labels();
      for (let i=0;i<spans.length;i+=1) {
        const item=items[i];
        spans[i].hidden=!item||!item[1].visible;
        if (item) {
          spans[i].textContent=item[0];
          spans[i].style.left=`${item[1].x}px`;spans[i].style.top=`${item[1].y}px`;
        }
      }
      const contact=scene.contactPoint();
      $('contact-label').hidden=state.explode>0||!poseAt(state.time).contact||!['section','schematic'].includes(state.view)||!contact.visible;
      $('contact-label').style.left=`${contact.x}px`;$('contact-label').style.top=`${contact.y}px`;
      if (state.playing) schedule();
    } catch (reason) {error(reason);}
  }
  function act(action) {
    try {
      const old=state;
      state=transition(state,action);lastTime=null;
      scene.apply(state);syncUI();
      if (state.view!==old.view) scene.home();
      else if (state.explode!==old.explode) scene.fit();
      schedule();
    } catch (reason) {error(reason);}
  }
  scene=createMotionScene(assembly,meshes,section,$('viewport'),schedule,error);
  $('play').addEventListener('click',()=>act({type:'play'}));
  $('reset-motion').addEventListener('click',()=>act({type:'reset'}));
  $('progress').addEventListener('input',event=>act({type:'seek',time:Number(event.target.value)}));
  $('explode').addEventListener('input',event=>act({type:'explode',value:Number(event.target.value)}));
  $('assemble').addEventListener('click',()=>act({type:'explode',value:0}));
  $('cutaway').addEventListener('change',event=>act({type:'cutaway',value:event.target.checked}));
  for (const b of document.querySelectorAll('[data-time]')) b.addEventListener('click',()=>act({type:'seek',time:Number(b.dataset.time),view:b.dataset.targetView}));
  for (const b of document.querySelectorAll('[data-view]')) b.addEventListener('click',()=>act({type:'view',value:b.dataset.view}));
  $('home').addEventListener('click',()=>{scene.home();schedule();});
  $('fit').addEventListener('click',()=>{scene.fit();schedule();});
  $('focus-part').addEventListener('change',event=>{scene.select(event.target.value);syncUI();schedule();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)act({type:'pause'});});
  matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',()=>act({type:'pause'}));
  new ResizeObserver(()=>{scene.resize();schedule();}).observe($('viewport'));
  for (const id of ['view-controls','motion-controls','inspection-controls']) $(id).disabled=false;
  $('loading').hidden=true;$('view-label').hidden=false;$('scene-note').hidden=false;
  $('viewport').setAttribute('aria-busy','false');
  scene.apply(state);scene.home();syncUI();schedule();
  window.c08Motion=Object.freeze({snapshot:()=>({state:{...state},pose:poseAt(state.time),...scene.snapshot()})});
  document.documentElement.dataset.motionState='ready';
}
