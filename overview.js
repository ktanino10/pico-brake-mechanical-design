import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {validateAssembly, validateMesh} from './contract.js';

const $ = selector => document.querySelector(selector);
const setText = (selector, value) => { $(selector).textContent = value; };
const KINDS = new Set(['plate', 'pcb', 'tube', 'screw', 'nut', 'box', 'band']);
const SECTIONS = new Set(['case', 'mount', 'pcb', 'battery']);

export function validateOverview(layout) {
  if (layout?.schema !== 'brake-reference-overview-v1' || layout.units !== 'mm') throw new Error('参考配置の形式・単位が一致しません。');
  for (const key of ['whole_fit', 'build_ready', 'physical_ready', 'actual_board_data', 'original_pico_geometry_used']) {
    if (layout[key] !== false) throw new Error(`参考図の未資格状態が不正です: ${key}`);
  }
  if (!Array.isArray(layout.parts) || layout.parts.length !== layout.reference_part_count || layout.parts.length === 0) throw new Error('参考部品数が一致しません。');
  const ids = new Set(['BASE_X', 'BASE_Y', 'BASE_Z']);
  for (const part of layout.parts) {
    if (!/^REF_[A-Z0-9_]+$/.test(part.id) || ids.has(part.id) || !KINDS.has(part.kind) || !SECTIONS.has(part.section)) throw new Error('未承認の参考部品です。');
    if (part.origin !== 'independently-authored-primitive' || part.source_geometry !== null ||
      part.is_reference !== true || part.included_in_brake_cad !== false || part.tightening_torque_Nm !== null) {
      throw new Error(`参考部品の出所・CAD範囲が不正です: ${part.id}`);
    }
    for (const field of ['position_mm', 'explode_mm']) {
      if (!Array.isArray(part[field]) || part[field].length !== 3 || !part[field].every(Number.isFinite)) throw new Error(`参考部品の位置が不正です: ${part.id}`);
    }
    const requiredLength = {plate: 3, pcb: 3, tube: 3, screw: 4, nut: 3, box: 3, band: 5}[part.kind];
    if (!Array.isArray(part.dimensions_mm) || part.dimensions_mm.length !== requiredLength || !part.dimensions_mm.every(value => Number.isFinite(value) && value > 0) ||
      !['X', 'Y', 'Z'].includes(part.orientation) || !Array.isArray(part.mates)) throw new Error(`参考部品の寸法が不正です: ${part.id}`);
    if (['tube', 'nut'].includes(part.kind) && part.dimensions_mm[1] >= part.dimensions_mm[0]) throw new Error('参考部品の内径が外径以上です。');
    if (part.kind === 'band' && (part.dimensions_mm[3] >= part.dimensions_mm[0] || part.dimensions_mm[4] >= part.dimensions_mm[1])) throw new Error('参考帯の内側寸法が不正です。');
    for (const hole of part.holes || []) {
      if (hole.length !== 3 || !hole.every(Number.isFinite) || hole[2] <= 0 ||
          Math.abs(hole[0]) + hole[2] > part.dimensions_mm[0] / 2 ||
          Math.abs(hole[1]) + hole[2] > part.dimensions_mm[1] / 2) throw new Error(`参考穴が板の範囲外です: ${part.id}`);
    }
    ids.add(part.id);
  }
  for (const part of layout.parts) {
    if (part.mates.some(id => !ids.has(id) || id === part.id)) throw new Error(`固定先が存在しません: ${part.id}`);
  }
  if (!Array.isArray(layout.steps) || layout.steps.map(step => step.id).join(',') !== 'all,case,mount,pcb,battery') throw new Error('表示段階の定義が一致しません。');
  return layout;
}

async function load(url, bytes = false) {
  const response = await fetch(url, {cache: 'no-cache', signal: AbortSignal.timeout(20000)});
  if (!response.ok) throw new Error(`${url} を読み込めません（HTTP ${response.status}）。ファイルを確認して再読み込みしてください。`);
  return bytes ? response.arrayBuffer() : response.json();
}

