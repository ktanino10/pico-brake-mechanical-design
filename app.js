import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {instanceId, torqueText, validateAssembly, validateMesh} from './contract.js';

const $ = selector => document.querySelector(selector);
const COLORS = {steel: 0x8798a5, copper: 0xb5683d, blue: 0x3672a3, green: 0x4d806b,
  reference: 0xa2b4c1, selected: 0xb57c29, mate: 0x167586, neutral: 0xb8c3cb};

async function load(url, responseType = 'json') {
  const response = await fetch(url, {signal: AbortSignal.timeout(20000), cache: 'no-cache'});
  if (!response.ok) throw new Error(`${url} を読み込めません（HTTP ${response.status}）。公開セットのファイルを確認して再読み込みしてください。`);
  return responseType === 'bytes' ? response.arrayBuffer() : response.json();
}

function colorFor(part) {
  if (part.is_reference) return COLORS.reference;
  if (part.id === 'WINDING' || part.material_code === 'C110-copper') return COLORS.copper;
  if (part.group === 'rotor') return COLORS.blue;
  if (part.group === 'support') return COLORS.green;
  if (part.material_code === 'PEEK') return 0xc3b28a;
  if (part.group === 'wiring') return 0x596c78;
  return COLORS.steel;
}

function text(selector, value) { $(selector).textContent = value; }

