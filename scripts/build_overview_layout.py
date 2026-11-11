"""Generate independent illustration primitives; never read private CAD or a board model."""
from pathlib import Path
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]


def axis_point(point, axis):
    x, y, z = point
    return {"Z": [x, y, z], "X": [z, -y, x], "Y": [x, z, -y]}[axis]


def build():
    parts = []

    def add(identifier, label, kind, section, position, dimensions, mates=(), axis="Z", explode=(0, 0, 0), **extra):
        parts.append({
            "id": identifier, "label": label, "kind": kind, "section": section,
            "position_mm": list(position), "dimensions_mm": list(dimensions),
            "orientation": axis, "explode_mm": list(explode), "mates": list(mates),
            "is_reference": True, "source_geometry": None,
            "origin": "independently-authored-primitive", "included_in_brake_cad": False,
            "tightening_torque_Nm": None, **extra,
        })

    corners = [(x, y) for x in (-81, 81) for y in (-81, 81)]
    mount_holes = [(63 * math.cos(math.radians(a)), 63 * math.sin(math.radians(a)))
                   for a in (45, 135, 225, 315)]
    board_specs = [
        ("CTRL", "制御基板の参考外形", 52, 40, 28, [44, 32]),
        ("DRIVE", "駆動基板の参考外形", 70, 45, -29, [62, 37]),
    ]
    top_holes = [[x, y, 1.65] for x, y in corners]
    for _, _, _, _, center_y, pitch in board_specs:
        top_holes += [[x, center_y + y, 1.65] for x in (-pitch[0]/2, pitch[0]/2)
                      for y in (-pitch[1]/2, pitch[1]/2)]
    panel_specs = [
        ("TOP", "上側パネル", [176, 176, 3], [0, 0, 86.5], "Z", [0, 0, 70], top_holes),
        ("BOTTOM", "下側パネル", [176, 176, 3], [0, 0, -86.5], "Z", [0, 0, -55],
         [[x, y, 1.65] for x, y in (*corners, *mount_holes)]),
        ("LEFT", "X軸側パネル", [170, 170, 3], [-86.5, 0, 0], "X", [-55, 0, 0],
         [[x, y, 1.65] for x, y in mount_holes]),
        ("RIGHT", "反対側パネル", [170, 170, 3], [86.5, 0, 0], "X", [55, 0, 0], []),
        ("FRONT", "Y軸側パネル", [176, 170, 3], [0, -86.5, 0], "Y", [0, -55, 0],
         [[x, y, 1.65] for x, y in mount_holes]),
        ("BACK", "背面パネル", [176, 170, 3], [0, 86.5, 0], "Y", [0, 55, 0], []),
    ]
    for key, label, size, pos, axis, explode, holes in panel_specs:
        add("REF_CASE_" + key, label, "plate", "case", pos, size, axis=axis, explode=explode, holes=holes,
            note="独立した平板の参考筐体。原Picoの枠・cornerを写したものではありません。板厚3 mmは図示用の仮値です。")
    for i, (x, y) in enumerate(corners):
        add(f"REF_CORNER_POST_{i}", f"筐体の支柱 {i+1}", "tube", "case", [x, y, 0], [7, 3.3, 170],
            ["REF_CASE_TOP", "REF_CASE_BOTTOM"], note="支柱・インサートの配置例です。材質、接合形式、荷重は未資格です。")
        for side, z, flip in (("TOP", 88, True), ("BOTTOM", -88, False)):
            add(f"REF_CASE_SCREW_{side}_{i}", f"{'上' if side == 'TOP' else '下'}パネルの参考ねじ {i+1}",
                "screw", "case", [x, y, z], [3, 12, 5.5, 3],
                [f"REF_CASE_{side}", f"REF_CORNER_POST_{i}"],
                explode=[0, 0, 85 if side == "TOP" else -70], flip=flip,
                note="M3相当の簡略図です。長さ・ねじ込み・インサート・締付値は実部材に合わせた確認が必要です。")
    for axis, panel in (("Z", "BOTTOM"), ("X", "LEFT"), ("Y", "FRONT")):
        for i, (x, y) in enumerate(mount_holes):
            add(f"REF_MODULE_POST_{axis}_{i}", f"{axis}軸と筐体の参考支柱 {i+1}", "tube", "mount",
                axis_point([x, y, -76.5], axis), [7, 3.3, 17], [f"BASE_{axis}", "REF_CASE_" + panel],
                axis=axis, explode=axis_point([0, 0, -16], axis),
                note="公開ブレーキの参考支持リングと、今回の参考筐体をつなぐ位置の例です。全機適合や反力保持の証明ではありません。")
            add(f"REF_MODULE_SCREW_{axis}_{i}", f"{axis}軸側の参考取付ねじ {i+1}", "screw", "mount",
                axis_point([x, y, -88], axis), [3, 10, 5.5, 3],
                ["REF_CASE_" + panel, f"REF_MODULE_POST_{axis}_{i}"], axis=axis,
                explode=axis_point([0, 0, -65], axis),
                note="筐体側の接続位置を示す簡略ねじ。既存C08の締付計算値をこの参考接合へ適用しません。")
    for key, label, width, height, center_y, pitch in board_specs:
        holes = [[x, y, 1.65] for x in (-pitch[0]/2, pitch[0]/2) for y in (-pitch[1]/2, pitch[1]/2)]
        add(f"REF_PCB_{key}", label, "pcb", "pcb", [0, center_y, 74.2], [width, height, 1.6],
            [f"REF_PCB_POST_{key}_{i}" for i in range(4)], explode=[0, 0, 25], holes=holes, hole_pitch_mm=pitch,
            note="製品の基板ではありません。外形・取付穴・絶縁支柱・コネクタ位置は未確定です。緑の板と穴は配置説明のための仮値です。")
        for i, (x, y, _) in enumerate(holes):
            y += center_y
            add(f"REF_PCB_POST_{key}_{i}", f"{'制御' if key == 'CTRL' else '駆動'}基板の絶縁支柱 {i+1}",
                "tube", "pcb", [x, y, 80], [6, 3.3, 10], [f"REF_PCB_{key}", "REF_CASE_TOP"],
                explode=[0, 0, 12], note="長さ10 mmの仮スペーサー。絶縁性・強度・材質・クリアランスの指定ではありません。")
            add(f"REF_PCB_SCREW_{key}_{i}", f"{'制御' if key == 'CTRL' else '駆動'}基板の参考ねじ {i+1}",
                "screw", "pcb", [x, y, 73.4], [3, 18, 5.5, 3],
                [f"REF_PCB_{key}", f"REF_PCB_POST_{key}_{i}", "REF_CASE_TOP", f"REF_PCB_NUT_{key}_{i}"],
                explode=[0, 0, -20], note="M3相当の表示用ねじ。仮の積層を見せるもので、実基板への締付値・推奨ねじではありません。")
            add(f"REF_PCB_NUT_{key}_{i}", f"{'制御' if key == 'CTRL' else '駆動'}基板の参考ナット {i+1}",
                "nut", "pcb", [x, y, 89.2], [5.5, 3.0, 2.4],
                [f"REF_PCB_SCREW_{key}_{i}", "REF_CASE_TOP"], explode=[0, 0, 78],
                note="筐体外側に示した仮の相手部材。実際の固定方式は未選定です。")
    add("REF_BATTERY", "電池の予約外形", "box", "battery", [45, 40, 35], [30, 48, 22],
        ["REF_BATTERY_TRAY", "REF_BATTERY_BAND_0", "REF_BATTERY_BAND_1"], explode=[30, 0, 0],
        note="採用電池ではありません。電圧・容量・保護回路・発熱・端子方向は未確定。既知の1.757 Aと1.5 Aの不整合を解決する図ではありません。")
    add("REF_BATTERY_TRAY", "電池保持部の参考板", "box", "battery", [61, 40, 35], [2, 52, 26],
        ["REF_BATTERY", "REF_CASE_RIGHT"], explode=[42, 0, 0],
        note="保持位置の参考形状です。筐体への実接合・保持強度・熱対策は未設計です。")
    for i, z in enumerate((27, 43)):
        add(f"REF_BATTERY_BAND_{i}", f"電池保持帯の参考形状 {i+1}", "band", "battery", [45, 40, z],
            [34, 52, 2, 31, 49], ["REF_BATTERY", "REF_BATTERY_TRAY"], explode=[32, 0, (i*2-1)*12],
            note="帯の位置だけを説明する独立形状です。材質や締付、電池への圧力は指定していません。")
    ids = {part["id"] for part in parts} | {"BASE_X", "BASE_Y", "BASE_Z"}
    if len(ids) != len(parts) + 3:
        raise ValueError("Duplicate overview reference ID")
    for part in parts:
        if any(mate not in ids or mate == part["id"] for mate in part["mates"]):
            raise ValueError("Invalid overview counterpart: " + part["id"])
        if any(value <= 0 for value in part["dimensions_mm"]):
            raise ValueError("Nonpositive reference dimension")
        for x, y, radius in part.get("holes", []):
            if abs(x)+radius > part["dimensions_mm"][0]/2 or abs(y)+radius > part["dimensions_mm"][1]/2:
                raise ValueError("Reference hole exceeds its plate")
    return parts