function rectangle(width, height) {
  const shape = new THREE.Shape();
  shape.moveTo(-width/2, -height/2);
  shape.lineTo(width/2, -height/2);
  shape.lineTo(width/2, height/2);
  shape.lineTo(-width/2, height/2);
  shape.closePath();
  return shape;
}

function extrude(shape, thickness) {
  const geometry = new THREE.ExtrudeGeometry(shape, {depth: thickness, bevelEnabled: false, curveSegments: 20});
  geometry.translate(0, 0, -thickness/2);
  return geometry;
}

function roundHole(shape, x, y, radius) {
  const hole = new THREE.Path();
  hole.absarc(x, y, radius, 0, Math.PI * 2, true);
  shape.holes.push(hole);
}

export function referenceGeometries(part) {
  const d = part.dimensions_mm;
  if (part.kind === 'plate' || part.kind === 'pcb') {
    const shape = rectangle(d[0], d[1]);
    for (const [x, y, radius] of part.holes || []) roundHole(shape, x, y, radius);
    return [extrude(shape, d[2])];
  }
  if (part.kind === 'box') return [new THREE.BoxGeometry(...d)];
  if (part.kind === 'tube' || part.kind === 'nut') {
    const shape = new THREE.Shape();
    if (part.kind === 'tube') shape.absarc(0, 0, d[0]/2, 0, Math.PI * 2, false);
    else {
      const radius = d[0] / Math.sqrt(3);
      for (let i = 0; i < 6; i += 1) {
        const x = radius * Math.cos(i*Math.PI/3), y = radius * Math.sin(i*Math.PI/3);
        if (i === 0) shape.moveTo(x, y); else shape.lineTo(x, y);
      }
      shape.closePath();
    }
    roundHole(shape, 0, 0, d[1]/2);
    return [extrude(shape, d[2])];
  }
  if (part.kind === 'band') {
    const shape = rectangle(d[0], d[1]);
    const hole = new THREE.Path();
    hole.moveTo(-d[3]/2, -d[4]/2);
    hole.lineTo(-d[3]/2, d[4]/2);
    hole.lineTo(d[3]/2, d[4]/2);
    hole.lineTo(d[3]/2, -d[4]/2);
    hole.closePath();
    shape.holes.push(hole);
    return [extrude(shape, d[2])];
  }
  const shaft = new THREE.CylinderGeometry(d[0]/2, d[0]/2, d[1], 24);
  shaft.rotateX(Math.PI/2);
  shaft.translate(0, 0, d[1]/2);
  const head = new THREE.CylinderGeometry(d[2]/2, d[2]/2, d[3], 24);
  head.rotateX(Math.PI/2);
  head.translate(0, 0, -d[3]/2);
  return [shaft, head];
}

function referenceColor(part) {
  if (part.kind === 'pcb') return 0x23795c;
  if (part.kind === 'screw' || part.kind === 'nut') return 0x718493;
  if (part.id === 'REF_BATTERY') return 0xa5793a;
  if (part.kind === 'band') return 0x354956;
  if (part.section === 'pcb') return 0xc2b895;
  return part.section === 'case' ? 0x9eb7c5 : 0x54796d;
}

function baseColor(part) {
  if (part.id === 'WINDING') return 0xb5683d;
  if (part.group === 'rotor') return 0x3672a3;
  if (part.group === 'support') return 0x4d806b;
  return 0x8295a3;
}

