import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {jointLengthText, jointStack, validateEnclosure, validateEnclosureMesh} from './enclosure-contract.js';

const $ = selector => document.querySelector(selector);
const text = (selector, value) => { $(selector).textContent = value; };
const number = value => Number(value.toFixed(3));
const tuple = values => values.map(number).join(', ');

async function load(url, bytes = false) {
  const response = await fetch(url, {cache: 'no-cache', signal: AbortSignal.timeout(30000)});
  if (!response.ok) throw new Error(`${url} を読み込めません（HTTP ${response.status}）。ファイルを確認して再読み込みしてください。`);
  return bytes ? response.arrayBuffer() : response.json();
}

function color(part) {
  if (part.id.endsWith('_WINDING')) return 0xa7592f;
  if (part.id.startsWith('E_REF_BOARD_')) return 0x527f70;
  if (part.is_reference) return part.id.endsWith('_REF_WHEEL') ? 0x7394af : 0xb7c8ce;
  if (part.group === 'rotor') return 0x2e6697;
  if (['support', 'electronics'].includes(part.group)) return 0x376e58;
  return 0x788c9b;
}

function partName(part) {
  const names = [
    ['E_FRAME_SCREW_', 'フレーム・内部cornerの皿ねじ'],
    ['E_CAP_SCREW_', '外側coverの対角皿ねじ'],
    ['E_HOLDER_FIX_PCB_', 'PCB保持部・フレームの皿ねじ'],
    ['E_HOLDER_FIX_MPU_', 'MPU保持部・フレームの皿ねじ'],
    ['E_BOARD_SCREW_PCB_', 'PCBを挟む首下10 mmねじ'],
    ['E_BOARD_SCREW_MPU_', 'MPU参照板を挟む首下10 mmねじ'],
    ['E_HOLDER_PCB', 'PCBの三点支持保持部'],
    ['E_HOLDER_MPU', 'MPUの三点支持保持部'],
    ['E_REF_BOARD_PCB', 'PCB機械参照板・厚さは名目値'],
    ['E_REF_BOARD_MPU', 'MPU参考包絡・外形と穴径は仮定'],
    ['E_FRAME_MOTOR_', 'PCD126・motor側フレーム'],
    ['E_FRAME_BOARD_', '基板保持部を受けるフレーム'],
  ];
  return names.find(([prefix]) => part.id.startsWith(prefix))?.[1] || part.label;
}

