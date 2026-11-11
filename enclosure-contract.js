import {validateMesh} from './contract.js';

const finiteVector = (value, size) => Array.isArray(value) && value.length === size && value.every(Number.isFinite);

export function validateEnclosure(data) {
  if (data?.schema !== 'independent-enclosure-assembly-v1' || data.units !== 'mm') throw new Error('筐体データの形式・mm単位が一致しません。');
  for (const key of ['whole_fit', 'build_ready', 'physical_ready']) {
    if (data[key] !== false) throw new Error(`未資格状態が不正です: ${key}`);
  }
  if (data.original_shapes_copied !== 0 || data.old_reference_frames_in_integrated_model !== 0 ||
      data.source_leaf_count !== 83 || data.reference_motor_CAD_nominal_fit !== 'failed' ||
      data.actual_hardware_compatibility !== 'unverified/blocked' ||
      data.original_motor_overlap_mm3 !== 29.606056754452105) throw new Error('公開境界・未解決のmotor条件が欠落しています。');
  if (!Array.isArray(data.parts) || data.parts.length !== 526 || data.model_part_count !== 526 ||
      !Array.isArray(data.joints) || data.joints.length !== 200 || data.fastener_count !== 200) throw new Error('名目筐体の部品・ねじ数が一致しません。');
  const ids = new Set();
  for (const part of data.parts) {
    if (!/^(?:E_|[XYZ]_)[A-Z0-9_]+$/.test(part.id) || ids.has(part.id) ||
        /(?:_LOAD_FRAME|_REF_FRAME|_WHEEL)$/.test(part.id) && !part.id.endsWith('_REF_WHEEL')) throw new Error('未承認・重複した部品IDです。');
    if (!finiteVector(part.bbox_mm, 6) || !finiteVector(part.center_of_mass_mm, 3) ||
        !finiteVector(part.mesh_bbox_mm, 6) || !finiteVector(part.mesh_centroid_mm, 3) ||
        !finiteVector(part.explode_mm, 3) || !Number.isFinite(part.volume_mm3) || part.volume_mm3 <= 0 ||
        !Array.isArray(part.mates) || !Array.isArray(part.joint_ids) ||
        typeof part.is_reference !== 'boolean' || typeof part.is_fastener !== 'boolean') throw new Error(`形状・姿勢・接合情報が不足しています: ${part.id}`);
    ids.add(part.id);
  }
  const joints = new Map(), screws = new Set();
  for (const row of data.joints) {
    const stack = jointStack(row);
    if (joints.has(row.id) || screws.has(row.fastener) || !ids.has(row.fastener) ||
        stack.some(id => !ids.has(id) || id === row.fastener) || new Set(stack).size !== stack.length ||
        stack[0] !== row.clamped_part || stack.at(-1) !== row.receiver) throw new Error(`実在する締結相手・stackがありません: ${row.id}`);
    if (!finiteVector(row.axis, 3) || Math.abs(Math.hypot(...row.axis) - 1) > 1e-8 ||
        !finiteVector(row.seat_point_mm, 3) || !(row.engagement_mm > 0) || !(row.nominal_length_mm > 0) ||
        !['including-head', 'under-head'].includes(row.length_convention) ||
        row.tightening_torque_Nm !== null || row.physical_ready !== false) throw new Error(`ねじの名目条件が不正です: ${row.id}`);
    const total = row.nominal_length_mm + (row.length_convention === 'under-head' ? row.head_height_mm : 0);
    if (!Number.isFinite(total) || Math.abs(total - row.modeled_total_length_mm) > 1e-8) throw new Error('ねじの呼び長さと実全長が一致しません。');
    screws.add(row.fastener);
    joints.set(row.id, row);
  }
  for (const part of data.parts) {
    if (part.mates.some(id => !ids.has(id) || id === part.id) || part.joint_ids.some(id => !joints.has(id)) ||
        part.is_fastener !== screws.has(part.id)) throw new Error(`部品・ねじ台帳の接合対応が一致しません: ${part.id}`);
  }
  if (data.parts.filter(part => part.is_reference).length !== 11 || data.reference_part_count !== 11) throw new Error('参照形状の区分が一致しません。');
  return data;
}

export function jointStack(joint) {
  return joint.stack || [joint.clamped_part, joint.receiver];
}

export function jointLengthText(joint) {
  const convention = joint.length_convention === 'under-head' ? '首下' : '頭を含む';
  return `呼び ${joint.nominal_length_mm} mm（${convention}） / 実全長 ${joint.modeled_total_length_mm} mm`;
}

export function validateEnclosureMesh(payload, assembly) {
  return validateMesh(payload, assembly);
}
