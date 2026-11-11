"""Public Japanese part and joint descriptions, independent of private files."""
from public_policy import ALLOWED, REFERENCES, family, provenance_for

LABELS = {
    "YOKE": "ヨーク", "POLE_CAP_INNER": "内側の分割磁極蓋",
    "POLE_CAP_OUTER": "外側の分割磁極蓋", "COIL_RETAINER": "コイル押え板",
    "LINING": "摩擦材セグメント", "LINING_KEEPER": "摩擦材の個別押え",
    "RETAINER_BOLT": "磁極蓋・押えの皿ねじ", "BOBBIN": "PEEKボビン",
    "WINDING": "巻線包絡", "BOBBIN_PAD": "ボビン予圧ばね",
    "BOBBIN_REAR_INSULATOR": "ボビン後端絶縁板", "LEAD_BUSHING": "リード絶縁ブッシュ",
    "CARRIER": "固定キャリア", "STATOR_LOCATING_PIN": "ステータ定位ピン",
    "STATOR_BOLT": "ステータ固定ねじ", "STATOR_WASHER": "ステータ座金",
    "POST": "段付き支柱", "FRAME_BOLT": "支持部の通しねじ", "FRAME_NUT": "支持部のナット",
    "BEARING_CAP": "軸受外輪前蓋", "BEARING_OUTER": "軸受外輪・簡略",
    "BEARING_INNER": "軸受内輪・簡略", "HUB_INNER_RACE_REAR_SHIM": "内輪後側の選定シム",
    "BEARING_BALL": "軸受球・簡略", "CAP_BOLT": "軸受前蓋の皿ねじ",
    "RIM_BOLT": "円盤外周の皿ねじ", "RIM_NUT": "円盤外周のナット",
    "HUB": "ハブ軸側", "HUB_FACE": "ハブ表板", "HUB_CONNECT_BOLT": "分割ハブの皿ねじ",
    "HUB_CONNECT_PIN": "ハブの閉じ込めピン", "HUB_RETAINING_RING": "軸止め輪・簡略",
    "HUB_DOWEL": "円盤定位ピン", "POSITIVE_CROSSPIN": "入力横ピン",
    "WHEEL_BOLT": "円盤・ハブの皿ねじ", "WHEEL_NUT": "円盤・ハブのナット",
    "ARMATURE": "可動円盤", "SPRING": "接線板ばね",
    "SPRING_CLAMP_ROOT": "板ばね根元の押え", "SPRING_CLAMP_TIP": "板ばね先端の押え",
    "SPRING_ROOT_BOLT": "板ばね根元の肩付きねじ", "SPRING_TIP_BOLT": "板ばね先端の肩付きねじ",
    "SPRING_ROOT_NUT_PLATE": "板ばね根元の二穴ねじ板",
    "SPRING_TIP_NUT_PLATE": "板ばね先端の二穴ねじ板", "RELEASE_STOP": "解除ストッパ",
    "MOTOR_INTERFACE_BOLT": "モーター側の名目ねじ", "STRAIN_CLAMP": "配線クランプ",
    "STRAIN_INSULATOR": "配線絶縁スリーブ", "STRAIN_INSULATOR_LID": "配線絶縁ふた",
    "LEAD_CRIMP_COLLAR": "肩付き圧着カラー", "INSULATED_LEAD": "絶縁リード",
    "STRAIN_BOLT": "配線クランプねじ",
}

MATERIALS = {
    "magnetic-steel": "低炭素磁性鋼（最終状態のB-H・強度は未資格）",
    "316": "316Lの設計候補", "friction-required": "摩擦材は未選定・未資格",
    "steel": "鋼。ねじの強度区分は接合欄の設計条件",
    "PEEK": "切削・無充填PEEK（印刷樹脂ではない）",
    "copper-winding-pack": "銅巻線の包絡（個々の線は省略）",
    "12R11": "12R11ばね材の設計候補（疲労未資格）",
    "Al": "EN AW6061-T6、材証が必要",
    "42CrMo4": "42CrMo4+QT、耐力600 MPa以上の材証が必要",
    "bearing-steel": "軸受鋼の寸法模式図", "DSH10-ST": "DSH-10寸法候補の模式図",
    "C110-copper": "C110銅の設計候補", "insulated-copper": "絶縁銅線の模式図",
    "reference": "説明用の仮想部材。材質・製造条件を指定しない",
}

CONDITIONS = (
    "C08金属案の条件付き設計計算。ねじ・座面摩擦0.10–0.20、工具±6%、緩和20%の"
    "感度を含む。材証・実摩擦・非一様温度・実締結は未資格。メーカー指定値でも"
    "現物への締付指示でもなく、既存の印刷樹脂へ転用不可。"
)