export async function startOverview(onError) {
  const [layoutData, assemblyData, bytes] = await Promise.all([
    load('./data/overview-layout.json'), load('./data/assembly.json'), load('./data/meshes.json', true),
  ]);
  const layout = validateOverview(layoutData), assembly = validateAssembly(assemblyData);
  if (!crypto.subtle) throw new Error('SHA-256を検証するためHTTPSまたはlocalhostで開いてください。');
  const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2, '0')).join('');
  if (sha !== layout.base_mesh_sha256 || sha !== assembly.mesh.sha256 || layout.base_parts_per_axis !== assembly.parts.length) throw new Error('参考図と既存ブレーキの版が一致しません。');
  const model = validateMesh(JSON.parse(new TextDecoder().decode(bytes)), assembly);
  const viewport = $('#overview-viewport');
  const scene = new THREE.Scene();
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setClearColor(0xeaf0f4);
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  const canvas = renderer.domElement;
  canvas.id = 'overview-canvas';
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', '筐体・基板・電池の参考全体図。ドラッグまたは矢印キーで回転し、部品一覧からも選択できます。');
  viewport.prepend(canvas);
  const camera = new THREE.PerspectiveCamera(36, 1, 0.5, 4000);
  const controls = new OrbitControls(camera, canvas);
  controls.autoRotate = false;
  controls.enableDamping = false;
  controls.minDistance = 70;
  controls.maxDistance = 1800;
  scene.add(new THREE.HemisphereLight(0xf5f9ff, 0x5f7480, 2.5));
  const light = new THREE.DirectionalLight(0xffffff, 3.2);
  light.position.set(150, 100, 250);
  scene.add(light);
  const fill = new THREE.DirectionalLight(0xe0edf8, 1.4);
  fill.position.set(-200, -150, 50);
  scene.add(fill);
  const records = new Map(), pickables = [];
  const geometries = new Map();
  const baseParts = new Map(assembly.parts.map(part => [part.id, part]));
  for (const part of model.parts) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(part.positions, 3));
    geometry.setIndex(part.indices);
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    geometries.set(part.id, geometry);
  }
  function addMesh(record, geometry, color, outline) {
    geometry.computeBoundingBox();
    const material = new THREE.MeshStandardMaterial({color, roughness: 0.55, metalness: 0.18, side: THREE.DoubleSide, transparent: true});
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.entityId = record.data.id;
    record.group.add(mesh);
    record.meshes.push(mesh);
    pickables.push(mesh);
    if (outline) {
      const edge = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28),
        new THREE.LineBasicMaterial({color: 0x526c7c, transparent: true, opacity: 0.35}));
      mesh.add(edge);
      record.edges.push(edge);
    }
  }
  for (const axis of ['Z', 'X', 'Y']) {
    const group = new THREE.Group();
    group.quaternion.fromArray(assembly.axis_quaternions_xyzw[axis]);
    const data = {id: `BASE_${axis}`, label: `${axis}軸の公開ブレーキ部`, kind: 'base', section: 'mount',
      dimensions_mm: [116], mates: layout.parts.filter(p => p.id.startsWith(`REF_MODULE_POST_${axis}_`)).map(p => p.id),
      note: '公開済みの149部品を同じ尺度・軸変換で表示。元全機ではなく、既存CADの参照円盤・支持リングを含みます。'};
    const offset = new THREE.Vector3(0, 0, -28).applyQuaternion(group.quaternion);
    const record = {data, group, meshes: [], edges: [], base: new THREE.Vector3(), offset};
    for (const part of model.parts) addMesh(record, geometries.get(part.id), baseColor(baseParts.get(part.id)), false);
    records.set(data.id, record);
    scene.add(group);
  }
  for (const part of layout.parts) {
    const group = new THREE.Group();
    group.position.fromArray(part.position_mm);
    group.quaternion.fromArray(assembly.axis_quaternions_xyzw[part.orientation]);
    if (part.flip) group.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI));
    const record = {data: part, group, meshes: [], edges: [], base: group.position.clone(),
      offset: new THREE.Vector3().fromArray(part.explode_mm)};
    for (const geometry of referenceGeometries(part)) addMesh(record, geometry, referenceColor(part), true);
    records.set(part.id, record);
    scene.add(group);
  }
  const state = {step: 'all', selected: 'REF_PCB_CTRL', explode: 0, transparent: true, brakes: true};
  const labels = [];
  for (const [id, title] of [['REF_PCB_CTRL', '制御基板（仮）'], ['REF_PCB_DRIVE', '駆動基板（仮）'], ['REF_BATTERY', '電池（仮）']]) {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'overview-label'; button.textContent = title;
    button.setAttribute('aria-label', `${title}を選択`);
    button.addEventListener('click', () => select(id));
    viewport.append(button);
    labels.push({id, button});
  }
  function counterparts(id) {
    const part = records.get(id).data;
    return part.mates.length ? part.mates : [...records.values()].filter(r => r.data.mates.includes(id)).map(r => r.data.id);
  }
  let pending = false, frames = 0;
  function requestRender() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false; renderer.render(scene, camera); frames += 1; canvas.dataset.rendered = 'true';
      for (const label of labels) {
        const record = records.get(label.id), point = record.group.position.clone().project(camera);
        const relevant = state.step === 'all' || record.data.section === state.step || state.selected === label.id;
        label.button.hidden = !relevant || point.z < -1 || point.z > 1 || Math.abs(point.x) > 1 || Math.abs(point.y) > 1;
        label.button.style.left = `${(point.x+1)*viewport.clientWidth/2}px`;
        label.button.style.top = `${(1-point.y)*viewport.clientHeight/2-18}px`;
        label.button.setAttribute('aria-pressed', String(state.selected === label.id));
      }
    });
  }
  function corners() {
    const points = [];
    for (const record of records.values()) {
      if (!record.group.visible) continue;
      for (const mesh of record.meshes) {
        const box = mesh.geometry.boundingBox;
        for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
          points.push(new THREE.Vector3(x, y, z).applyMatrix4(mesh.matrixWorld));
        }
      }
    }
    return points;
  }
  function fit() {
    scene.updateMatrixWorld(true);
    const points = corners();
    const center = new THREE.Box3().setFromPoints(points).getCenter(new THREE.Vector3());
    const direction = camera.position.clone().sub(controls.target).normalize();
    const right = new THREE.Vector3().crossVectors(camera.up, direction).normalize();
    if (right.lengthSq() < 0.1) right.set(1, 0, 0);
    const up = new THREE.Vector3().crossVectors(direction, right).normalize();
    const verticalTan = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2), horizontalTan = verticalTan * camera.aspect;
    let distance = controls.minDistance;
    for (const point of points) {
      const v = point.clone().sub(center), depth = v.dot(direction);
      distance = Math.max(distance, depth + 1.12 * Math.abs(v.dot(right)) / horizontalTan, depth + 1.12 * Math.abs(v.dot(up)) / verticalTan);
    }
    controls.target.copy(center);
    camera.position.copy(center).addScaledVector(direction, distance);
    controls.update();
    camera.updateMatrixWorld(true);
    requestRender();
  }
  function home(top = false) {
    camera.up.set(0, 1, 0);
    controls.target.set(0, 0, 0);
    camera.position.set(...(top ? [0, -0.01, 450] : [280, 230, 250]));
    controls.update();
    fit();
  }
  function updateVisuals() {
    const selected = records.get(state.selected).data;
    const mates = new Set(counterparts(selected.id));
    for (const [id, record] of records) {
      const part = record.data;
      record.group.visible = part.kind !== 'base' || state.brakes;
      record.group.position.copy(record.base).addScaledVector(record.offset, state.explode/100);
      const chosen = id === state.selected, mate = mates.has(id);
      const relevant = state.step === 'all' || part.section === state.step || chosen || mate;
      for (const mesh of record.meshes) {
        let alpha = part.kind === 'base' ? 0.56 : 1;
        if (part.kind === 'plate' && state.transparent) alpha = 0.12;
        if (!relevant) alpha = 0.045;
        if (chosen && part.kind === 'base') alpha = 0.8;
        mesh.material.opacity = alpha;
        mesh.material.depthWrite = alpha === 1;
        mesh.material.emissive.setHex(chosen ? 0x392504 : mate ? 0x043f44 : 0);
        mesh.renderOrder = alpha === 1 ? 0 : part.kind === 'plate' ? 3 : 1;
      }
      for (const edge of record.edges) {
        edge.material.color.setHex(chosen ? 0xb57516 : mate ? 0x087887 : 0x527080);
        edge.material.opacity = chosen || mate ? 0.9 : relevant ? 0.25 : 0.06;
      }
    }
    scene.updateMatrixWorld(true);
    canvas.dataset.selected = state.selected;
    canvas.dataset.step = state.step;
    canvas.dataset.explode = String(state.explode);
    canvas.dataset.brakes = String(state.brakes);
    canvas.dataset.highlighted = JSON.stringify([...mates]);
    setText('#overview-view-state', state.explode ? `分解 ${state.explode}%（表示のみ）` : '組付け位置（仮）');
    setText('#overview-count', `${layout.parts.length} reference items + ${state.brakes ? assembly.parts.length * 3 : 0} brake parts`);
    requestRender();
  }
  function select(id) {
    const record = records.get(id);
    if (!record) throw new Error('選択した参考部品が存在しません。');
    if (record.data.kind === 'base' && !state.brakes) {
      state.brakes = true;
      $('#show-brakes').checked = true;
    }
    state.selected = id;
    $('#overview-part-select').value = id;
    const part = record.data;
    setText('#overview-part-id', id);
    setText('#overview-part-title', part.label);
    setText('#overview-part-kind', part.kind === 'base' ? '既存の公開ブレーキCAD / 原全機ではない' : '独立した参考形状 / 実寸・取付は未確定');
    let dimensions = part.dimensions_mm.map(n => Number(n.toFixed(2))).join(' × ') + ' mm（仮）';
    if (part.kind === 'base') dimensions = '149部品 / 公開円盤外径116 mm';
    if (part.kind === 'screw') dimensions = `M${part.dimensions_mm[0]}相当 / 長さ${part.dimensions_mm[1]} mmは表示例`;
    if (part.kind === 'tube') dimensions = `外径${part.dimensions_mm[0]} / 高さ${part.dimensions_mm[2]} mm（仮）`;
    if (part.kind === 'pcb') dimensions += ` / 穴ピッチ ${part.hole_pitch_mm.join(' × ')} mm（仮）`;
    setText('#overview-dimensions', dimensions);
    setText('#overview-part-note', part.note);
    const container = $('#overview-mates');
    container.replaceChildren();
    const counterpartIds = counterparts(id);
    for (const counterpart of counterpartIds) {
      const target = records.get(counterpart).data;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'mate-button'; button.dataset.mate = counterpart;
      const title = document.createElement('span'); title.textContent = target.label;
      const code = document.createElement('small'); code.textContent = counterpart;
      button.append(title, code);
      button.addEventListener('click', () => select(counterpart));
      container.append(button);
    }
    updateVisuals();
  }
  const dropdown = $('#overview-part-select');
  dropdown.replaceChildren();
  for (const {data} of records.values()) {
    const option = document.createElement('option');
    option.value = data.id; option.textContent = `${data.label} / ${data.id}`;
    dropdown.append(option);
  }
  dropdown.addEventListener('change', event => select(event.target.value));
  for (const button of document.querySelectorAll('button[data-step]')) {
    button.disabled = false;
    button.addEventListener('click', () => {
      state.step = button.dataset.step;
      for (const other of document.querySelectorAll('button[data-step]')) other.setAttribute('aria-pressed', String(other === button));
      const step = layout.steps.find(row => row.id === state.step);
      setText('#stage-title', step.title); setText('#stage-description', step.description);
      select({all: 'REF_PCB_CTRL', case: 'REF_CASE_TOP', mount: 'BASE_Z', pcb: 'REF_PCB_SCREW_CTRL_0', battery: 'REF_BATTERY'}[state.step]);
      home(state.step === 'pcb');
    });
  }
  $('#overview-explode').addEventListener('input', event => {
    state.explode = Number(event.target.value); setText('#overview-explode-value', `${state.explode}%`); updateVisuals(); fit();
  });
  $('#case-transparent').addEventListener('change', event => { state.transparent = event.target.checked; updateVisuals(); });
  $('#show-brakes').addEventListener('change', event => {
    state.brakes = event.target.checked;
    if (!state.brakes && state.selected.startsWith('BASE_')) select('REF_PCB_CTRL');
    else updateVisuals();
    fit();
  });
  $('#overview-fit').addEventListener('click', fit);
  $('#overview-top').addEventListener('click', () => home(true));
  $('#overview-reset').addEventListener('click', () => {
    Object.assign(state, {step: 'all', selected: 'REF_PCB_CTRL', explode: 0, transparent: true, brakes: true});
    $('#overview-explode').value = '0'; setText('#overview-explode-value', '0%');
    $('#case-transparent').checked = true; $('#show-brakes').checked = true;
    for (const button of document.querySelectorAll('button[data-step]')) button.setAttribute('aria-pressed', String(button.dataset.step === 'all'));
    setText('#stage-title', layout.steps[0].title); setText('#stage-description', layout.steps[0].description);
    select('REF_PCB_CTRL'); home();
  });
  let down;
  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
  canvas.addEventListener('pointerdown', event => { down = [event.clientX, event.clientY]; });
  canvas.addEventListener('pointercancel', () => { down = null; });
  canvas.addEventListener('pointerup', event => {
    if (!down || Math.hypot(event.clientX-down[0], event.clientY-down[1]) > 5) { down = null; return; }
    down = null;
    const rect = canvas.getBoundingClientRect();
    pointer.set((event.clientX-rect.left)/rect.width*2-1, -(event.clientY-rect.top)/rect.height*2+1);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickables.filter(mesh => mesh.parent.visible && mesh.material.opacity > 0.1), false);
    const hit = hits.find(row => row.object.material.opacity >= 0.5) || hits[0];
    if (hit) select(hit.object.userData.entityId);
  });
  canvas.addEventListener('keydown', event => {
    const spherical = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
    if (event.key === 'ArrowLeft') spherical.theta -= Math.PI/24;
    else if (event.key === 'ArrowRight') spherical.theta += Math.PI/24;
    else if (event.key === 'ArrowUp') spherical.phi = Math.max(0.04, spherical.phi-Math.PI/24);
    else if (event.key === 'ArrowDown') spherical.phi = Math.min(Math.PI-0.04, spherical.phi+Math.PI/24);
    else if (['+', '='].includes(event.key)) spherical.radius = Math.max(controls.minDistance, spherical.radius/1.12);
    else if (['-', '_'].includes(event.key)) spherical.radius = Math.min(controls.maxDistance, spherical.radius*1.12);
    else if (event.key === 'Home') { event.preventDefault(); fit(); return; }
    else return;
    event.preventDefault();
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    controls.update(); requestRender();
  });
  function resize() {
    const width = viewport.clientWidth, height = viewport.clientHeight;
    renderer.setSize(width, height, false); camera.aspect = width/height; camera.updateProjectionMatrix(); requestRender();
  }
  controls.addEventListener('change', requestRender);
  new ResizeObserver(resize).observe(viewport);
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); onError(new Error('WebGLの描画接続が失われました。ほかの3D画面を閉じ、再読み込みしてください。')); });
  $('#overview-loading').hidden = true; $('#overview-caption').hidden = false;
  $('#overview-controls').disabled = false; $('#overview-part-controls').disabled = false;
  viewport.setAttribute('aria-busy', 'false');
  setText('#stage-description', layout.steps[0].description);
  resize(); select(state.selected); home();
  window.brakeOverview = Object.freeze({snapshot() {
    const projected = corners().map(point => point.project(camera));
    const bolt = records.get('REF_CASE_SCREW_TOP_0');
    const boltPoint = new THREE.Vector3(0, 0, -bolt.data.dimensions_mm[3]/2).applyMatrix4(bolt.group.matrixWorld).project(camera);
    const rect = canvas.getBoundingClientRect();
    return {selected: state.selected, step: state.step, explode: state.explode, showBrakes: state.brakes,
      transparentCase: state.transparent, referenceItems: layout.parts.length,
      brakeParts: state.brakes ? assembly.parts.length*3 : 0, frames,
      drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
      camera: camera.position.toArray(), autoRotate: controls.autoRotate,
      referenceScrewPickPoint: {id: bolt.data.id, x: rect.left + (boltPoint.x+1)*rect.width/2, y: rect.top + (1-boltPoint.y)*rect.height/2},
      projectedBounds: [Math.min(...projected.map(p=>p.x)), Math.min(...projected.map(p=>p.y)), Math.max(...projected.map(p=>p.x)), Math.max(...projected.map(p=>p.y))]};
  }});
  document.documentElement.dataset.overviewState = 'ready';
}
