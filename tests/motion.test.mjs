import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {test} from 'node:test';
import {DURATION, GAP_MM, initialMotionState, motionRole, poseAt, springWeight, transition} from '../motion-contract.js';

const assembly = JSON.parse(await readFile(new URL('../data/assembly.json', import.meta.url)));

test('every source part has a motion group; hub and stator never acquire armature travel', () => {
  const roles = new Map(assembly.parts.map(p => [p.id, motionRole(p)]));
  assert.equal(roles.size, 149);
  for (const id of ['YOKE', 'WINDING', 'LINING_0', 'CARRIER']) assert.equal(roles.get(id), 'fixed');
  for (const id of ['HUB', 'HUB_FACE', 'REF_WHEEL', 'REF_SHAFT']) assert.equal(roles.get(id), 'rotating');
  for (const id of ['ARMATURE', 'SPRING_TIP_BOLT_0', 'SPRING_CLAMP_TIP_0']) assert.equal(roles.get(id), 'axial');
  assert.equal(roles.get('SPRING_0'), 'spring');
  assert.throws(() => motionRole({id: 'UNKNOWN', group: 'unknown'}));
});

test('drive-off precedes contact; braking starts at contact and stops at rest', () => {
  assert.equal(poseAt(12).drive, false);
  assert.ok(poseAt(12.5).angle > poseAt(12).angle);
  assert.equal(poseAt(21.99).contact, false);
  assert.equal(poseAt(21.99).braking, false);
  assert.ok(poseAt(21.99).travel < GAP_MM);
  assert.equal(poseAt(22).travel, GAP_MM);
  assert.equal(poseAt(22).contact, true);
  assert.equal(poseAt(22).braking, true);
  assert.equal(poseAt(29).braking, false);
  assert.equal(poseAt(30).speed, 0);
  assert.equal(poseAt(40).angle, poseAt(29).angle);
  assert.equal(poseAt(40).travel, 0);
  assert.equal(poseAt(40).coil, false);
});

test('all three tangential spring roots stay while tips follow', () => {
  for (let i=0; i<3; i+=1) {
    const a=i*2*Math.PI/3;
    const transform=(x,y)=>[x*Math.cos(a)-y*Math.sin(a),x*Math.sin(a)+y*Math.cos(a)];
    assert.equal(springWeight(...transform(24,3),i),0);
    assert.equal(springWeight(...transform(24,33),i),1);
    assert.ok(Math.abs(springWeight(...transform(24,18),i)-.5)<1e-12);
  }
});

test('explosion pauses and resets motion, and reassembly never starts playback', () => {
  let state=transition(initialMotionState(),{type:'play'});
  state=transition(state,{type:'tick',delta:.1});
  state=transition(state,{type:'explode',value:60});
  assert.equal(state.playing,false);
  assert.equal(state.time,4);
  assert.equal(transition(state,{type:'play'}).playing,false);
  assert.equal(transition(state,{type:'tick',delta:.1}).time,4);
  state=transition(state,{type:'explode',value:0});
  assert.equal(state.playing,false);
  assert.equal(state.explode,0);
});

test('contact jumps and section modes resolve exploded-state conflicts', () => {
  let state=transition(initialMotionState(),{type:'explode',value:70});
  state=transition(state,{type:'seek',time:22,view:'schematic'});
  assert.equal(state.explode,0);assert.equal(state.playing,false);assert.equal(state.time,22);
  assert.equal(state.view,'schematic');
  state=transition(state,{type:'explode',value:30});
  assert.equal(state.view,'model');
  state=transition(state,{type:'view',value:'section'});
  assert.equal(state.explode,0);assert.equal(state.playing,false);
});

test('end does not loop and invalid state input is rejected', () => {
  let state=transition(initialMotionState(),{type:'seek',time:39.95});
  state=transition(state,{type:'play'});
  state=transition(state,{type:'tick',delta:.1});
  assert.equal(state.time,DURATION);assert.equal(state.playing,false);
  for (const time of [-1,NaN,Infinity,40.01]) assert.throws(()=>poseAt(time));
  assert.throws(()=>transition(state,{type:'explode',value:101}));
  assert.throws(()=>transition(state,{type:'view',value:'unknown'}));
  assert.throws(()=>transition(state,{type:'unknown'}));
});