def joint(title, size, torque, receiver, role, count, grip=None, engagement=None):
    return {
        "title": title, "size": size, "torque_Nm": torque, "receiver": receiver,
        "role": role, "per_axis_count": count, "grip_mm": grip,
        "engagement_mm": engagement, "conditions": CONDITIONS,
        "physical_qualified": False,
    }


JOINTS = {
    "J01": joint("支持枠・支柱・キャリア", "M3×20 / 皿頭 / 10.9", [0.35, 0.45],
                 "C08: class10鋼ナット、6061-T6枠・キャリア、金属支柱。公開版の枠は別の参考リング。",
                 "支柱とキャリアを軸方向に保持。主反力は段付き定位部へ伝える。", 4, 16.5, 2.4),
    "J02": joint("ステータ・キャリア", "M3×12 / 六角穴付き / 12.9", [0.32, 0.42],
                 "低炭素鋼ヨークのM3止まり穴。必要耐力235 MPa以上、座金厚0.5 mm。",
                 "固定磁極をキャリアに保持。トルクは定位ピンで伝える。", 4, 5.5, 6.5),
    "J03": joint("円盤・ハブ表板", "M3×8 / 皿頭 / 10.9", [0.27, 0.32],
                 "42CrMo4+QT表板、class10ナット。公開版は独立の参考円盤で元wheelではない。",
                 "円盤とハブ表板を保持。定位ピンの働きを摩擦締結と混同しない。", 4, 3.2, 2.4),
    "J04": joint("板ばね端・二穴ねじ板", "特注肩付き M2×6 / 10.9", [0.07, 0.09],
                 "42CrMo4+QTねじ板4.7×9×1.6 mm、316L押え。板ばね0.4 mm。樹脂は挟まない。",
                 "金属板ばねを根元・先端で固定。肩径2.08 mmの設計形状。", 12, 4.0, 1.6),
    "J05": joint("分割磁極蓋・押え板・ヨーク", "設計皿ねじ M2.5×8 / 10.9", [0.37, 0.42],
                 "磁極蓋・316L個別押え、ヨーク内M2.5ねじ。切欠き込みの座面を前提にした計算。",
                 "磁極蓋と個別押えを保持し、コイル押えの軸方向の抜けを防ぐ。", 6, 1.8, 6.2),
    "J06": joint("軸受外輪前蓋", "設計皿ねじ M2×6 / 10.9", [0.14, 0.15],
                 "6061-T6キャリアの軸受カートリッジ。必要耐力240 MPa以上。",
                 "外輪だけを保持する。内輪と外輪を締結で予圧する指示ではない。", 3, 1.5, 4.5),
    "J07": joint("配線クランプ", "M2×5 / 六角穴付き / A2-70", [0.04, 0.06],
                 "金属クランプ脚と金属キャリア。PEEKスリーブへ締付軸力を負担させない。",
                 "肩付きカラーを機械捕捉。実圧着の5 N引抜き耐力は未実測。", 2, 2.0, 3.0),
    "J08": joint("解除ストッパ", "特注 M2×2.8 / 肩径4×1.2 / 316L", [0.03, 0.035],
                 "C08では6061-T6 wheelのM2止まり穴。公開版は参考円盤。",
                 "解除位置の名目ストップ。現物での戻り力・隙間は未保証。", 3, 0.0, 2.8),
    "J09": joint("ボビン予圧・抜け止め", "非ねじ接合", None, "ボビン、予圧ばね、前押え、後端座。",
                 "がた止め予圧と20 Nの抜け止め荷重ケースを分離する。", 3),
    "J10": joint("実モーター側・未確認", "名目 M3×7 / 実ねじ仕様は未決", None,
                 "実モーターの型番・穴深さ・材質・巻線との距離が不明。包絡円筒は相手形状を保証しない。",
                 "必要な接続端点の表示。元モーターの取付が成立したという意味ではない。", 3, 3.0, None),
    "J11": joint("円盤の定位ピン", "丸／径方向逃がしピン", None, "ハブ表板と参考円盤の独立ポケット。",
                 "トルクの定位経路。公開参考円盤への強度結果は転用しない。", 2),
    "J12": joint("軸止め輪", "DSH-10寸法候補・模式図", None, "ハブ溝。実輪郭・材料・動的適合が未確認。",
                 "軸方向保持の配置説明。カタログ静定格をブレーキ全体の動定格としない。", 1),
    "J15": joint("分割ハブ表板・ハブ軸", "設計皿ねじ M2×4 / 10.9", [0.17, 0.19],
                 "42CrMo4+QTハブ軸のM2。3本の閉じ込めピンが主トルクを伝える。",
                 "分割ハブの表板を軸方向に保持する。", 3, 1.5, 2.5),
    "J14": joint("参考円盤の等配外周ねじ", "M4×8 / 皿頭 / 10.9", [0.4, 0.5],
                 "C08では6061-T6 wheelとclass10ナット。公開参考リングは異なる形状。",
                 "等配した締結位置を示す。元のリム慣性・バランス・性能は再現しない。", 8, 3.2, 3.2),
    "J16": joint("ステータ定位ピン", "丸／径方向逃がしピン", None, "ヨークとキャリア。",
                 "反力トルクを伝え、熱膨張の径方向逃げを設ける名目設計。", 2),
    "J17": joint("押え板の正の回り止め", "キー／切欠き", None, "押え板とヨーク。",
                 "主トルク経路を接着やねじ座面摩擦だけに頼らない。", 3),
    "J18": joint("3分割ライニング・個別押え", "キー／個別押え", None,
                 "摩擦材は未選定。エッジ強度・接触面圧・摩擦係数・熱が未資格。",
                 "正の回り止めと軸方向保持を示す。材料が確定した製品ではない。", 3),
    "J19": joint("配線の圧着カラー", "捕捉された肩", None, "PEEK絶縁スリーブ、ふた、銅カラー。",
                 "配線引抜き5 Nの設計ケース。実圧着の試験は未実施。", 2),
    "J20": joint("軸受の選定シム", "図示内輪シム0.1 mm", None, "軸受・ハブ・ハウジングの実測寸法が必要。",
                 "内輪と外輪を互いに予圧せず、実寸でスタックを選定する前提。", 1),
    "J21": joint("入力横ピン", "名目径2 mm / 長さ27.4 mm", None,
                 "実モーターの軸径・材質・許容荷重は不明。参考入力軸は実部品ではない。",
                 "軸方向逃げは力の完全分離ではない。摩擦感度では軸荷重が生じ得る。", 1),
}

