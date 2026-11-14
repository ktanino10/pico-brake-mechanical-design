import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {motionRole, springWeight, poseAt, GAP_MM} from './motion-contract.js';

const COLOR = {fixed: 0x8795a5, rotating: 0x256fc0, axial: 0x4da8e2, spring: 0x91b456,
  coil: 0xc36a24, lining: 0x4d5a69, yellow: 0xffdc65};

function geometry(item) {
  const result = new THREE.BufferGeometry();
  result.setAttribute('position', new THREE.Float32BufferAttribute(item.positions, 3));
  result.setIndex(item.indices);
  result.computeVertexNormals();
  result.computeBoundingBox();
  result.computeBoundingSphere();
  return result;
}

export function createMotionScene(assembly, meshData, sectionData, viewport, onChange, onError) {
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.setClearColor(0x192b3c);
  renderer.localClippingEnabled = true;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  const canvas = renderer.domElement;
  canvas.id = 'motion-canvas';
  canvas.tabIndex = 0;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', 'C08ブレーキの3D。ドラッグ・矢印キーで視点回転、ホイール・プラスマイナスでズーム。部品の動作は別の再生ボタンで操作。');
  viewport.prepend(canvas);
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-100, 100, 60, -60, .01, 3000);
  const controls = new OrbitControls(camera, canvas);
  controls.autoRotate = false;
  controls.enableDamping = false;
  controls.minZoom = .15;
  controls.maxZoom = 80;
  controls.addEventListener('change', onChange);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x344052, 2.6));
  for (const [position, strength] of [[[100, -150, -220], 2.4], [[-170, 130, 120], 1.8]]) {
    const light = new THREE.DirectionalLight(0xffffff, strength);
    light.position.fromArray(position);
    scene.add(light);
  }
  const parts = new Map(assembly.parts.map(p => [p.id, p]));
  const geometries = new Map(meshData.parts.map(p => [p.id, geometry(p)]));
  const springBases = new Map([...geometries].filter(([id]) => /^SPRING_\d+$/.test(id))
    .map(([id, g]) => [id, g.attributes.position.array.slice()]));
  const groups = new Map();
  const rows = [];
  const cutPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const markingMaterial = new THREE.MeshBasicMaterial({color: 0xf6fafc, side: THREE.DoubleSide});

  function addPart(parent, part, geo, prefix, slice = false) {
    const role = motionRole(part);
    let color = COLOR[role];
    if (part.id === 'WINDING') color = COLOR.coil;
    if (/^LINING_\d+$/.test(part.id)) color = COLOR.lining;
    const material = new THREE.MeshStandardMaterial({color, roughness: .56, metalness: .15,
      side: THREE.DoubleSide, flatShading: true, transparent: true});
    const mesh = new THREE.Mesh(geo, material);
    mesh.userData = {id: part.id, role, source: part.provenance, reference: part.is_reference};
    parent.add(mesh);
    const markers = [];
    if (!slice && ['REF_WHEEL', 'ARMATURE'].includes(part.id)) {
      for (const [angle, arc] of [[.1, .25], [-2.3, .15]]) {
        const radii = part.id === 'REF_WHEEL' ? [34, 57.3] : [29, 45.2];
        const mark = new THREE.Mesh(new THREE.RingGeometry(...radii, 48, 1, angle, arc), markingMaterial);
        mark.position.z = part.id === 'REF_WHEEL' ? -68.025 : -64.22;
        mesh.add(mark);
        markers.push(mark);
      }
    }
    const row = {mesh, markers, part, role, prefix, slice};
    rows.push(row);
    return row;
  }
  for (const axis of ['Z', 'X', 'Y']) {
    const group = new THREE.Group();
    group.quaternion.fromArray(assembly.axis_quaternions_xyzw[axis]);
    groups.set(axis, group);
    scene.add(group);
    for (const part of assembly.parts) addPart(group, part, geometries.get(part.id), axis);
  }
  const contactSection = new THREE.Group();
  scene.add(contactSection);
  for (const item of sectionData.parts) addPart(contactSection, parts.get(item.id), geometry(item), 'slice', true);
  const sectionContact = new THREE.Line(new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-.61,32,-61.2),new THREE.Vector3(-.61,40,-61.2),
  ]),new THREE.LineBasicMaterial({color:COLOR.yellow}));
  scene.add(sectionContact);

  const schematic = new THREE.Group();
  scene.add(schematic);
  function block(name, center, size, color) {
    const material = new THREE.MeshStandardMaterial({color, roughness: .65});
    const object = new THREE.Mesh(new THREE.BoxGeometry(...size), material);
    object.position.fromArray(center);
    object.userData.id = name;
    schematic.add(object);
    return object;
  }
  const hub = block('模式ハブ', [-46.5, 2.5, 6], [58, 12.5, 9], COLOR.rotating);
  const disc = block('模式可動円盤', [3.5, 0, 32.5], [5, 12, 52.5], COLOR.axial);
  const face = block('模式固定摩擦面', [26, 0, 35], [4, 14.5, 45], COLOR.lining);
  const coil = block('模式電磁石', [47, 3.5, 35], [31, 11, 32.5], COLOR.coil);
  block('模式固定支持', [67, 1.5, 34.5], [7, 15, 56], COLOR.fixed);
  block('模式固定支持上', [47.5, 1.5, 60], [45.5, 15, 7], COLOR.fixed);
  block('模式固定支持下', [48, 1.5, 9.5], [45, 15, 7], COLOR.fixed);
  const contact = block('接触の強調', [24.1, -8, 35], [1.2, 1.2, 42.5], COLOR.yellow);
  const springGeo = new THREE.BufferGeometry();
  const springVertices = new Float32Array(32 * 2 * 3);
  const springIndices = [];
  for (let i = 0; i < 31; i += 1) springIndices.push(2*i, 2*i+1, 2*i+2, 2*i+1, 2*i+3, 2*i+2);
  springGeo.setAttribute('position', new THREE.BufferAttribute(springVertices, 3));
  springGeo.setIndex(springIndices);
  const schematicSpring = new THREE.Mesh(springGeo, new THREE.MeshStandardMaterial({color: COLOR.spring, side: THREE.DoubleSide}));
  schematic.add(schematicSpring);
  const axialArrow = new THREE.ArrowHelper(new THREE.Vector3(1,0,0), new THREE.Vector3(7,-9,43), 15, COLOR.coil, 4, 3);
  schematic.add(axialArrow);
  const returnArrow = new THREE.ArrowHelper(new THREE.Vector3(-1,0,0), new THREE.Vector3(23,-9,43), 15, COLOR.spring, 4, 3);
  schematic.add(returnArrow);
  const frictionGroup = new THREE.Group();
  const frictionPoints = Array.from({length: 49}, (_, i) => {
    const a = THREE.MathUtils.degToRad(200-i*1.8);
    return new THREE.Vector3(68*Math.cos(a),68*Math.sin(a),-69.2);
  });
  const frictionLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(frictionPoints),
    new THREE.LineBasicMaterial({color: 0xff907d}));
  frictionGroup.add(frictionLine);
  const end = frictionPoints.at(-1);
  const a = THREE.MathUtils.degToRad(200-48*1.8);
  const frictionHead = new THREE.ArrowHelper(new THREE.Vector3(Math.sin(a),-Math.cos(a),0), end, 5, 0xff907d, 5, 4);
  frictionGroup.add(frictionHead);
  scene.add(frictionGroup);
  let current = null, pose = poseAt(4), scale = 120, renders = 0, selected = 'ARMATURE';

  function apply(state) {
    current = state;
    pose = poseAt(state.time);
    const assembled = state.explode === 0;
    for (const [axis, group] of groups) group.visible = ['model','three'].includes(state.view) && (axis === 'Z' || state.view === 'three');
    contactSection.visible = state.view === 'section';
    sectionContact.visible = state.view === 'section' && assembled && pose.contact;
    schematic.visible = state.view === 'schematic';
    for (const [id, base] of springBases) {
      const g = geometries.get(id), p = g.attributes.position;
      const index = Number(id.split('_').at(-1));
      for (let i = 0; i < p.count; i += 1) p.setZ(i, base[3*i+2] + (assembled ? pose.travel * springWeight(base[3*i], base[3*i+1], index) : 0));
      p.needsUpdate = true;
      g.computeVertexNormals();
    }
    for (const row of rows) {
      const {mesh, role, part} = row;
      mesh.rotation.set(0, 0, assembled && !row.slice && role !== 'fixed' ? THREE.MathUtils.degToRad(pose.angle) : 0);
      mesh.position.set(0, 0, assembled && role === 'axial' ? pose.travel : 0);
      if (!assembled) mesh.position.add(new THREE.Vector3().fromArray(part.explode_mm).multiplyScalar(state.explode/100));
      const inside = state.cutaway && state.view === 'model';
      mesh.material.clippingPlanes = inside && role === 'fixed' && part.id !== 'WINDING' ? [cutPlane] : [];
      mesh.material.opacity = row.slice ? 1 : part.id === 'REF_WHEEL' && inside ? .23 : part.id === 'REF_FRAME' ? .22 : 1;
      mesh.material.depthWrite = mesh.material.opacity === 1;
      mesh.material.emissive.setHex(part.id === selected ? 0x062033 : 0);
      if (part.id === 'WINDING') mesh.material.color.setHex(assembled && pose.coil ? 0xf28b31 : COLOR.coil);
      for (const mark of row.markers) mark.visible = !row.slice;
    }
    const move = 18 * pose.travel / GAP_MM;
    disc.position.x = 3.5 + move;
    for (let i = 0; i < 32; i += 1) {
      const u = i/31, weight = u*u*(3-2*u);
      for (let side = 0; side < 2; side += 1) {
        const k = (2*i+side)*3;
        springVertices[k] = -34.5 + 38*u + move*weight;
        springVertices[k+1] = -1;
        springVertices[k+2] = 10 + 23*u + (side ? 1.2 : -1.2);
      }
    }
    springGeo.attributes.position.needsUpdate = true;
    springGeo.computeVertexNormals();
    springGeo.computeBoundingSphere();
    contact.visible = pose.contact;
    coil.material.color.setHex(pose.coil ? 0xf28b31 : COLOR.coil);
    axialArrow.visible = pose.coil && !pose.contact && pose.time < 22;
    axialArrow.position.x = 7+move;
    axialArrow.setLength(Math.max(.1, 16-move), Math.min(4, Math.max(.1,(16-move)/2)), 3);
    returnArrow.visible = pose.time >= 32.5 && pose.time < 35.5;
    returnArrow.setLength(Math.max(.1, 16-move), Math.min(4, Math.max(.1,(16-move)/2)), 3);
    frictionGroup.visible = state.view === 'model' && assembled && pose.braking;
    scene.updateMatrixWorld(true);
  }

  function resize() {
    const width = viewport.clientWidth, height = viewport.clientHeight;
    if (width <= 0 || height <= 0) return;
    renderer.setSize(width, height, false);
    camera.left = -scale*width/height/2;
    camera.right = scale*width/height/2;
    camera.top = scale/2;
    camera.bottom = -scale/2;
    camera.updateProjectionMatrix();
    onChange();
  }
  function visibleBounds() {
    const box = new THREE.Box3();
    if (current.view === 'schematic') {
      box.setFromObject(schematic);
    } else if (current.view === 'section') {
      box.setFromObject(contactSection);
    } else {
      for (const group of groups.values()) if (group.visible) box.union(new THREE.Box3().setFromObject(group));
    }
    return box;
  }
  function fit() {
    scene.updateMatrixWorld(true);
    const box = visibleBounds(), center = box.getCenter(new THREE.Vector3());
    const offset = camera.position.clone().sub(controls.target);
    controls.target.copy(center);
    camera.position.copy(center).add(offset);
    camera.zoom = 1;
    controls.update();
    camera.updateMatrixWorld(true);
    const inverse = camera.matrixWorldInverse;
    let maxX = 0, maxY = 0;
    for (const x of [box.min.x,box.max.x]) for (const y of [box.min.y,box.max.y]) for (const z of [box.min.z,box.max.z]) {
      const p = new THREE.Vector3(x,y,z).applyMatrix4(inverse);
      maxX = Math.max(maxX,Math.abs(p.x));
      maxY = Math.max(maxY,Math.abs(p.y));
    }
    scale = 2.3 * Math.max(maxY, maxX*viewport.clientHeight/viewport.clientWidth, .1);
    resize();
  }
  function home() {
    camera.zoom = 1;
    if (current.view === 'schematic') {
      camera.up.set(0,0,1);controls.target.set(0,0,32.5);camera.position.set(0,-200,32.5);
      scale = Math.max(78,175*viewport.clientHeight/viewport.clientWidth);
    } else if (current.view === 'section') {
      camera.up.set(0,1,0);controls.target.set(0,36,-62.1);camera.position.set(-80,36,-62.1);
      scale = Math.max(10,14*viewport.clientHeight/viewport.clientWidth);
    } else {
      camera.up.set(0,0,1);
      const target = current.view === 'three' ? new THREE.Vector3() : new THREE.Vector3(0,0,-58);
      controls.target.copy(target);
      camera.position.copy(target).add(current.view === 'three' ? new THREE.Vector3(-230,-270,-220) : new THREE.Vector3(105,-160,-118));
      scale = current.view === 'three' ? 280 : 150;
    }
    controls.update();resize();
    if (['model','three'].includes(current.view)) fit();
    if (current.view==='model' && current.explode===0) {
      camera.zoom=1.35;camera.updateProjectionMatrix();onChange();
    }
  }
  function render() {
    scene.updateMatrixWorld(true);
    renderer.render(scene,camera);
    renders += 1;
    canvas.dataset.rendered = 'true';
  }
  function project(point) {
    const p = point.clone().project(camera);
    return {x:(p.x+1)*viewport.clientWidth/2,y:(1-p.y)*viewport.clientHeight/2,visible:p.z>=-1&&p.z<=1&&Math.abs(p.x)<1&&Math.abs(p.y)<1};
  }
  function labels() {
    if (current.view === 'schematic') return [
      ['動く円盤',project(new THREE.Vector3(disc.position.x-14,0,64))],
      ['固定摩擦面',project(new THREE.Vector3(42,0,66))],
      ['電磁石',project(new THREE.Vector3(47,-8,36))],
      ['ハブ：軸位置固定',project(new THREE.Vector3(-43,-8,6))],
    ];
    if (current.view === 'section') return [
      ['可動円盤',project(new THREE.Vector3(-.62,39,-62.7+pose.travel))],
      ['固定摩擦面',project(new THREE.Vector3(-.62,39,-60.5))],
      ['電磁石（非接触）',project(new THREE.Vector3(-.62,39,-56.4))],
      ['参考ホイール',project(new THREE.Vector3(-.62,39,-66.5))],
    ];
    return [];
  }
  function snapshot() {
    scene.updateMatrixWorld(true);
    const wanted = ['HUB','ARMATURE','WINDING','LINING_0','REF_WHEEL','SPRING_0'];
    const transforms = {};
    for (const id of wanted) {
      const row = rows.find(r => r.prefix === 'Z' && r.part.id === id);
      transforms[id] = {position:row.mesh.position.toArray(),rotation:row.mesh.rotation.toArray().slice(0,3),
        matrix:row.mesh.matrixWorld.toArray(),role:row.role};
    }
    const spring = geometries.get('SPRING_0').attributes.position;
    const base = springBases.get('SPRING_0');
    let root = null, tip = null;
    for (let i=0;i<spring.count;i+=1) {
      const weight = springWeight(base[3*i],base[3*i+1],0);
      if (weight === 0 && root === null) root = spring.getZ(i)-base[3*i+2];
      if (weight === 1 && tip === null) tip = spring.getZ(i)-base[3*i+2];
    }
    const armature = rows.find(r=>r.prefix==='Z' && r.part.id==='ARMATURE').mesh;
    const lining = rows.find(r=>r.prefix==='Z' && r.part.id==='LINING_0').mesh;
    const actualGap = new THREE.Box3().setFromObject(lining).min.z - new THREE.Box3().setFromObject(armature).max.z;
    const schematicGap = new THREE.Box3().setFromObject(face).min.x - new THREE.Box3().setFromObject(disc).max.x;
    return {camera:camera.position.toArray(),target:controls.target.toArray(),zoom:camera.zoom,
      autoRotate:controls.autoRotate,renderedFrames:renders,drawCalls:renderer.info.render.calls,
      triangles:renderer.info.render.triangles,transforms,springDisplacement:{root,tip},
      actualGap:current.explode ? null : actualGap,schematicGap,
      schematicHub:hub.position.toArray(),frictionArrowVisible:frictionGroup.visible,
      attractionArrowVisible:axialArrow.visible,contactHighlight:contact.visible,
      visibleAxes:[...groups].filter(([,g])=>g.visible).map(([n])=>n),
      sectionVisible:contactSection.visible,schematicVisible:schematic.visible,
      actualContactHighlight:sectionContact.visible,
      sourceMeshSha256:assembly.mesh.sha256};
  }
  canvas.addEventListener('keydown',event=>{
    if (event.key==='Home') {event.preventDefault();home();onChange();return;}
    if (['+','=','-','_'].includes(event.key)) {
      event.preventDefault();
      camera.zoom=THREE.MathUtils.clamp(camera.zoom*(['+','='].includes(event.key)?1.12:1/1.12),controls.minZoom,controls.maxZoom);
      camera.updateProjectionMatrix();onChange();return;
    }
    const rotations={ArrowLeft:-1,ArrowRight:1,ArrowUp:-1,ArrowDown:1};
    if (!(event.key in rotations)) return;
    event.preventDefault();
    const offset=camera.position.clone().sub(controls.target);
    const axis=['ArrowLeft','ArrowRight'].includes(event.key)?camera.up.clone():new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0);
    offset.applyAxisAngle(axis,rotations[event.key]*Math.PI/24);
    camera.position.copy(controls.target).add(offset);controls.update();onChange();
  });
  canvas.addEventListener('webglcontextlost',event=>{
    event.preventDefault();onError(new Error('WebGLの描画接続が失われました。再読み込みしてください。'));
  });
  return {canvas,apply,resize,home,fit,render,snapshot,labels,
    contactPoint:()=>current.view==='schematic'?project(new THREE.Vector3(24,-10,42)):project(new THREE.Vector3(0,36,-61.2)),
    select(id){selected=id;},
  };
}