export async function startEnclosure(onError) {
  const [data, bytes] = await Promise.all([load('./data/enclosure-assembly.json'), load('./data/enclosure-meshes.json', true)]);
  const assembly = validateEnclosure(data);
  if (!crypto.subtle) throw new Error('SHA-256を検証するためHTTPSまたはlocalhostで開いてください。');
  const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(n => n.toString(16).padStart(2, '0')).join('');
  if (sha !== assembly.mesh.sha256) throw new Error('筐体メッシュのSHA-256がCAD台帳と一致しません。再生成済みの公開セットを確認してください。');
  const model = validateEnclosureMesh(JSON.parse(new TextDecoder().decode(bytes)), assembly);
  const viewport = $('#enclosure-viewport');
  const scene = new THREE.Scene();
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setClearColor(0xeaf0f4);
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.localClippingEnabled = true;
  const plane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
  const canvas = renderer.domElement;
  canvas.id = 'enclosure-canvas';
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', '138 mmの名目筐体CAD。矢印キーで回転、プラス・マイナスでズーム。部品一覧から接合相手を選択できます。');
  viewport.prepend(canvas);
  const camera = new THREE.PerspectiveCamera(36, 1, 0.5, 5000);
  const controls = new OrbitControls(camera, canvas);
  // On-demand rendering: https://threejs.org/docs/pages/OrbitControls.html
  controls.autoRotate = false;
  controls.enableDamping = false;
  controls.minDistance = 70;
  controls.maxDistance = 3000;
  scene.add(new THREE.HemisphereLight(0xf5f9ff, 0x5f7480, 2.5));
  for (const [position, intensity] of [[[150, 100, 250], 3.2], [[-200, -150, 50], 1.4]]) {
    const light = new THREE.DirectionalLight(0xffffff, intensity);
    light.position.fromArray(position);
    scene.add(light);
  }
  const parts = new Map(assembly.parts.map(part => [part.id, part]));
  const joints = new Map(assembly.joints.map(row => [row.id, row]));
  const records = new Map();
  for (const row of model.parts) {
    const part = parts.get(row.id);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(row.positions, 3));
    geometry.setIndex(row.indices);
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    const material = new THREE.MeshStandardMaterial({color: color(part), roughness: 0.55, metalness: 0.18, flatShading: true,
      side: THREE.DoubleSide, transparent: true});
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.partId = part.id;
    scene.add(mesh);
    records.set(part.id, {part, mesh});
  }
  const state = {selected: 'E_FRAME_SCREW_PPP_X', joint: null, focus: 'all', explode: 0, section: false};
  let pending = false, frames = 0, failed = false;
  function render() {
    if (pending || failed) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      if (failed) return;
      renderer.render(scene, camera);
      frames += 1;
      canvas.dataset.rendered = 'true';
    });
  }
  function points() {
    const result = [];
    for (const {mesh} of records.values()) {
      const b = mesh.geometry.boundingBox;
      for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) {
        result.push(new THREE.Vector3(x, y, z).add(mesh.position));
      }
    }
    return result;
  }
  function fit() {
    const sphere = new THREE.Box3().setFromPoints(points()).getBoundingSphere(new THREE.Sphere());
    const direction = camera.position.clone().sub(controls.target).normalize();
    const halfAngle = Math.min(THREE.MathUtils.degToRad(camera.fov) / 2,
      Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2) * camera.aspect));
    controls.target.copy(sphere.center);
    camera.position.copy(sphere.center).addScaledVector(direction, 1.08 * sphere.radius / Math.sin(halfAngle));
    controls.update();
    camera.updateMatrixWorld(true);
    render();
  }
  function home() {
    controls.target.set(0, 0, 0);
    camera.position.set(260, 210, 270);
    controls.update();
    fit();
  }
  function relatedIds() {
    const joint = joints.get(state.joint);
    return joint ? [joint.fastener, ...jointStack(joint)].filter(id => id !== state.selected) : parts.get(state.selected)?.mates || [];
  }
  function updateVisuals() {
    const mates = new Set(relatedIds());
    for (const [id, {part, mesh}] of records) {
      mesh.position.fromArray(part.explode_mm).multiplyScalar(state.explode / 100);
      const chosen = id === state.selected, mate = mates.has(id);
      const focused = state.focus === 'all' ||
        state.focus === 'enclosure' && /^(?:E_FRAME_|E_CORNER_|E_CAP_SCREW_|[XYZ]_(?:POST|FRAME_|CARRIER))/.test(id) ||
        state.focus === 'electronics' && /^E_(?:HOLDER|REF_BOARD|SPACER|WASHER|BOARD_SCREW)/.test(id);
      const opacity = chosen || mate ? 1 : !focused ? 0.055 : part.is_reference ? 0.48 : 1;
      mesh.material.opacity = opacity;
      mesh.material.depthWrite = opacity === 1;
      mesh.material.color.setHex(chosen ? 0xb7802c : mate ? 0x277f89 : color(part));
      mesh.material.emissive.setHex(chosen ? 0x281902 : mate ? 0x03191c : 0);
      // Negative signed distance is clipped: https://threejs.org/docs/pages/Material.html#clippingPlanes
      mesh.material.clippingPlanes = state.section ? [plane] : [];
      mesh.renderOrder = opacity === 1 ? 0 : 1;
    }
    scene.updateMatrixWorld(true);
    canvas.dataset.selected = state.selected || '';
    canvas.dataset.joint = state.joint || '';
    canvas.dataset.highlighted = JSON.stringify([...mates]);
    canvas.dataset.explode = String(state.explode);
    canvas.dataset.section = String(state.section);
    text('#enclosure-view-state', `${state.explode ? `分解 ${state.explode}%（表示のみ）` : '組付け位置（名目）'}${state.section ? ' / X = 0 描画断面' : ''}`);
    render();
  }
  function fillParts() {
    const query = $('#enclosure-search').value.trim().toLowerCase();
    const select = $('#enclosure-part');
    select.replaceChildren();
    const matches = assembly.parts.filter(part => `${part.id} ${partName(part)}`.toLowerCase().includes(query));
    for (const part of matches) {
      const option = document.createElement('option');
      option.value = part.id;
      option.textContent = `${part.id} / ${partName(part)}`;
      select.append(option);
    }
    if (!matches.length) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = '該当する部品はありません';
      option.disabled = true;
      select.append(option);
    }
    text('#enclosure-selection-count', `${matches.length} / ${assembly.parts.length} CAD要素。部品数は購入数量ではありません。`);
    return matches;
  }
  function detail() {
    const part = parts.get(state.selected), joint = joints.get(state.joint);
    $('.joint-card').hidden = !part;
    if (!part) {
      text('#enclosure-part-id', '—');
      text('#enclosure-part-title', '部品未選択');
      text('#enclosure-part-kind', '検索条件に一致する部品がありません。条件を変更してください。');
      for (const id of ['fastener-id', 'screw-size', 'length', 'engagement', 'receiver', 'axis']) text(`#enclosure-${id}`, '—');
      text('#enclosure-chain-title', '接合相手は未選択');
      $('#enclosure-mates').replaceChildren();
      updateVisuals();
      return;
    }
    text('#enclosure-part-id', part.id);
    text('#enclosure-part-title', partName(part));
    text('#enclosure-part-kind', part.is_reference ? '参照形状 / 実部品への適合は未資格' :
      part.id.startsWith('E_') ? '独立作図した名目部品 / 製作未資格' : '変更していない公開C08形状 / 実機成立は未資格');
    text('#enclosure-fastener-id', joint?.fastener || 'ねじ以外の接続・関係部品');
    text('#enclosure-screw-size', joint ? `${joint.nominal_thread.split(';')[0].replace('x', '×')} / 名目ねじ` : '寸法・位置のスナップショット');
    text('#enclosure-length', joint ? jointLengthText(joint) : '対象外');
    text('#enclosure-engagement', joint ? `${number(joint.frame_grip_mm)} / ${number(joint.engagement_mm)} mm` : '対象外');
    text('#enclosure-receiver', joint ? `${joint.receiver} / ${joint.receiver_end === 'through' ?
      `通し・突出 ${number(joint.protrusion_mm)} mm` : `止まり・底余裕 ${number(joint.bottom_margin_mm)} mm`}` : '関係部品を下に表示');
    text('#enclosure-axis', joint ? `axis [${tuple(joint.axis)}] / seat [${tuple(joint.seat_point_mm)}] mm` : `bbox [${tuple(part.bbox_mm)}] mm`);
    text('#enclosure-chain-title', joint ? 'ねじが挟む順序（頭側から）' : '関係する部品');
    const list = $('#enclosure-mates');
    list.replaceChildren();
    for (const id of joint ? jointStack(joint) : part.mates) {
      const target = parts.get(id), button = document.createElement('button');
      button.type = 'button';
      button.className = 'mate-button';
      button.dataset.mate = id;
      button.dataset.reference = String(target.is_reference);
      const label = document.createElement('span'), code = document.createElement('small');
      label.textContent = partName(target);
      code.textContent = id;
      button.append(label, code);
      button.addEventListener('click', () => select(id));
      list.append(button);
    }
    updateVisuals();
  }
  function synchronizeSelection(matches) {
    const part = parts.get(state.selected);
    const dropdown = $('#enclosure-part');
    if (part && !matches.some(row => row.id === part.id)) {
      const option = document.createElement('option');
      option.value = part.id;
      option.textContent = `選択中（検索外）: ${part.id} / ${partName(part)}`;
      dropdown.append(option);
      text('#enclosure-selection-count', `${matches.length} / ${assembly.parts.length} CAD要素。検索外の選択部品を併記しています。`);
    }
    dropdown.value = state.selected || '';
    dropdown.disabled = !part && matches.length === 0;
    const selectJoint = $('#enclosure-joint');
    selectJoint.replaceChildren();
    const jointIds = part?.joint_ids || [];
    for (const jointId of jointIds) {
      const option = document.createElement('option');
      option.value = jointId;
      option.textContent = joints.get(jointId).fastener;
      selectJoint.append(option);
    }
    state.joint = jointIds.includes(state.joint) ? state.joint : jointIds[0] || null;
    if (!state.joint) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = part ? 'ねじ以外の接続・関係部品' : '部品未選択';
      selectJoint.append(option);
    }
    selectJoint.value = state.joint || '';
    selectJoint.disabled = jointIds.length === 0;
    detail();
  }
  function select(id) {
    if (!parts.has(id)) throw new Error('選択した筐体部品は存在しません。');
    state.selected = id;
    synchronizeSelection(fillParts());
  }
  $('#enclosure-search').addEventListener('input', () => {
    const matches = fillParts();
    if (!matches.some(part => part.id === state.selected)) state.selected = matches[0]?.id || null;
    synchronizeSelection(matches);
  });
  $('#enclosure-part').addEventListener('change', event => { if (event.target.value) select(event.target.value); });
  $('#enclosure-joint').addEventListener('change', event => { state.joint = event.target.value || null; detail(); });
  $('#enclosure-explode').addEventListener('input', event => {
    state.explode = Number(event.target.value);
    text('#enclosure-explode-value', `${state.explode}%`);
    updateVisuals();
    fit();
  });
  $('#enclosure-section').addEventListener('change', event => { state.section = event.target.checked; updateVisuals(); });
  $('#enclosure-fit').addEventListener('click', fit);
  function setFocus(value) {
    state.focus = value;
    for (const button of document.querySelectorAll('[data-focus]')) button.setAttribute('aria-pressed', String(button.dataset.focus === value));
    select(value === 'electronics' ? 'E_BOARD_SCREW_PCB_0' : 'E_FRAME_SCREW_PPP_X');
    home();
  }
  for (const button of document.querySelectorAll('[data-focus]')) {
    button.disabled = false;
    button.addEventListener('click', () => setFocus(button.dataset.focus));
  }
  $('#enclosure-reset').addEventListener('click', () => {
    state.explode = 0;
    state.section = false;
    $('#enclosure-explode').value = '0';
    $('#enclosure-section').checked = false;
    $('#enclosure-search').value = '';
    text('#enclosure-explode-value', '0%');
    setFocus('all');
  });
  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
  let down;
  canvas.addEventListener('pointerdown', event => { down = [event.clientX, event.clientY]; });
  canvas.addEventListener('pointercancel', () => { down = null; });
  canvas.addEventListener('pointerup', event => {
    if (!down || Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 5) { down = null; return; }
    down = null;
    const rect = canvas.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const meshes = [...records.values()].map(row => row.mesh).filter(mesh => mesh.material.opacity >= 0.1);
    const hits = raycaster.intersectObjects(meshes, false).filter(hit => !state.section || plane.distanceToPoint(hit.point) >= 0);
    const hit = hits.find(row => row.object.material.opacity >= 0.9) || hits[0];
    if (hit) select(hit.object.userData.partId);
  });
  canvas.addEventListener('keydown', event => {
    const spherical = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
    if (event.key === 'ArrowLeft') spherical.theta -= Math.PI / 24;
    else if (event.key === 'ArrowRight') spherical.theta += Math.PI / 24;
    else if (event.key === 'ArrowUp') spherical.phi = Math.max(0.04, spherical.phi - Math.PI / 24);
    else if (event.key === 'ArrowDown') spherical.phi = Math.min(Math.PI - 0.04, spherical.phi + Math.PI / 24);
    else if (['+', '='].includes(event.key)) spherical.radius = Math.max(controls.minDistance, spherical.radius / 1.12);
    else if (['-', '_'].includes(event.key)) spherical.radius = Math.min(controls.maxDistance, spherical.radius * 1.12);
    else if (event.key === 'Home') { event.preventDefault(); fit(); return; }
    else return;
    event.preventDefault();
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    controls.update();
    render();
  });
  function resize() {
    renderer.setSize(viewport.clientWidth, viewport.clientHeight, false);
    camera.aspect = viewport.clientWidth / viewport.clientHeight;
    camera.updateProjectionMatrix();
    if (frames) fit(); else render();
  }
  new ResizeObserver(resize).observe(viewport);
  controls.addEventListener('change', render);
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    failed = true;
    controls.enabled = false;
    onError(new Error('WebGLの描画接続が失われました。ほかの3D画面を閉じ、再読み込みしてください。'));
  });
  $('#enclosure-loading').hidden = true;
  $('#enclosure-caption').hidden = false;
  $('#enclosure-controls').disabled = false;
  $('#enclosure-parts-controls').disabled = false;
  viewport.setAttribute('aria-busy', 'false');
  text('#enclosure-count', `138 × 138 × 138 / ${assembly.parts.length} CAD要素`);
  resize();
  select(state.selected);
  home();
  window.enclosureInspection = Object.freeze({snapshot() {
    scene.updateMatrixWorld(true);
    camera.updateMatrixWorld(true);
    const projected = points().map(point => point.project(camera));
    const seat = assembly.joints.find(row => row.fastener === 'E_FRAME_SCREW_PPP_X').seat_point_mm;
    const point = new THREE.Vector3(...seat).add(records.get('E_FRAME_SCREW_PPP_X').mesh.position).project(camera);
    const rect = canvas.getBoundingClientRect();
    return {...state, frames, partCount: records.size, referenceCount: assembly.reference_part_count,
      fastenerCount: assembly.joints.length, autoRotate: controls.autoRotate, camera: camera.position.toArray(),
      drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
      renderedMeshCount: scene.children.filter(object => object.isMesh).length,
      materialHighlights: [...records].filter(([, record]) => record.mesh.material.color.getHex() === 0x277f89).map(([id]) => id),
      selectedMaterialColor: records.get(state.selected)?.mesh.material.color.getHex() ?? null,
      highlighted: relatedIds(), meshSha256: sha,
      screwPickPoint: {id: 'E_FRAME_SCREW_PPP_X', x: rect.left + (point.x + 1) * rect.width / 2, y: rect.top + (1 - point.y) * rect.height / 2},
      projectedBounds: [Math.min(...projected.map(p => p.x)), Math.min(...projected.map(p => p.y)),
        Math.max(...projected.map(p => p.x)), Math.max(...projected.map(p => p.y))]};
  }});
  document.documentElement.dataset.enclosureState = 'ready';
}
