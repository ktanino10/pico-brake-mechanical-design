import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import * as THREE from 'three';
import {validateOverview, referenceGeometries} from '../overview.js';

const layout = JSON.parse(await readFile(new URL('../data/overview-layout.json', import.meta.url), 'utf8'));
const assembly = JSON.parse(await readFile(new URL('../data/assembly.json', import.meta.url), 'utf8'));
const mesh = await readFile(new URL('../data/meshes.json', import.meta.url));
const parts = new Map(layout.parts.map(part => [part.id, part]));

test('overview uses independent reference items and the exact existing brake mesh', () => {
  assert.equal(validateOverview(layout).parts.length, 72);
  assert.equal(layout.base_mesh_sha256, createHash('sha256').update(mesh).digest('hex'));
  assert.equal(layout.base_mesh_sha256, assembly.mesh.sha256);
  assert.equal(layout.base_parts_per_axis, 149);
  assert.ok(layout.parts.every(part => part.source_geometry === null && part.included_in_brake_cad === false));
});

test('every board screw, post, nut and panel hole shares its reference axis', () => {
  const top = parts.get('REF_CASE_TOP');
  for (const key of ['CTRL', 'DRIVE']) {
    const board = parts.get(`REF_PCB_${key}`);
    assert.equal(board.holes.length, 4);
    board.holes.forEach(([x, y], i) => {
      const worldX = x + board.position_mm[0], worldY = y + board.position_mm[1];
      for (const type of ['POST', 'SCREW', 'NUT']) {
        const part = parts.get(`REF_PCB_${type}_${key}_${i}`);
        assert.deepEqual(part.position_mm.slice(0, 2), [worldX, worldY]);
      }
      assert.ok(top.holes.some(hole => hole[0] === worldX && hole[1] === worldY));
      assert.deepEqual(parts.get(`REF_PCB_SCREW_${key}_${i}`).mates,
        [`REF_PCB_${key}`, `REF_PCB_POST_${key}_${i}`, 'REF_CASE_TOP', `REF_PCB_NUT_${key}_${i}`]);
    });
  }
});

test('rendered board holes are really open and the reference plate remains solid elsewhere', () => {
  for (const id of ['REF_PCB_CTRL', 'REF_PCB_DRIVE']) {
    const board = parts.get(id), geometry = referenceGeometries(board)[0];
    const object = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({side: THREE.DoubleSide}));
    object.updateMatrixWorld(true);
    for (const [x, y] of board.holes) {
      const ray = new THREE.Raycaster(new THREE.Vector3(x, y, 10), new THREE.Vector3(0, 0, -1));
      assert.equal(ray.intersectObject(object).length, 0);
    }
    const center = new THREE.Raycaster(new THREE.Vector3(0, 0, 10), new THREE.Vector3(0, 0, -1));
    assert.ok(center.intersectObject(object).length > 0);
    geometry.dispose(); object.material.dispose();
  }
});

test('all additional shapes are finite; bad origins, mates, dimensions and qualification fail closed', () => {
  for (const part of layout.parts) {
    for (const geometry of referenceGeometries(part)) {
      geometry.computeBoundingBox();
      assert.ok(geometry.attributes.position.count > 0);
      assert.ok([...geometry.attributes.position.array].every(Number.isFinite));
      assert.ok(!geometry.boundingBox.isEmpty());
      geometry.dispose();
    }
  }
  for (const mutate of [
    value => { value.whole_fit = true; },
    value => { value.parts[0].source_geometry = 'original-private-frame'; },
    value => { value.parts[0].origin = 'source-modified'; },
    value => { value.parts[0].included_in_brake_cad = true; },
    value => { value.parts[0].tightening_torque_Nm = 0.4; },
    value => { value.parts[0].mates = ['UNKNOWN_PART']; },
    value => { value.parts[0].dimensions_mm[0] = NaN; },
    value => { value.parts[0].holes[0][0] = 1000; },
  ]) {
    const changed = structuredClone(layout);
    mutate(changed);
    assert.throws(() => validateOverview(changed));
  }
});