BOLT_JOINT = {
    "FRAME_BOLT": "J01", "STATOR_BOLT": "J02", "WHEEL_BOLT": "J03",
    "SPRING_ROOT_BOLT": "J04", "SPRING_TIP_BOLT": "J04",
    "RETAINER_BOLT": "J05", "CAP_BOLT": "J06", "STRAIN_BOLT": "J07",
    "RELEASE_STOP": "J08", "MOTOR_INTERFACE_BOLT": "J10",
    "RIM_BOLT": "J14", "HUB_CONNECT_BOLT": "J15",
}


def bolt_mates(name):
    base = family(name)
    if base not in BOLT_JOINT:
        return []
    i = int(name.rsplit("_", 1)[1])
    return {
        "FRAME_BOLT": ["REF_FRAME", f"POST_{i}", "CARRIER", f"FRAME_NUT_{i}"],
        "STATOR_BOLT": [f"STATOR_WASHER_{i}", "CARRIER", "YOKE"],
        "WHEEL_BOLT": ["HUB_FACE", "REF_WHEEL", f"WHEEL_NUT_{i}"],
        "SPRING_ROOT_BOLT": ["HUB_FACE", "REF_WHEEL", f"SPRING_{i//2}",
                             f"SPRING_CLAMP_ROOT_{i//2}", f"SPRING_ROOT_NUT_PLATE_{i//2}"],
        "SPRING_TIP_BOLT": ["ARMATURE", f"SPRING_{i//2}", f"SPRING_CLAMP_TIP_{i//2}",
                            f"SPRING_TIP_NUT_PLATE_{i//2}"],
        "RETAINER_BOLT": [f"LINING_KEEPER_{i//2}", "POLE_CAP_INNER" if i % 2 == 0 else "POLE_CAP_OUTER",
                          "COIL_RETAINER", "YOKE"],
        "CAP_BOLT": ["BEARING_CAP", "CARRIER"],
        "STRAIN_BOLT": ["STRAIN_CLAMP", "CARRIER"],
        "RELEASE_STOP": ["REF_WHEEL", "ARMATURE"],
        "MOTOR_INTERFACE_BOLT": ["CARRIER", "REF_MOTOR_ENVELOPE"],
        "RIM_BOLT": ["REF_WHEEL", f"RIM_NUT_{i}"],
        "HUB_CONNECT_BOLT": ["HUB_FACE", "HUB"],
    }[base]


