import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {instanceId, torqueText, validateAssembly, validateMesh} from '../contract.js';

const root = new URL('../', import.meta.url);
const assembly = JSON.parse(await readFile(new URL('data/assembly.json', root), 'utf8'));
const bytes = await readFile(new URL('data/meshes.json', root));
const meshes = JSON.parse(bytes.toString('utf8'));
const policy = JSON.parse(await readFile(new URL('data/provenance.json', root), 'utf8'));
const copy = value => structuredClone(value);

test('149 parts, mm, unreleased flags and checksum match the exact public meshes', () => {
  assert.equal(validateAssembly(assembly).parts.length, 149);
  assert.equal(validateMesh(meshes, assembly).parts.length, 149);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), assembly.mesh.sha256);
  assert.deepEqual(new Set(assembly.parts.map(p => p.id)), new Set(policy.included.map(p => p.public_part)));
  assert.equal(assembly.parts.filter(p => p.is_reference).length, 4);
});

test('each real screw selects its same-axis public counterparts and an explicit joint', () => {
  const screws = assembly.parts.filter(part => part.is_fastener);
  assert.equal(screws.length, 52);
  for (const axis of ['X', 'Y', 'Z']) {
    for (const screw of screws) {
      assert.ok(assembly.joints[screw.joint_id]);
      assert.ok(screw.mates.length);
      assert.ok(screw.mates.every(id => instanceId(axis, id).startsWith(`${axis}_`)));
      assert.ok(!screw.mates.includes('WHEEL'));
      assert.ok(!screw.mates.includes('LOAD_FRAME'));
      assert.equal(screw.reference_joint, screw.mates.some(id => id.startsWith('REF_')));
    }
  }
  const retainer = assembly.parts.find(p => p.id === 'RETAINER_BOLT_0');
  assert.deepEqual(retainer.mates, ['LINING_KEEPER_0', 'POLE_CAP_INNER', 'COIL_RETAINER', 'YOKE']);
  const frame = assembly.parts.find(p => p.id === 'FRAME_BOLT_0');
  assert.deepEqual(frame.mates, ['REF_FRAME', 'POST_0', 'CARRIER', 'FRAME_NUT_0']);
});

test('motor torque stays unknown; non-screw contacts have no tightening value', () => {
  assert.equal(torqueText(assembly.joints.J10, true), '未決');
  assert.equal(torqueText(assembly.joints.J09, false), '締付値なし');
  assert.equal(torqueText(assembly.joints.J05, true), '0.37–0.42 N·m');
});

test('missing counterpart, wrong unit and released flag all fail explicitly', () => {
  for (const mutate of [
    value => { value.parts[0].mates = ['SOURCE_WHEEL']; },
    value => { value.units = 'm'; },
    value => { value.whole_fit = true; },
    value => { value.parts[0].id = value.parts[1].id; },
  ]) {
    const changed = copy(assembly);
    mutate(changed);
    assert.throws(() => validateAssembly(changed));
  }
});

test('invalid mesh index, omitted part and altered CAD scale fail explicitly', () => {
  const missing = copy(meshes);
  missing.parts.pop();
  assert.throws(() => validateMesh(missing, assembly));
  const broken = copy(meshes);
  broken.parts[0].indices[0] = broken.parts[0].positions.length;
  assert.throws(() => validateMesh(broken, assembly));
  const scaled = copy(meshes);
  scaled.parts[0].positions = scaled.parts[0].positions.map(n => n * 1000);
  assert.throws(() => validateMesh(scaled, assembly));
});

test('known C08 failures are not suppressed or replaced by reference-fixture claims', () => {
  const limits = assembly.known_limits;
  assert.ok(limits.three_axis_max_current_A > limits.retained_current_limit_A);
  assert.ok(limits.inner_edge_force_N > limits.structure_case_N);
  assert.ok(limits.inner_edge_required_A > limits.hot_available_A);
  assert.equal(limits.source_whole_machine_mass_and_fit_transferred, false);
  assert.equal(limits.actual_motor_compatible, false);
});

test('mesh centroid metadata and all three rotations agree with an independent coordinate convention', () => {
  const changed = copy(assembly);
  changed.parts[0].mesh_centroid_mm[0] += 1;
  assert.throws(() => validateMesh(meshes, changed), /重心/);
  const expected = {X: [3, -2, 1], Y: [1, 3, -2], Z: [1, 2, 3]};
  for (const axis of ['X', 'Y', 'Z']) {
    const [x, y, z, w] = assembly.axis_quaternions_xyzw[axis];
    const vector = [1, 2, 3];
    const cross = [y * vector[2] - z * vector[1], z * vector[0] - x * vector[2], x * vector[1] - y * vector[0]];
    const cross2 = [y * cross[2] - z * cross[1], z * cross[0] - x * cross[2], x * cross[1] - y * cross[0]];
    const result = vector.map((value, i) => value + 2 * w * cross[i] + 2 * cross2[i]);
    result.forEach((value, i) => assert.ok(Math.abs(value - expected[axis][i]) < 1e-12));
  }
});