export async function start(onError) {
  const assembly = validateAssembly(await load('./data/assembly.json'));
  const release = await load('./data/checksums.json');
  if (typeof release.downloads_ready !== 'boolean') throw new Error('公開CADの検査状態を確認できません。公開セットを取り直してください。');
  for (const link of document.querySelectorAll('.download-buttons a')) {
    link.setAttribute('aria-disabled', String(!release.downloads_ready));
    link.addEventListener('click', event => { if (!release.downloads_ready) event.preventDefault(); });
  }
  $('#download-status').hidden = release.downloads_ready;
  if (!release.downloads_ready) text('#download-status', `${release.reason} 確認が完了した後、再読み込みしてください。`);
  const meshBytes = await load('./data/meshes.json', 'bytes');
  if (!crypto.subtle) throw new Error('この接続ではモデルのSHA-256を検証できません。HTTPSまたはlocalhostで開いてください。');
  const meshHash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', meshBytes))]
    .map(value => value.toString(16).padStart(2, '0')).join('');
  if (meshHash !== assembly.mesh.sha256) throw new Error('メッシュのSHA-256が部品表と一致しません。異なる版を混ぜず、公開セットを取り直してください。');
  const meshData = validateMesh(JSON.parse(new TextDecoder().decode(meshBytes)), assembly);
  const parts = new Map(assembly.parts.map(part => [part.id, part]));
  const viewport = $('#viewport');
  const renderer = new THREE.WebGLRenderer({antialias: true, alpha: false});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0xeaf0f4);
  renderer.localClippingEnabled = true;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  const canvas = renderer.domElement;
  canvas.id = 'assembly-canvas';
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', 'ブレーキ組立の3D。ドラッグまたは矢印キーで回転、プラス・マイナスでズーム。部品選択は右の一覧でもできます。');
  viewport.prepend(canvas);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.5, 4000);
  camera.up.set(0, 1, 0);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false;
  controls.autoRotate = false;
  controls.minDistance = 35;
  controls.maxDistance = 1300;
  controls.enablePan = true;
  controls.zoomSpeed = 0.8;
  scene.add(new THREE.HemisphereLight(0xf4f8ff, 0x647783, 2.4));
  const key = new THREE.DirectionalLight(0xffffff, 3.2);
  key.position.set(100, 180, -200);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xe6f1ff, 1.5);
  fill.position.set(-180, -60, 100);
  scene.add(fill);
  const grid = new THREE.GridHelper(180, 18, 0xb3c2cd, 0xd2dce3);
  grid.rotation.x = Math.PI / 2;
  grid.position.z = -71;
  grid.material.transparent = true;
  grid.material.opacity = 0.4;
  grid.material.depthWrite = false;
  scene.add(grid);
  const groups = new Map();
  const objects = new Map();
  const renderMeshes = [];
  const geometries = new Map();
  const clip = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
  for (const item of meshData.parts) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(item.positions, 3));
    geometry.setIndex(item.indices);
    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();
    geometry.computeBoundingBox();
    geometries.set(item.id, {surface: geometry, edges: new THREE.EdgesGeometry(geometry, 28)});
  }
  for (const axis of ['Z', 'X', 'Y']) {
    const group = new THREE.Group();
    group.quaternion.fromArray(assembly.axis_quaternions_xyzw[axis]);
    groups.set(axis, group);
    scene.add(group);
    for (const part of assembly.parts) {
      const geometry = geometries.get(part.id);
      const material = new THREE.MeshStandardMaterial({color: colorFor(part), metalness: 0.23,
        roughness: 0.5, side: THREE.DoubleSide, transparent: true});
      const mesh = new THREE.Mesh(geometry.surface, material);
      const lineMaterial = part.is_reference
        ? new THREE.LineDashedMaterial({color: 0x728a9b, dashSize: 1.1, gapSize: 0.8, transparent: true})
        : new THREE.LineBasicMaterial({color: 0x4d6574, transparent: true});
      const edges = new THREE.LineSegments(geometry.edges, lineMaterial);
      if (part.is_reference) edges.computeLineDistances();
      mesh.add(edges);
      mesh.userData = {axis, partId: part.id, instanceId: instanceId(axis, part.id)};
      group.add(mesh);
      objects.set(mesh.userData.instanceId, {mesh, edges, part, axis});
      renderMeshes.push(mesh);
    }
  }
  const state = {mode: 'single', axis: 'Z', selected: 'RETAINER_BOLT_0',
    explode: 0, section: false, sectionPosition: 0, highlight: true, filter: 'all'};
  let scheduled = false, renderedFrames = 0;
  function render() {
    scheduled = false;
    renderer.render(scene, camera);
    renderedFrames += 1;
    canvas.dataset.rendered = 'true';
  }
  function requestRender() {
    if (!scheduled) {
      scheduled = true;
      requestAnimationFrame(render);
    }
  }
  function resize() {
    const width = viewport.clientWidth, height = viewport.clientHeight;
    if (width <= 0 || height <= 0) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    requestRender();
  }
  function modelCorners() {
    const corners = [];
    for (const {mesh} of objects.values()) {
      if (!mesh.parent.visible) continue;
      const box = mesh.geometry.boundingBox;
      for (const x of [box.min.x, box.max.x]) {
        for (const y of [box.min.y, box.max.y]) {
          for (const z of [box.min.z, box.max.z]) {
            corners.push(new THREE.Vector3(x, y, z).applyMatrix4(mesh.matrixWorld));
          }
        }
      }
    }
    return corners;
  }
  function fitAll() {
    scene.updateMatrixWorld(true);
    const corners = modelCorners();
    const center = new THREE.Box3().setFromPoints(corners).getCenter(new THREE.Vector3());
    const direction = camera.position.clone().sub(controls.target).normalize();
    const right = new THREE.Vector3().crossVectors(camera.up, direction).normalize();
    if (right.lengthSq() < 0.1) right.setFromMatrixColumn(camera.matrixWorld, 0);
    const up = new THREE.Vector3().crossVectors(direction, right).normalize();
    const verticalTan = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2);
    const horizontalTan = verticalTan * camera.aspect;
    let distance = controls.minDistance;
    for (const corner of corners) {
      const relative = corner.clone().sub(center);
      const depth = relative.dot(direction);
      distance = Math.max(distance, depth + 1.12 * Math.abs(relative.dot(right)) / horizontalTan,
        depth + 1.12 * Math.abs(relative.dot(up)) / verticalTan);
    }
    controls.target.copy(center);
    camera.position.copy(center).addScaledVector(direction, distance);
    controls.update();
    camera.updateMatrixWorld(true);
    requestRender();
  }
  function home(front = false) {
    const three = state.mode === 'three';
    const target = three ? new THREE.Vector3(-15, -15, -15) : new THREE.Vector3(0, 0, -55);
    const narrow = viewport.clientWidth < 500;
    const distance = (three ? (narrow ? 370 : 340) : (narrow ? 265 : 235)) * (1 + 0.9 * state.explode / 100);
    const direction = front ? new THREE.Vector3(0, 0, -1) : new THREE.Vector3(0.9, -0.75, -1.35).normalize();
    camera.position.copy(target).addScaledVector(direction, distance);
    camera.up.set(0, 1, 0);
    controls.target.copy(target);
    controls.update();
    fitAll();
  }
  function syncVisuals() {
    const selected = parts.get(state.selected);
    const mates = new Set(selected.mates.map(id => instanceId(state.axis, id)));
    const selectedId = instanceId(state.axis, state.selected);
    for (const [axis, group] of groups) group.visible = state.mode === 'three' || axis === 'Z';
    grid.visible = state.mode === 'single';
    clip.constant = state.sectionPosition;
    let activeCount = 0;
    for (const [id, row] of objects) {
      const isSelected = id === selectedId;
      const isMate = mates.has(id);
      const dim = state.highlight && !isSelected && !isMate;
      row.mesh.position.fromArray(row.part.explode_mm).multiplyScalar(state.explode / 100);
      row.mesh.material.opacity = row.part.is_reference ? (isSelected ? 0.56 : dim ? 0.08 : 0.22) : dim ? 0.16 : 1;
      row.mesh.material.depthWrite = row.mesh.material.opacity === 1;
      row.mesh.material.color.setHex(isSelected && row.part.is_fastener ? COLORS.selected : colorFor(row.part));
      row.mesh.material.emissive.setHex(isSelected ? 0x382004 : isMate && state.highlight ? 0x022227 : 0x000000);
      row.mesh.material.clippingPlanes = state.section ? [clip] : [];
      row.edges.material.clippingPlanes = state.section ? [clip] : [];
      row.edges.material.color.setHex(isSelected ? COLORS.selected : isMate && state.highlight ? COLORS.mate : 0x597282);
      row.edges.material.opacity = isSelected || (isMate && state.highlight) ? 0.95 : dim ? 0.1 : row.part.is_reference ? 0.38 : 0.17;
      row.mesh.renderOrder = row.mesh.material.opacity === 1 ? 0 : row.part.is_reference ? 2 : 1;
      if (row.axis === 'Z' || state.mode === 'three') activeCount += 1;
    }
    canvas.dataset.selected = selectedId;
    canvas.dataset.mode = state.mode;
    canvas.dataset.explode = String(state.explode);
    canvas.dataset.section = String(state.section);
    canvas.dataset.highlighted = JSON.stringify([...mates]);
    canvas.dataset.visibleParts = String(activeCount);
    text('#view-state', `${state.explode ? `分解 ${state.explode}%` : '組付け位置'}${state.section ? ` / X ${state.sectionPosition} mmで半断面` : ''}`);
    text('#mode-label', state.mode === 'three' ? '同一モジュールの参考三軸' : 'Z軸モジュール');
    text('#model-warning', state.mode === 'three' ? '参考配置のみ。元全機の適合・質量・起立を示しません' : '薄い参考形状はPicoの原CADではありません');
    text('#selection-count', `${activeCount} parts / selected ${selectedId}`);
    requestRender();
  }
  function syncPartOptions() {
    const select = $('#part-select');
    select.replaceChildren();
    for (const part of assembly.parts.filter(part => state.filter === 'all' || part.group === state.filter)) {
      const option = document.createElement('option');
      option.value = part.id;
      option.textContent = `${part.label} / ${part.id}`;
      select.append(option);
    }
    select.value = state.selected;
    $('#part-filter').value = state.filter;
    $('#axis-select').value = state.axis;
    $('#axis-select').disabled = state.mode === 'single';
    for (const button of document.querySelectorAll('[data-pick]')) {
      button.setAttribute('aria-pressed', String(button.dataset.pick === state.selected));
    }
  }
  function syncCard() {
    const part = parts.get(state.selected);
    const id = instanceId(state.axis, part.id);
    text('#part-id', id);
    text('#part-title', part.label);
    text('#part-kind', part.is_reference ? 'REF / 独立した説明用の参考形状・互換保証なし' : `${part.role} / ${part.provenance.startsWith('authored-') ? '新規作図部品' : part.provenance}`);
    const joint = part.joint_id ? assembly.joints[part.joint_id] : null;
    $('#joint-card').hidden = !joint;
    if (joint) {
      text('#joint-id', part.joint_id);
      text('#joint-title', joint.title);
      text('#screw-size', joint.size);
      text('#joint-role', joint.role);
      text('#torque-label', part.is_fastener && joint.torque_Nm ? 'C08金属案の条件付き計算（組立用）' : part.is_fastener ? '実入力が不足しています' : '非ねじ接合 / 配置と役割');
      text('#torque-value', torqueText(joint, part.is_fastener));
      text('#joint-receiver', joint.receiver);
      text('#joint-conditions', joint.conditions);
      $('#reference-caution').hidden = !part.reference_joint;
    }
    let description = `材質候補：${part.material}。`;
    if (part.is_reference) description = '元Pico部品ではない、今回独立に作図した参考形状です。原全機の質量・適合・強度・締付値を引き継ぎません。';
    if (part.id === 'WINDING') description += '796巻の包絡表示です。前押え・後端座・内外壁・キーによる拘束を見ます。3軸最大約1.757 Aは従来1.5 Aを超え、実磁力・温度・dutyは未資格です。';
    if (part.id === 'ARMATURE') description += 'C08の公称移動量は0.20 mm。分解スライダーはこの作動ストロークではありません。';
    if (['CARRIER', 'HUB'].includes(part.id)) description += 'PCD30の3孔は名目の参照取付パターンです。元モーターの形状は含まず、実物のねじ・軸との互換は未確認です。';
    text('#part-description', description);
    text('#mates-heading', part.is_fastener ? 'このねじが関係する部品' : '関係する部品');
    const list = $('#mate-list');
    list.replaceChildren();
    for (const mateId of part.mates) {
      const mate = parts.get(mateId);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'mate-button';
      button.dataset.reference = String(mate.is_reference);
      button.dataset.mate = mateId;
      const label = document.createElement('span');
      label.textContent = mate.label;
      const code = document.createElement('small');
      code.textContent = instanceId(state.axis, mateId);
      button.append(label, code);
      if (mate.is_reference) {
        const tag = document.createElement('span');
        tag.className = 'reference-tag';
        tag.textContent = '独立参照';
        label.append(tag);
      }
      button.addEventListener('click', () => selectPart(mateId));
      list.append(button);
    }
    if (part.mates.length === 0) {
      const note = document.createElement('p');
      note.className = 'mate-help';
      note.textContent = 'この表示用部品には接合相手を指定していません。';
      list.append(note);
    }
  }
  function selectPart(id, axis = state.axis) {
    if (!parts.has(id) || !groups.has(axis)) throw new Error('部品の選択先が不正です。');
    state.selected = id;
    state.axis = state.mode === 'single' ? 'Z' : axis;
    if (state.filter !== 'all' && parts.get(id).group !== state.filter) state.filter = 'all';
    syncPartOptions();
    syncCard();
    syncVisuals();
  }
  function syncDownloads() {
    const mode = state.mode === 'single' ? 'single' : 'reference-three';
    $('#download-native').href = `./downloads/brake-${mode}.FCStd`;
    $('#download-step').href = `./downloads/brake-${mode}.step`;
    text('#download-mode', `${state.mode === 'single' ? '単軸149部品' : '参考三軸447部品'}・組付け位置。分解／断面はCADに保存しません。`);
  }
  function mode(value) {
    state.mode = value;
    state.axis = 'Z';
    for (const button of document.querySelectorAll('button[data-mode]')) button.setAttribute('aria-pressed', String(button.dataset.mode === value));
    selectPart(state.selected, 'Z');
    syncDownloads();
    home();
  }
  for (const button of document.querySelectorAll('button[data-mode]')) {
    button.disabled = false;
    button.addEventListener('click', () => mode(button.dataset.mode));
  }
  for (const button of document.querySelectorAll('[data-pick]')) {
    button.addEventListener('click', () => selectPart(button.dataset.pick));
  }
  $('#part-select').addEventListener('change', event => selectPart(event.target.value));
  $('#axis-select').addEventListener('change', event => selectPart(state.selected, event.target.value));
  $('#part-filter').addEventListener('change', event => {
    state.filter = event.target.value;
    const choices = assembly.parts.filter(part => state.filter === 'all' || part.group === state.filter);
    if (!choices.some(part => part.id === state.selected)) state.selected = choices[0].id;
    selectPart(state.selected);
  });
  $('#explode').addEventListener('input', event => {
    state.explode = Number(event.target.value);
    text('#explode-value', `${state.explode}%`);
    syncVisuals();
    fitAll();
  });
  $('#section').addEventListener('change', event => {
    state.section = event.target.checked;
    $('#section-position').disabled = !state.section;
    syncVisuals();
  });
  $('#section-position').addEventListener('input', event => {
    state.sectionPosition = Number(event.target.value);
    text('#section-value', `X ${state.sectionPosition} mm`);
    syncVisuals();
  });
  $('#highlight').addEventListener('change', event => {
    state.highlight = event.target.checked;
    syncVisuals();
  });
  $('#front-view').addEventListener('click', () => home(true));
  $('#fit-view').addEventListener('click', fitAll);
  $('#reset').addEventListener('click', () => {
    Object.assign(state, {mode: 'single', axis: 'Z', selected: 'RETAINER_BOLT_0',
      explode: 0, section: false, sectionPosition: 0, highlight: true, filter: 'all'});
    $('#explode').value = '0';
    $('#section').checked = false;
    $('#section-position').value = '0';
    $('#section-position').disabled = true;
    $('#highlight').checked = true;
    text('#explode-value', '0%');
    text('#section-value', 'X 0 mm');
    mode('single');
  });
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let down = null;
  canvas.addEventListener('pointerdown', event => { down = {x: event.clientX, y: event.clientY}; });
  canvas.addEventListener('pointerup', event => {
    if (!down || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) { down = null; return; }
    down = null;
    const rect = canvas.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    scene.updateMatrixWorld(true);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(renderMeshes.filter(mesh =>
      mesh.parent.visible && (mesh.material.opacity >= 0.16 || mesh.userData.partId === state.selected)), false)
      .filter(hit => !state.section || clip.distanceToPoint(hit.point) >= 0);
    // Ghosted context must not intercept a visible selected/mating part behind it.
    const hit = hits.find(hit => hit.object.material.opacity >= 0.5) || hits[0];
    if (hit) selectPart(hit.object.userData.partId, hit.object.userData.axis);
  });
  canvas.addEventListener('pointercancel', () => { down = null; });
  canvas.addEventListener('keydown', event => {
    const offset = camera.position.clone().sub(controls.target);
    const spherical = new THREE.Spherical().setFromVector3(offset);
    const step = Math.PI / 24;
    if (event.key === 'ArrowLeft') spherical.theta -= step;
    else if (event.key === 'ArrowRight') spherical.theta += step;
    else if (event.key === 'ArrowUp') spherical.phi = Math.max(0.04, spherical.phi - step);
    else if (event.key === 'ArrowDown') spherical.phi = Math.min(Math.PI - 0.04, spherical.phi + step);
    else if (['+', '='].includes(event.key)) spherical.radius = Math.max(controls.minDistance, spherical.radius / 1.12);
    else if (['-', '_'].includes(event.key)) spherical.radius = Math.min(controls.maxDistance, spherical.radius * 1.12);
    else if (event.key === 'Home') { event.preventDefault(); home(); return; }
    else return;
    event.preventDefault();
    camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(spherical));
    controls.update();
    requestRender();
  });
  controls.addEventListener('change', requestRender);
  new ResizeObserver(resize).observe(viewport);
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    onError(new Error('WebGLの描画接続が失われました。ほかの3D画面を閉じてから再読み込みしてください。'));
  });
  $('#loading').hidden = true;
  $('#view-caption').hidden = false;
  $('#model-warning').hidden = false;
  $('#bench-controls').disabled = false;
  $('#part-controls').disabled = false;
  viewport.setAttribute('aria-busy', 'false');
  syncPartOptions();
  syncCard();
  syncVisuals();
  syncDownloads();
  resize();
  home();
  // Read-only diagnostics support reproducible browser checks without mutating the scene.
  window.brakeInspection = Object.freeze({
    snapshot() {
      const rect = canvas.getBoundingClientRect();
      const projected = modelCorners().map(point => point.project(camera));
      const projectedBounds = [
        Math.min(...projected.map(point => point.x)), Math.min(...projected.map(point => point.y)),
        Math.max(...projected.map(point => point.x)), Math.max(...projected.map(point => point.y)),
      ];
      const projectedFasteners = [];
      for (const [id, row] of objects) {
        if (!row.part.is_fastener || !row.mesh.parent.visible) continue;
        const box = row.mesh.geometry.boundingBox;
        const point = box.getCenter(new THREE.Vector3());
        point.z = box.min.z + 0.05;
        point.applyMatrix4(row.mesh.matrixWorld).project(camera);
        projectedFasteners.push({id, x: rect.left + (point.x + 1) * rect.width / 2,
          y: rect.top + (1 - point.y) * rect.height / 2});
      }
      return {
        camera: camera.position.toArray(), target: controls.target.toArray(),
        autoRotate: controls.autoRotate, damping: controls.enableDamping, renderedFrames,
        drawCalls: renderer.info.render.calls, triangles: renderer.info.render.triangles,
        projectedBounds,
        clippingPlanes: state.section ? 1 : 0,
        visibleAxes: [...groups].filter(([, group]) => group.visible).map(([axis]) => axis),
        selected: instanceId(state.axis, state.selected), projectedFasteners,
      };
    },
  });
  document.documentElement.dataset.viewerState = 'ready';
}