def make_catalog(material_by_name):
    parts = []
    ids = set(ALLOWED) | set(REFERENCES)
    fastener_connections = {name: bolt_mates(name) for name in ALLOWED if family(name) in BOLT_JOINT}
    for name in (*ALLOWED, *REFERENCES):
        base = family(name)
        reference = name in REFERENCES
        is_bolt = base in BOLT_JOINT
        label = REFERENCES[name]["label"] if reference else LABELS[base]
        if not reference and base != name:
            label += " " + str(int(name.rsplit("_", 1)[1]) + 1)
        material = "reference" if reference else material_by_name[name]
        if material not in MATERIALS:
            raise ValueError(f"Unknown material: {name}")
        if reference:
            group, role, explode = "reference", "説明用の独立参照形状", -65 if name in {"REF_WHEEL", "REF_FRAME"} else 95
        elif is_bolt:
            group, role, explode = "fasteners", "ねじ・締結部", {
                "J01": -95, "J02": 90, "J03": -90, "J04": -62, "J05": -18,
                "J06": -38, "J07": 98, "J08": -55, "J10": 65, "J14": -90, "J15": -90,
            }[BOLT_JOINT[base]]
        elif base in {"WINDING", "BOBBIN", "BOBBIN_PAD", "BOBBIN_REAR_INSULATOR",
                       "YOKE", "POLE_CAP_INNER", "POLE_CAP_OUTER", "COIL_RETAINER",
                       "LINING", "LINING_KEEPER"}:
            group, role = "coil", "固定磁極・コイル保持"
            explode = {"YOKE": 55, "WINDING": 30, "BOBBIN": 30, "BOBBIN_PAD": 18,
                       "BOBBIN_REAR_INSULATOR": 44, "POLE_CAP_INNER": 8, "POLE_CAP_OUTER": 8,
                       "COIL_RETAINER": -4, "LINING": -12, "LINING_KEEPER": -12}[base]
        elif base.startswith(("STRAIN_", "LEAD_", "INSULATED_")):
            group, role, explode = "wiring", "絶縁・配線保持", 70
        elif base in {"CARRIER", "POST", "FRAME_NUT", "STATOR_LOCATING_PIN", "STATOR_WASHER",
                       "BEARING_CAP", "BEARING_OUTER"}:
            group, role, explode = "support", "固定支持部", 75 if base == "CARRIER" else 60
        else:
            group, role, explode = "rotor", "回転側・可動側", -45
            if base == "ARMATURE":
                role, explode = "軸方向に動く円盤", -28
            if base in {"HUB_FACE", "RIM_NUT", "WHEEL_NUT"}:
                explode = -65
        mates = list(fastener_connections.get(name, []))
        if not is_bolt:
            mates = [bolt for bolt, receivers in fastener_connections.items() if name in receivers]
        named_mates = {
            "WINDING": ["BOBBIN", "BOBBIN_REAR_INSULATOR", "COIL_RETAINER", "YOKE",
                        "BOBBIN_PAD_0", "BOBBIN_PAD_1", "BOBBIN_PAD_2"],
            "BOBBIN": ["WINDING", "BOBBIN_REAR_INSULATOR", "COIL_RETAINER", "BOBBIN_PAD_0"],
            "ARMATURE": ["SPRING_0", "SPRING_1", "SPRING_2", "LINING_0", "LINING_1", "LINING_2"],
            "HUB": ["HUB_FACE", "BEARING_INNER", "HUB_RETAINING_RING", "POSITIVE_CROSSPIN", "REF_SHAFT"],
            "COIL_RETAINER": ["YOKE", "POLE_CAP_INNER", "POLE_CAP_OUTER", "BOBBIN", "LINING_0",
                              "LINING_1", "LINING_2"],
        }
        mates += named_mates.get(name, [])
        if base == "BOBBIN_PAD":
            mates += ["BOBBIN", "YOKE", "COIL_RETAINER"]
        if base == "LINING":
            mates += ["ARMATURE", "COIL_RETAINER"]
        mates = list(dict.fromkeys(mates))
        if any(mate not in ids or mate == name for mate in mates):
            raise ValueError(f"Invalid joint endpoint: {name}")
        joint_id = BOLT_JOINT.get(base)
        if not joint_id:
            joint_id = {
                "BOBBIN_PAD": "J09", "HUB_DOWEL": "J11", "HUB_RETAINING_RING": "J12",
                "HUB_CONNECT_PIN": "J15", "STATOR_LOCATING_PIN": "J16", "COIL_RETAINER": "J17",
                "LINING": "J18", "LINING_KEEPER": "J18", "LEAD_CRIMP_COLLAR": "J19",
                "STRAIN_INSULATOR_LID": "J19", "HUB_INNER_RACE_REAR_SHIM": "J20",
                "POSITIVE_CROSSPIN": "J21",
            }.get(base)
        parts.append({
            "id": name, "label": label, "group": group, "role": role,
            "material": MATERIALS[material], "material_code": material,
            "is_reference": reference, "is_fastener": is_bolt, "joint_id": joint_id,
            "mates": mates, "reference_joint": reference or any(m in REFERENCES for m in mates),
            "explode_mm": [0, 0, explode],
            "provenance": "independent-reference" if reference else provenance_for(name)["kind"],
        })
    return parts
