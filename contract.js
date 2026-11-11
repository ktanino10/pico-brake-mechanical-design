export function validateAssembly(data) {
  if (data?.schema !== 'public-brake-assembly-v1' || data.units !== 'mm') {
    throw new Error('部品データの形式またはmm単位が一致しません。公開セットを取り直してください。');
  }
  for (const key of ['whole_fit', 'build_ready', 'physical_ready']) {
    if (data[key] !== false) throw new Error(`公開モデルの未資格状態が不正です: ${key}`);
  }
  if (!Array.isArray(data.parts) || data.parts.length === 0) throw new Error('公開部品がありません。');
  const ids = new Set();
  for (const part of data.parts) {
    if (!/^[A-Z][A-Z0-9_]*$/.test(part.id) || ids.has(part.id)) throw new Error('部品IDが不正または重複しています。');
    if (!Array.isArray(part.mates) || !Array.isArray(part.explode_mm) || part.explode_mm.length !== 3 ||
        !part.explode_mm.every(Number.isFinite) || typeof part.is_reference !== 'boolean') {
      throw new Error(`部品の接合・表示情報が不足しています: ${part.id}`);
    }
    if (!Array.isArray(part.bbox_mm) || part.bbox_mm.length !== 6 || !part.bbox_mm.every(Number.isFinite) ||
        !Number.isFinite(part.volume_mm3) || part.volume_mm3 <= 0) throw new Error(`部品の尺度が不正です: ${part.id}`);
    for (const [field, length] of [['center_of_mass_mm', 3], ['mesh_centroid_mm', 3], ['mesh_bbox_mm', 6]]) {
      if (!Array.isArray(part[field]) || part[field].length !== length || !part[field].every(Number.isFinite)) {
        throw new Error(`部品の独立姿勢情報がありません: ${part.id} / ${field}`);
      }
    }
    if (part.is_fastener && (!part.joint_id || !data.joints?.[part.joint_id] || part.mates.length === 0)) {
      throw new Error(`ねじの相手・接合情報がありません: ${part.id}`);
    }
    ids.add(part.id);
  }
  for (const part of data.parts) {
    if (part.mates.some(id => !ids.has(id) || id === part.id)) throw new Error(`存在しない相手部品があります: ${part.id}`);
    if (part.joint_id && !data.joints?.[part.joint_id]) throw new Error(`接合IDがありません: ${part.id}`);
  }
  for (const axis of ['Z', 'X', 'Y']) {
    const q = data.axis_quaternions_xyzw?.[axis];
    if (!Array.isArray(q) || q.length !== 4 || !q.every(Number.isFinite) || Math.abs(Math.hypot(...q) - 1) > 1e-8) {
      throw new Error(`軸の変換が不正です: ${axis}`);
    }
  }
  return data;
}

export function validateMesh(data, assembly) {
  if (data?.schema !== 'public-brake-mesh-v1' || data.units !== 'mm' || !Array.isArray(data.parts) ||
      data.parts.length !== assembly.parts.length) throw new Error('メッシュの単位・部品数がCAD構成と一致しません。');
  const expected = new Map(assembly.parts.map(part => [part.id, part]));
  const seen = new Set();
  for (const mesh of data.parts) {
    const part = expected.get(mesh.id);
    if (!part || seen.has(mesh.id)) throw new Error('メッシュの部品IDが一致しません。');
    if (!Array.isArray(mesh.positions) || mesh.positions.length < 9 || mesh.positions.length % 3 ||
        !mesh.positions.every(Number.isFinite) || !Array.isArray(mesh.indices) || mesh.indices.length % 3 ||
        mesh.indices.length < 12 || !mesh.indices.every(i => Number.isInteger(i) && i >= 0 && i < mesh.positions.length / 3)) {
      throw new Error(`メッシュの形状データが不正です: ${mesh.id}`);
    }
    const box = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
    mesh.positions.forEach((value, index) => {
      const axis = index % 3;
      box[axis] = Math.min(box[axis], value);
      box[axis + 3] = Math.max(box[axis + 3], value);
    });
    if (box.some((value, i) => Math.abs(value - part.bbox_mm[i]) > 0.12)) {
      throw new Error(`メッシュのmm寸法がCADと一致しません: ${mesh.id}`);
    }
    if (box.some((value, i) => Math.abs(value - part.mesh_bbox_mm[i]) > 1e-6)) {
      throw new Error(`メッシュのbboxが保存された姿勢と一致しません: ${mesh.id}`);
    }
    const centroid = meshCentroid(mesh.positions, mesh.indices);
    if (Math.hypot(...centroid.map((value, i) => value - part.mesh_centroid_mm[i])) > 0.002) {
      throw new Error(`メッシュの重心が保存された姿勢と一致しません: ${mesh.id}`);
    }
    seen.add(mesh.id);
  }
  return data;
}

export function meshCentroid(positions, indices) {
  let volume = 0, x = 0, y = 0, z = 0;
  for (let index = 0; index < indices.length; index += 3) {
    const a = indices[index] * 3, b = indices[index + 1] * 3, c = indices[index + 2] * 3;
    const v = (positions[a] * (positions[b + 1] * positions[c + 2] - positions[b + 2] * positions[c + 1]) +
      positions[a + 1] * (positions[b + 2] * positions[c] - positions[b] * positions[c + 2]) +
      positions[a + 2] * (positions[b] * positions[c + 1] - positions[b + 1] * positions[c])) / 6;
    volume += v;
    x += v * (positions[a] + positions[b] + positions[c]) / 4;
    y += v * (positions[a + 1] + positions[b + 1] + positions[c + 1]) / 4;
    z += v * (positions[a + 2] + positions[b + 2] + positions[c + 2]) / 4;
  }
  if (!Number.isFinite(volume) || Math.abs(volume) < 1e-12) throw new Error('メッシュの体積重心を計算できません。');
  return [x / volume, y / volume, z / volume];
}

export function instanceId(axis, partId) {
  if (!['X', 'Y', 'Z'].includes(axis)) throw new Error('不正な軸');
  return `${axis}_${partId}`;
}

export function torqueText(joint, isFastener) {
  if (!isFastener) return '締付値なし';
  if (joint.torque_Nm === null) return '未決';
  return `${joint.torque_Nm[0]}–${joint.torque_Nm[1]} N·m`;
}