def main():
    assembly = json.loads((ROOT / "data/assembly.json").read_text())
    mesh_hash = hashlib.sha256((ROOT / "data/meshes.json").read_bytes()).hexdigest()
    if mesh_hash != assembly["mesh"]["sha256"]:
        raise ValueError("Existing brake mesh identity mismatch")
    parts = build()
    payload = {
        "schema": "brake-reference-overview-v1", "units": "mm",
        "whole_fit": False, "build_ready": False, "physical_ready": False,
        "actual_board_data": False, "original_pico_geometry_used": False,
        "base_mesh_sha256": mesh_hash, "base_parts_per_axis": len(assembly["parts"]),
        "reference_part_count": len(parts), "enclosure_outer_mm": [176, 176, 176],
        "cad_scope": "Existing FCStd/STEP/ZIP contain the brake components only; new overview references are illustration-only.",
        "all_reference_dimensions_are_examples": True, "parts": parts,
        "steps": [
            {"id": "all", "title": "全体を見る", "description": "筐体・3軸ブレーキ・基板・電池の位置関係をまとめて確認します。全機の適合・重心・起立性能は未検証です。"},
            {"id": "case", "title": "筐体と支持部", "description": "6枚の参考パネルと支柱を分けて見ます。原Picoの筐体ではなく、角の固定方法も未資格です。"},
            {"id": "mount", "title": "3軸ブレーキ", "description": "各軸の参考支持リングから筐体への接続位置を示します。支柱の接合・反力保持・工具経路は実証していません。"},
            {"id": "pcb", "title": "基板の固定", "description": "基板 → 絶縁支柱 → 筐体 → 相手ナットの関係を見ます。これは位置関係の説明で、実基板の組立手順ではありません。"},
            {"id": "battery", "title": "電池と余白", "description": "電池の仮外形と保持位置を示します。通線・コネクタ・放熱・保護回路・実固定は未設計です。"},
        ],
    }
    (ROOT / "data/overview-layout.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Independent overview references: {len(parts)}; base brake mesh unchanged.")


if __name__ == "__main__":
    main()
