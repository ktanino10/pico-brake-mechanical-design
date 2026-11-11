import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {jointLengthText, jointStack, validateEnclosure, validateEnclosureMesh} from '../enclosure-contract.js';

const assembly = JSON.parse(fs.readFileSync(new URL('../data/enclosure-assembly.json', import.meta.url)));
const bytes = fs.readFileSync(new URL('../data/enclosure-meshes.json', import.meta.url));
const meshes = JSON.parse(bytes);

test('526 global-mm parts, 200 explicit joints and 11 references agree with the exact CAD mesh', () => {
  assert.equal(validateEnclosure(assembly), assembly);
  assert.equal(validateEnclosureMesh(meshes, assembly), meshes);
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), assembly.mesh.sha256);
  assert.ok(!assembly.parts.some(part => part.id.endsWith('_REF_FRAME')));
  for (const part of assembly.parts) assert.ok(part.bbox_mm.every(value => Math.abs(value) <= 69.0001));
});

test('new board fasteners distinguish under-head 10 and actual overall 13 mm with complete stacks', () => {
  const joint = assembly.joints.find(row => row.fastener === 'E_BOARD_SCREW_PCB_0');
  assert.equal(jointLengthText(joint), '呼び 10 mm（首下） / 実全長 13 mm');
  assert.deepEqual(jointStack(joint), ['E_WASHER_PCB_0', 'E_REF_BOARD_PCB', 'E_SPACER_PCB_0', 'E_HOLDER_PCB']);
  const flat = assembly.joints.find(row => row.fastener === 'E_FRAME_SCREW_PPP_X');
  assert.equal(jointLengthText(flat), '呼び 10 mm（頭を含む） / 実全長 10 mm');
});

test('missing counterpart, original geometry names and a misleading physical state fail explicitly', () => {
  const missing = structuredClone(assembly);
  missing.joints[0].receiver = 'ABSENT';
  assert.throws(() => validateEnclosure(missing), /相手|stack/);
  const original = structuredClone(assembly);
  original.parts[0].id = 'SRC_ORIGINAL_FRAME';
  assert.throws(() => validateEnclosure(original), /未承認/);
  const released = structuredClone(assembly);
  released.physical_ready = true;
  assert.throws(() => validateEnclosure(released), /未資格/);
});

test('source motor CAD failure and hardware uncertainty cannot be replaced by a compatible reference claim', () => {
  const altered = structuredClone(assembly);
  altered.reference_motor_CAD_nominal_fit = 'passed';
  assert.throws(() => validateEnclosure(altered), /motor/);
  assert.equal(assembly.nominal_conditions.motor_interface_limit.pilot_omission_does_not_resolve_source_motor_fit, true);
  assert.equal(assembly.nominal_conditions.mpu.actual_module_hole_diameter_verified, false);
  assert.equal(assembly.nominal_conditions.pcb.source_holder_vs_drill_one_hole_difference_mm, 0.186);
});

test('stale overall screw length and moved global mesh are rejected', () => {
  const altered = structuredClone(assembly);
  altered.joints.find(row => row.fastener === 'E_BOARD_SCREW_PCB_0').modeled_total_length_mm = 10;
  assert.throws(() => validateEnclosure(altered), /全長/);
  const row = {...meshes.parts[0], positions: meshes.parts[0].positions.map((value, i) => value + (i % 3 === 0 ? 1 : 0))};
  assert.throws(() => validateEnclosureMesh({...meshes, parts: [row, ...meshes.parts.slice(1)]}, assembly), /寸法|姿勢/);
});
