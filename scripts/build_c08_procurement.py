"""Create a procurement inventory from public C08 IDs, never the historical tabletop R1 BOM."""
from collections import Counter, defaultdict
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from public_policy import ALLOWED, REFERENCES

ROOT = Path(__file__).resolve().parents[1]
CHECKED = "2026-11-15"
SOURCE_FILES = ("data/assembly.json", "data/parts.csv", "data/joints.csv", "data/provenance.json",
                "data/c08-procurement-electrical.json")

SOURCES = {
    "JP-METAL": {
        "name": "タシロ・精密板金/切削サービス", "kind": "公式サービス（相談先候補）",
        "url": "https://tasiro.co.jp/business/service/",
        "confirmed": "精密板金/切削を1個から対応、図面があれば個人依頼も受付。DXF推奨、3D/手書き/現物からも相談。",
        "limits": "C08の磁性材、42CrMo4+QT、6061-T6、薄肉公差、熱処理を全て受注できるとは未確認。価格/納期未見積。"},
    "JP-PEEK": {
        "name": "アリス・PEEK試作切削", "kind": "公式サービス（相談先候補）",
        "url": "https://arice-world0917.jp/topics/peek%ef%bc%88%e3%83%9d%e3%83%aa%e3%82%a8%e3%83%bc%e3%83%86%e3%83%ab%e3%82%a8%e3%83%bc%e3%83%86%e3%83%ab%e3%82%b1%e3%83%88%e3%83%b3%ef%bc%89%e8%a9%a6%e4%bd%9c%e5%8a%a0%e5%b7%a5%e3%81%a8%e9%87%8f/",
        "confirmed": "PEEK切削、単品試作・少量ロット対応の記載。",
        "limits": "C08の無充填材等級、0.2/0.3mm薄部、分割形状、公差、検査を受けるかは相談が必要。PLA代替承認ではない。"},
    "JP-SPRING": {
        "name": "理研発条工業・試作品/小ロット", "kind": "公式サービス（相談先候補）",
        "url": "https://www.riken-spring.com/product/prototype/",
        "confirmed": "薄板ばね・コイルばね等を1個から。仮金型、レーザー、精密ベンダーの説明。",
        "limits": "12R11の在庫/支給材、圧延方向・熱処理・バリ・自由形状・疲労要求の対応は未確認。"},
    "MAT-12R11": {
        "name": "Alleima 12R11鋼帯", "kind": "メーカー公式仕様",
        "url": "https://www.alleima.com/en/technical-center/material-datasheets/strip-steel/alleima-12r11/",
        "confirmed": "ばね用オーステナイト系ステンレス鋼帯。標準冷間圧延、強度条件別の厚さ範囲と曲げ/熱処理条件を記載。",
        "limits": "小口国内在庫/価格とC08加工後の特性は未確認。SUS301名への単純置換やPLA化はしない。"},
    "JP-COIL": {
        "name": "釜石電機製作所・専用コイル試作", "kind": "公式サービス（相談先候補）",
        "url": "https://www.e-kamaden.co.jp/coil-manufacturer",
        "confirmed": "専用コイルを1つから試作可能と記載。ブレーキ/マグネットコイル、特殊巻線・専用治具、巻線後処理に対応。",
        "limits": "今回の小型円環796巻・PEEKボビン支給・個人/小口の受入れ、絶縁等級・含浸・検査・価格は個別確認。"},
    "JP-FRICTION": {
        "name": "アスクテクニカ・産業機械用摩擦材", "kind": "メーカー公式製品群・相談窓口",
        "url": "https://www.asktechnica.co.jp/product-category/friction-material/brake-and-clutch/",
        "confirmed": "電磁ブレーキ用途を含むレジンモールド系摩擦材、複数材料の用途区分を掲載。",
        "limits": "3分割の小片/厚さ1.2mm/キー形状の加工、少量販売、具体的材料選定は未確認。製品名だけでC08の摩擦係数を保証しない。"},
    "MAT-MAGNETIC": {
        "name": "特殊金属エクセル・SUY-1", "kind": "メーカー公式素材仕様（比較資料）",
        "url": "https://www.tokkin.co.jp/search/low-carbon-steel/magnetic-iron/suy-1/",
        "confirmed": "電磁軟鉄SUY-1、板/帯の製造範囲0.030〜2.5mm。加工後磁気焼鈍と磁気特性の関係を記載。",
        "limits": "C08磁性鋼をSUY-1に決定したわけではない。掲載板厚上限はヨーク13.2mmや円盤外接厚2.8mmを満たす根拠にならない。厚材は別途調達相談。"},
    "BUY-BEARING-SPEC": {
        "name": "NSK 6800ZZ", "kind": "メーカー公式商品・仕様",
        "url": "https://www.nsk.com/jp-ja/engineering/6800zz-apn.html",
        "confirmed": "内径10/外径19/幅5mm、玉10個・玉径2.381mm、CNすきま、両側鋼板シールド。税別標準1330円/個。",
        "limits": "C08の簡略軸受と寸法/玉数を照合した候補。実荷重・はめあい・温度・予圧は未確認。C5すきまやステンレス別品と混同しない。"},
    "BUY-BEARING-JP": {
        "name": "AXEL エスコEA966ED-800（6800ZZ寸法系）", "kind": "国内販売商品",
        "url": "https://axel.as-1.co.jp/asone/d/64-7971-46/",
        "confirmed": "6800ZZ、10×19×5mm、高炭素クロム軸受鋼、1個入、税別標準820円。",
        "limits": "実売/送料/在庫は未確認。NSK製であることは確認していない。メーカー指定発注時は製造者も照合。"},
    "BUY-RING": {
        "name": "Rotor Clip DSH-10", "kind": "メーカー公式商品・仕様",
        "url": "https://www.rotorclip.com/product/dsh-10/",
        "confirmed": "軸10mm、溝径9.54〜9.60/溝幅1.10、板厚0.94〜1.00mm。DSH-10STには表面処理別品番がある。",
        "limits": "国内小口販売先・価格・在庫は未確認。めっき品の厚さ増分0.05mm注意。C08は模式形状であり元motorとの干渉が未解決。"},
    "BUY-M3-CAP": {
        "name": "NBK SNS-M3-12-EL", "kind": "メーカー公式商品・国内直販",
        "url": "https://www.nbk1560.com/products/specialscrew/nedzicom/socketheadcapscrew/SNS-EL/SNS-M3-EL/SNS-M3-12-EL/",
        "confirmed": "M3×12、頭径5.5/頭高さ3、SCM435・無電解Ni・強度12.9、20本/袋・税込594円、在庫品表示。",
        "limits": "現行STATOR_BOLTの規格候補。表面摩擦・相手材を再確認。C08条件付き締付計算の無条件適用不可。小頭SD品と別。バラは別手数料。"},
    "MAT-WIRE": {
        "name": "古河マグネットワイヤ・エナメル線", "kind": "メーカー公式製品群",
        "url": "https://www.furukawa-magnetwire.co.jp/products/index.htm#enamel",
        "confirmed": "各種エナメル線・巻線応用品の開発製造と相談先の案内。",
        "limits": "C08の線径・被膜種・絶縁等級・小口線長/価格は未確定。自作時の線材候補選定用で、796巻だけでは線径を決めない。"},
    "MAT-TAPE": {
        "name": "Nitto No.360UL系ポリイミド粘着テープ", "kind": "メーカー公式製品仕様",
        "url": "https://www-origin.nitto.com/jp/ja/products/e_parts/heat_resistant001/",
        "confirmed": "耐熱電気絶縁向け。360UL全厚0.055/0.080mm、標準20m、細幅加工対応の記載。",
        "limits": "巻線/PEEK/含浸材との相性、幅・巻重ね・完成寸法・絶縁の採用試験が必要。保証値やC08への適合認定ではない。"},
    "TOOL-CALIPER": {
        "name": "シンワ19899 普及ノギス150mm", "kind": "メーカー公式商品・国内直販",
        "url": "https://www.shinwasokutei-onlineshop.com/shopdetail/000000002414/",
        "confirmed": "ステンレス、デプスバー・ケース付、最小読取0.05mm、最大許容誤差±0.1mm。税込7876円、残3個表示。",
        "limits": "一般外形確認用の例。0.20mm空隙の精密検査・軸/軸受のはめあい合否には精度不足。所有/借用で代替可。"},
    "TOOL-FEELER": {
        "name": "シンワ73776 シックネスゲージA75mm9枚組", "kind": "メーカー公式商品・国内直販",
        "url": "https://www.shinwasokutei-onlineshop.com/shopdetail/000000003256/7/page1/order/",
        "confirmed": "0.04/0.05/0.06/0.07/0.08/0.10/0.15/0.20/0.30mmの9枚、幅13mm、ケース付き。税込1067円、残5個表示。",
        "limits": "0.20mmリーフ許容差±0.012mm、積層時は許容差加算。炭素工具鋼なので無通電/静止時専用、測定後除去。挿入経路/面傷/最終公差を確認。"},
}
for _source in SOURCES.values():
    _source["checked_on"] = CHECKED

CONFIG = {
    "YOKE": ("加工依頼", "JP-METAL;MAT-MAGNETIC", "固定磁路と摩擦反力を受ける", "磁性鋼等級・最終B-H/耐力・焼鈍/防錆・基準面・M3ねじ深さ", "磁性鋼をSS400/SUY-1へ勝手に置換しない。"),
    "POLE_CAP_INNER": ("加工依頼", "JP-METAL;MAT-MAGNETIC", "内側磁極と巻線の前方保持", "切欠き・磁極高さ・面平行度・仕上げ・熱処理・全M3化後の穴/頭逃げ", ""),
    "POLE_CAP_OUTER": ("加工依頼", "JP-METAL;MAT-MAGNETIC", "外側磁極と巻線の前方保持", "切欠き・磁極高さ・面平行度・仕上げ・熱処理・全M3化後の穴/頭逃げ", ""),
    "COIL_RETAINER": ("加工依頼", "JP-METAL", "巻線/摩擦材の保持とキー回り止め", "316L・板厚/曲げ/キー・バリ・磁極との段差・穴位置", "接着だけを主反力経路にしない。"),
    "LINING": ("加工依頼", "JP-FRICTION", "可動円盤と接触する固定摩擦材", "材料名・温度/面圧/速度別摩擦・接線荷重・3分割/キー/板厚・許容摩耗", "3枚。材料は未選定。旧R1の天然ゴムを転用しない。"),
    "LINING_KEEPER": ("加工依頼", "JP-METAL;JP-FRICTION", "摩擦材の個別抜け止め", "316L・曲面/切欠き・板厚・接触端面・新M3座面", ""),
    "RETAINER_BOLT": ("加工依頼", "JP-METAL", "磁極蓋と摩擦材押えの締結", "現行M2.5設計皿ねじの頭形状・強度/表面・全M3変更後スタック", "名称だけM3へ置換しない。"),
    "BOBBIN": ("加工依頼", "JP-PEEK;JP-COIL", "巻線を磁性材から絶縁して保持", "無充填PEEK等級・巻線窓・薄肉・フランジ・引出し・成形公差・温度", "図示円環外形は巻線付き市販ボビンではない。PLA不可。"),
    "WINDING": ("巻線依頼または自作", "JP-COIL;MAT-WIRE;MAT-TAPE", "吸引磁界を作るリング状巻線", "796巻・外径82.6/内径61.4/軸長7.3の包絡・線径/被膜・R/L・電圧/電流/温度・含浸・リード・絶縁試験", "完成巻線1個。原材料行は委託内容に含めるなら二重手配しない。"),
    "BOBBIN_PAD": ("加工依頼", "JP-SPRING;MAT-12R11", "ボビンのがた止め予圧", "12R11状態・自由形状/予圧・板厚・圧延向き・熱処理・端面", "3個。接線板ばねとは別部品。"),
    "BOBBIN_REAR_INSULATOR": ("加工依頼", "JP-PEEK;JP-COIL", "ボビン後端絶縁", "無充填PEEK候補・名目0.3mm・絶縁/温度・表面傷・外形公差", ""),
    "LEAD_BUSHING": ("加工依頼", "JP-PEEK;JP-COIL", "巻線引出しを金属端面から絶縁", "PEEK候補・リード径/被覆/曲げ半径・穴/肩・耐熱", ""),
    "CARRIER": ("加工依頼", "JP-METAL", "固定磁極・軸受・機体接続の支持", "EN AW6061-T6材証・軸受はめあい・基準面・ピン孔・PCD/工具空間", "元motor由来PCD30は現物適合保証ではない。PLAへ置換しない。"),
    "STATOR_LOCATING_PIN": ("加工依頼", "JP-METAL", "ヨークからキャリアへ反力を伝える", "42CrMo4+QT・丸/逃がしの2種・径/長さ/公差・硬度・穴はめあい", "2形状を同じ丸ピン2本と注文しない。"),
    "STATOR_BOLT": ("市販購入", "BUY-M3-CAP", "ヨークとキャリアの締結", "M3×12/12.9・頭径5.5/高さ3・座金0.5・かかり6.5の名目値と現物照合", "候補はSNS-M3-12-EL。20本袋なら1軸4本/3軸12本とも1袋で足りる参考計算。"),
    "STATOR_WASHER": ("市販購入", "JP-METAL", "ステータねじの座面", "鋼・外径7/厚さ0.5の名目形状・内径/硬さ/平面度", "規格/硬さまで確認した販売品番は未選定。加工先への一括手配相談候補。"),
    "POST": ("加工依頼", "JP-METAL", "機体/固定台とキャリアの段付き位置決め", "鋼・段部/長さ/穴・座面直角度・相手固定枠/全M3接合", "単純なPLA支柱や一般スペーサーの代用ではない。"),
    "FRAME_BOLT": ("市販購入", "JP-METAL", "支持枠・支柱・キャリアの保持", "現行M3×20皿10.9・頭部/座面・かかり・工具アクセス", "市販規格照合/一括手配相談。最終品番未選定。"),
    "FRAME_NUT": ("市販購入", "JP-METAL", "支持ねじの受け", "現行M3鋼ナットclass10・高さ2.4候補・二面幅/表面", "class10とA2-70などを混同しない。"),
    "BEARING_CAP": ("加工依頼", "JP-METAL", "軸受外輪だけの保持", "6061-T6・外輪接触面/逃げ・全M3後の皿孔・予圧なしのスタック", ""),
    "BEARING_ASSEMBLY": ("市販購入", "BUY-BEARING-SPEC;BUY-BEARING-JP", "回転ハブの支持", "6800寸法系10×19×5・すきま/精度/シールド/潤滑・はめあい/荷重/温度", "内輪1＋外輪1＋玉10の12形状を完成軸受1個へ統合。球・保持器・シールドを別買いしない。"),
    "HUB_INNER_RACE_REAR_SHIM": ("加工依頼", "JP-METAL", "内輪の軸方向スタック調整", "鋼・図示ID10.05/OD12/厚さ0.1mm・バリ/平面度・実測後厚さ選定", "0.1mmは現在の図示値。必要厚さは公差スタックの実測で選ぶ。"),
    "CAP_BOLT": ("加工依頼", "JP-METAL", "軸受外輪前蓋の保持", "現行設計M2×6皿10.9・M3改訂後の頭/相手肉厚", ""),
    "RIM_BOLT": ("市販購入", "JP-METAL", "参考円盤外周の等配締結位置", "現行M4×8皿10.9・実ホイール設計/M3化後の個数/強度/バランス", "現行8本は参考円盤に接続。実ホイールの購入・回転強度を認めた数ではない。"),
    "RIM_NUT": ("市販購入", "JP-METAL", "外周ねじの受け", "現行M4/class10/高さ3.2候補・実ホイールとM3化後の寸法", ""),
    "HUB": ("加工依頼", "JP-METAL", "入力軸と回転側のトルク伝達", "42CrMo4+QT/耐力600MPa以上候補・軸径/溝/ピン孔/公差・所有D軸との接続", "既知D軸A6/B15/C4/D5mmを使用。参考横孔を所有軸へ加工する指示ではない。"),
    "HUB_FACE": ("加工依頼", "JP-METAL", "ホイールとばね根元の取付", "42CrMo4+QT・平面度/板厚・ばね根元位置・全M3後の肉厚/頭逃げ", ""),
    "HUB_CONNECT_BOLT": ("加工依頼", "JP-METAL", "分割ハブの軸方向締結", "現行設計M2×4皿10.9・M3改訂後の頭/ねじ深さ", ""),
    "HUB_CONNECT_PIN": ("加工依頼", "JP-METAL", "分割ハブの主トルク伝達", "42CrMo4+QT・図示径3/長2.75・穴はめあい/閉じ込め", ""),
    "HUB_RETAINING_RING": ("市販購入", "BUY-RING", "ハブの軸方向保持", "DSH-10STの処理付き完全品番・溝径/幅・肩・相手motorとの逃げ", "原motor CADとの29.606mm3干渉未解決。めっきの厚さ増分にも注意。国内手配先未確認。"),
    "HUB_DOWEL": ("加工依頼", "JP-METAL", "ホイールをハブに定位", "42CrMo4+QT・丸/径方向逃げの2種・径/長/はめあい", "2形状を同一汎用ピンとみなさない。"),
    "POSITIVE_CROSSPIN": ("加工依頼", "JP-METAL", "入力トルクの正の伝達", "42CrMo4+QT・現行径2/長27.4・横孔/端面/強度と所有軸の適合", "所有モーター軸への穴あけを承認しない。"),
    "WHEEL_BOLT": ("市販購入", "JP-METAL", "ホイールとハブ表板の保持", "現行M3×8皿10.9・実ホイール/座面/かかり・全M3再評価", "市販規格の照合と最終品番選定が必要。"),
    "WHEEL_NUT": ("市販購入", "JP-METAL", "ホイール締結ねじの受け", "現行M3/class10/厚2.4候補・表面・実ホイール側スタック", ""),
    "ARMATURE": ("加工依頼", "JP-METAL;MAT-MAGNETIC", "固定摩擦面へ軸方向移動する円盤", "磁性鋼・名目OD92/外接厚2.8・摩擦面平行度/振れ・磁気/熱処理/表面・全M3", "PLAや旧手動樹脂円盤に置換しない。0.20mmは名目移動量。"),
    "SPRING": ("加工依頼", "JP-SPRING;MAT-12R11", "可動円盤の復帰と回転トルク伝達", "12R11・板厚0.4候補(J04)/自由形状・圧延向き/熱処理・端部/疲労・M3根元/先端", "外接厚0.6は形成形状を含む。板厚0.6の素材を買う意味ではない。"),
    "SPRING_CLAMP_ROOT": ("加工依頼", "JP-METAL;JP-SPRING", "接線ばね根元の金属押え", "316L・名目7×7×0.4・孔/バリ/端面・M3化後面圧", ""),
    "SPRING_CLAMP_TIP": ("加工依頼", "JP-METAL;JP-SPRING", "接線ばね先端の金属押え", "316L・形成形状/外接厚0.6・孔/端面・M3化後面圧", "根元押えと同一形状としてまとめない。"),
    "SPRING_ROOT_BOLT": ("加工依頼", "JP-METAL;JP-SPRING", "板ばね根元締結", "現行肩付きM2×6/10.9・肩径2.08・全M3後の肩/孔/工具/荷重", "汎用M3へ名前だけ置換しない。"),
    "SPRING_TIP_BOLT": ("加工依頼", "JP-METAL;JP-SPRING", "板ばね先端締結", "現行肩付きM2×6/10.9・肩径2.08・全M3後の肩/孔/工具/荷重", ""),
    "SPRING_ROOT_NUT_PLATE": ("加工依頼", "JP-METAL;JP-SPRING", "根元側二穴ねじ板", "42CrMo4+QT・4.7×9×1.6の名目外形・全M3後のねじ/肉厚", ""),
    "SPRING_TIP_NUT_PLATE": ("加工依頼", "JP-METAL;JP-SPRING", "先端側二穴ねじ板", "42CrMo4+QT・4.7×9×1.6の名目外形・全M3後のねじ/肉厚", ""),
    "RELEASE_STOP": ("加工依頼", "JP-METAL", "解除位置を決める肩付きストッパ", "現行M2×2.8/肩径4×1.2/316L・全M3後の形状/隙間調整", "現物の戻り力/空隙を保証しない。"),
    "MOTOR_INTERFACE_BOLT": ("対象外", "JP-METAL", "名目motor接続点の表示", "現行M3×7の名目3本・実ねじ規格/孔深さは未確定", "所有モーター用として3本購入しない。適合設計後に実部品を別手配。"),
    "STRAIN_CLAMP": ("加工依頼", "JP-METAL", "配線の引張り止め", "6061-T6・脚/金属座面・リード肩の捕捉・全M3孔", ""),
    "STRAIN_INSULATOR": ("加工依頼", "JP-PEEK;JP-COIL", "リード絶縁と保持", "PEEK等級・線径/耐熱・ふた/カラーとの逃げ・クランプ荷重を負担しない形状", ""),
    "STRAIN_INSULATOR_LID": ("加工依頼", "JP-PEEK;JP-COIL", "リード絶縁ふた", "PEEK・名目厚0.2・保持/加工公差・温度", ""),
    "LEAD_CRIMP_COLLAR": ("加工依頼", "JP-METAL;JP-COIL", "配線肩部の機械的捕捉", "C110銅・外形/穴・圧着条件/工具・引抜き試験", "C08の引抜き5N設計ケースは実試験済みではない。"),
    "INSULATED_LEAD": ("巻線依頼または自作", "JP-COIL;MAT-WIRE", "コイルと端子の接続", "図示絶縁外径1mmは模式形状・実芯線断面/被覆/定格/長さ/曲げ半径", "巻線委託に含めるならリードだけ重複購入しない。"),
    "STRAIN_BOLT": ("市販購入", "JP-METAL", "配線クランプ固定", "現行M2×5六角穴付き/A2-70・M3化後のスタック/座面", "現在のM2を購入確定しない。"),
}

EXTRAS = [
    ("OWN-MOTOR", "所有モーター", "手持ち", 1, "台", "軸ごと", [],
     "Nidec24H055M020。申告A=円径6/B=有効突き出し15/C=D面から反対曲面4/D=D部軸方向長5mm",
     "手持ち1台・新規購入0。C08接続/電気定格/軸許容荷重は未確認。追加写真を前提にしない。"),
    ("OWN-HARNESS", "所有12極ハーネス", "手持ち", 1, "本", "軸ごと", [],
     "黄/青/白/緑/橙/茶/灰/紫/黒/黒/赤/赤は観察色順。メーカー端子番号ではない",
     "新規購入0。不良が見つかった場合だけ代替選定。"),
    ("COIL-WIRE", "エナメル銅線（巻線原材料）", "巻線依頼または自作", None, "m", "消耗量設計後", ["MAT-WIRE", "JP-COIL"],
     "796巻の包絡だけでは線径/被膜/長さ/質量/R/L/耐熱等級を決めない",
     "完成巻線の見積に含むなら別購入不要。自作なら線材証明・巻き方・絶縁/温度の計画が必要。"),
    ("COIL-INSULATION", "巻線間/ボビン/引出しの絶縁材", "市販購入", None, "巻", "消耗量設計後", ["MAT-TAPE", "JP-COIL"],
     "No.360UL等の耐熱絶縁テープは候補。厚さ0.055/0.080mmと巻重ねで包絡が変化",
     "幅/重ね数・被着体/含浸の相性・絶縁性能を決める。ボビンの代用ではない。"),
    ("COIL-TREATMENT", "含浸ワニス/巻線固定材/必要な接着材", "巻線依頼または自作", 1, "式", "軸ごと", ["JP-COIL"],
     "巻線後処理・耐熱/絶縁/硬化収縮・リード固定を製作条件に含める",
     "銘柄/硬化条件未確定。C08のキー/押え・反力経路を接着だけへ変更しない。"),
    ("ACTUAL-WHEEL", "実機用ホイール/慣性体", "加工依頼", 1, "個", "軸ごと", ["JP-METAL"],
     "REF_WHEELは参照。実材/慣性/強度/バランス/ハブ取付を決めた部品が別途必要",
     "形状・試験回転数・エネルギーとM3化の設計後。旧手動樹脂円盤をモーターで回さない。"),
    ("ACTUAL-INTERFACE", "所有モーターとC08の取付/軸連結部", "加工依頼", 1, "式", "軸ごと", ["JP-METAL"],
     "所有D軸4寸法を保持。C08の参考PCD30/横孔/軸止め輪をそのまま適合とはしない",
     "新規機構は作らない。全M3化・既知干渉・許容荷重/逃げの解決後に手配。"),
    ("TEST-FIXTURE", "静止吸着試験の固定台・反力受け・拘束具", "加工依頼", 1, "式", "共用・順次試験", ["JP-METAL"],
     "C08単軸を保持する非回転治具。吸着/解除荷重・可動部捕捉・工具空間を設計",
     "図示REF_FRAMEを市販台座とみなさない。1軸ずつ試すなら共用1式、三軸機体は別設計。"),
    ("GUARD", "接触・挟み込み・飛散に対する防護", "加工依頼", 1, "式", "共用・順次試験", ["JP-METAL"],
     "金属支持と必要な透明板等。材厚/固定法/開口/エネルギー条件は未決",
     "窓口は相談候補。PLAや任意の薄板を飛散防護として認定しない。"),
    ("PLA-GAUGE", "無通電の位置合わせ/寸法確認用補助治具", "PLA印刷候補", 1, "式", "共用・順次試験", [],
     "非磁性・非回転・荷重を受けない検討用。現在実機適合した印刷STLはない",
     "設計待ち。磁路/可動円盤/接線ばね/摩擦面/金属支持/PEEKを置換しない。"),
    ("PLA-ELECTRONICS", "低温側の基板/端子/配線ホルダ", "PLA印刷候補", 1, "式", "共用・順次試験", [],
     "電装部品/温度/絶縁距離が確定した後の補助品。現状の適合STLなし",
     "R1用STLをC08用として発注/印刷承認しない。"),
    ("PLA-STOCK", "PLAフィラメント（補助治具分）", "市販購入", None, "g", "消耗量設計後", [],
     "所有品の銘柄/残量を確認。造形体積/条件が決まるまで必要量を作らない",
     "主構造材・磁性材・ばね・摩擦材として購入しない。"),
    ("TOOL-CALIPER", "外形/突き出し長確認用ノギス", "市販購入", 1, "本", "共用・順次試験", ["TOOL-CALIPER"],
     "シンワ19899/150mm/最小読取0.05mm/最大許容誤差±0.1mm。ケース込み",
     "一般外形測定用。はめあい・0.20mm空隙の合否は別の精密計測を要する。所有/借用も可。"),
    ("TOOL-FEELER", "無通電のすきま比較用リーフゲージ", "市販購入", 1, "組", "共用・順次試験", ["TOOL-FEELER"],
     "シンワ73776/9枚組、0.20mmを含む、幅13mm、ケース込み",
     "炭素工具鋼、通電時に挟まない。0.20mm板の許容差±0.012mm、挿入経路と面傷に注意。"),
    ("TOOL-PRECISION", "精密寸法/振れ/面平行度検査", "工具借用または測定依頼", 1, "式", "共用・順次試験", ["JP-METAL"],
     "公差に適合するマイクロメーター/内径ゲージ/ダイヤルゲージ・定盤・測定保持具",
     "最終公差/分解能/測定不確かさで選定。加工先の検査成績書で代替する項目を定義。"),
    ("TOOL-ASSEMBLY", "ねじ・止め輪・部品保持の組立工具", "市販購入", 1, "式", "共用・順次試験", ["BUY-RING", "JP-METAL"],
     "最終ねじ頭に適合する六角/ドライバー・トルク工具・ピンセット・保持治具・軸止め輪プライヤー",
     "DSH-10公式はRPA系工具を案内。実工具先端/アクセスとM3改訂後トルク範囲を確認。所有/借用分は買わない。"),
]

ELECTRICAL_GAPS = [
    ("PC-SETUP", "PC・必要なUSB変換・書込環境", 1, "式", "共用・順次試験", ["EP02"],
     "PCの所有/USB端子/OSを確認。データ対応変換が必要な場合だけ追加。電磁石の駆動FWは未実装。"),
    ("POWER-WIRE", "電力用被覆電線", None, "m", "回路設計後", ["EP14", "EP15"],
     "最終電流・電圧・温度・経路で線径/赤黒各長さ/端末を選定。R1の0.5mm2×2mを自動転用しない。"),
    ("WIRE-ENDS", "圧着端末・スプライス・絶縁熱収縮", None, "式", "回路設計後", ["EP14", "EP15"],
     "導体太さ/端子仕様/温度に適合する端末、チューブ、識別ラベルを選定。細いmotorリードを不適合端子へ直接固定しない。"),
    ("WIRE-RESTRAINT", "配線結束・引張止め・端子固定具", 1, "式", "回路設計後", ["EP14"],
     "回転/可動部から離す経路、曲げ半径、固定、端子間隔を設計。PLA低温ホルダ候補行と重複しない。"),
    ("FUSES", "ヒューズ本体と予備", None, "本", "回路設計後", ["EP15"],
     "ホルダとは別売。主/枝の電流・DC遮断容量・時間特性・突入/誘導性負荷で決める。旧R1の1A/2Aを移さない。"),
    ("PASSIVES", "信号のプル抵抗・直列抵抗・容量部品", None, "個", "回路設計後", ["EP08", "EP10", "EP11", "EP12", "EP13"],
     "GPIO、電源/OE/Enable、信号フィルタの値/数はC08回路設計で決定。リード品または実装済み基板、SMD手実装を要求しない。"),
    ("PROTECTION", "温度/電流保護・遮断クランプ・回生対策", None, "式", "回路設計後", ["EP06", "EP08", "EP15", "EP16"],
     "巻線R/L/最大電流/温度・電源吸収能力・解除時間を確定して設計。汎用ダイオードやスイッチだけで保護完成とはしない。"),
    ("WAVEFORM", "電流減衰/解除応答の波形計測", 1, "式", "共用・順次試験", ["EP17"],
     "オシロスコープ/適合電流・差動プローブまたは外部測定。絶縁/レンジ/帯域を指定。PE必須測定器の接地は省略しない。DMM表示のみでは不可。"),
    ("OPTICAL-MARKER", "回転検出の光学マーカー・非摩擦域保持具", 1, "式", "軸ごと", ["EP13"],
     "C08の非摩擦面に脱落/バランスを考慮して配置し周期数/半径/取付を決める。旧R1の12周期/寸法を流用しない。"),
    ("ELECTRIC-TOOLS", "はんだ/配線の工具と作業環境", 1, "式", "共用・順次試験", ["EP10", "EP14"],
     "こて/台/はんだ/換気・局所排気、ニッパー/被覆剥き/保持具、適合圧着工具。所有/借用確認。PE不要の適合電源構成を確認し、接地必須工具は除外。"),
    ("THREE-AXIS-SYSTEM", "三軸完成機の電池・IMU・制御全機配線", None, "式", "今回対象外", [],
     "必要性のみ記録。1軸の段階試験/共通計測電源とは別設計。既存筐体の参照形状を完成機購入BOMへ変換しない。"),
]


def make_row(identifier, name, role, category, quantity, unit, rule, sources, spec, notes, ids=()):
    return {
        "id": identifier, "name": name, "role": role, "c08_ids": list(ids), "cad_shape_count": len(ids),
        "category": category, "current_spec": spec, "nominal_bbox_mm": "",
        "one_axis_quantity": quantity, "unit": unit,
        "three_axis_reference_quantity": quantity * 3 if rule == "軸ごと" and quantity is not None else quantity if rule == "共用・順次試験" else None,
        "additional_for_three_axes": quantity * 2 if rule == "軸ごと" and quantity is not None else 0 if rule == "共用・順次試験" else None,
        "quantity_basis": rule, "after_M3_redesign_quantity": None,
        "purchase_unit": "最小販売単位/小口対応は要確認", "owned_quantity": None, "new_purchase_for_one_axis": None,
        "included_and_duplicates": notes, "sources": sources,
        "display_price_jpy": None, "price_basis": "未見積", "shipping_stock": "送料/在庫/納期未確認",
        "readiness": "設計後に見積相談・製作発注は保留", "hold_reason": notes,
        "request_information": "", "physical_qualified": False,
    }


def electrical_rows(evidence):
    if evidence["schema"] != "c08-electrical-procurement-evidence-v1":
        raise ValueError("Unsupported electrical evidence schema")
    ids = [p["id"] for p in evidence["items"]]
    if len(ids) != 19 or set(ids) != {f"EP{i:02d}" for i in range(1, 20)}:
        raise ValueError("Electrical evidence must retain the19 distinct sourced items")
    sources, rows = {}, []
    included_from_facts = {
        "EP10": "細ピンヘッダー付属。基板上ICは実装済み、ヘッダーは別途はんだ付け。",
        "EP12": "ヘッダー付属、基板上ICは実装済み。",
        "EP17": "TL-23aテストリード付属。単3電池2本使用（電池の付属は未確認）。",
        "EP18": "AD-1214相当Kセンサー1個、保護ケース、モニター用9V電池が付属。",
    }
    per_axis = {"EP08", "EP11", "EP13"}
    circuit_dependent = {"EP09", "EP10", "EP12", "EP14", "EP15", "EP16"}
    for entry in evidence["items"]:
        key = entry["id"]
        source = {"name": entry["name"] + " / " + entry["model"],
                  "kind": entry["source_level"], "url": entry["shop_url"],
                  "checked_on": evidence["checked_on"],
                  "confirmed": entry["facts"], "limits": entry["notes"]}
        if key in {"EP16", "EP18", "EP19"}:
            source["confirmed"] = "販売入口。型番の照合経路と本文取得制限はkindを参照。仕様の根拠は別のメーカーURL。"
        sources[key] = source
        keys = [key]
        for field, kind in (("spec_url", "メーカー公式仕様"), ("label_url", "メーカー公式ラベル・目視確認"),
                            ("datasheet_url", "メーカー公式仕様PDF")):
            if field in entry:
                part_key = key + "-" + field
                sources[part_key] = {**source, "kind": kind, "url": entry[field],
                                     "confirmed": entry["facts"]}
                keys.append(part_key)
        rule = "軸ごと" if key in per_axis else "回路設計後" if key in circuit_dependent else "共用・順次試験"
        included = entry.get("included", included_from_facts.get(key, ""))
        row = make_row(key, entry["name"], "C08段階試験の電装/計測候補・採用BOMではない", "市販購入",
                       entry["one_axis_quantity"], entry["unit"], rule, keys,
                       entry["model"] + " / " + entry["facts"],
                       included + " " + entry["notes"] + " " + entry["scaling"])
        row.update(
            purchase_unit="; ".join([entry["unit"], included or "同梱品と単位は商品ページで照合"]),
            display_price_jpy=entry["price_yen_tax_included"],
            price_basis="税込販売表示/購入単位" if entry["price_yen_tax_included"] is not None else entry.get("price_note", "税込実売未確認"),
            shipping_stock=evidence["checked_on"] + ": " + entry["availability_observed"] + "。送料/現在の確保は未確認",
            readiness=entry["release"], hold_reason=entry["notes"],
            request_information="型番・入力/出力/端子・最終数量・電源/絶縁・過渡/温度とC08要求の照合",
        )
        if key == "EP19":
            row["category"] = "工具借用または測定依頼"
        rows.append(row)
    for key, name, quantity, unit, rule, source_ids, note in ELECTRICAL_GAPS:
        row = make_row(key, name, "部材値未定でも必要性を落とさない項目", "市販購入", quantity, unit, rule,
                       source_ids, note, "完成品に含む場合/所有・借用時は二重手配しない。")
        row["hold_reason"] = note
        row["request_information"] = "機能/仕様/検査条件と既存候補との付属・重複を確認"
        if key in {"PC-SETUP", "ELECTRIC-TOOLS", "WAVEFORM"}:
            row["readiness"] = "所有/借用・使用条件を確認して準備"
        if key == "WAVEFORM":
            row["category"] = "工具借用または測定依頼"
        if key == "THREE-AXIS-SYSTEM":
            row.update(category="対象外", readiness="三軸完成機は今回の数量/価格集計対象外")
        rows.append(row)
    return sources, rows


def build(electrical):
    assembly = json.loads((ROOT / "data/assembly.json").read_text())
    groups = defaultdict(list)
    for p in assembly["parts"]:
        family = re.sub(r"_\d+$", "", p["id"])
        groups[family].append(p)
    bearing = [*groups.pop("BEARING_OUTER"), *groups.pop("BEARING_INNER"), *groups.pop("BEARING_BALL")]
    groups["BEARING_ASSEMBLY"] = bearing
    rows = []
    sources = dict(SOURCES)
    for family, items in groups.items():
        ids = [p["id"] for p in items]
        reference = all(p["is_reference"] for p in items)
        if reference:
            row = make_row("C08-" + family, items[0]["label"], "表示上の独立参考形状", "対象外", 0, "個", "対象外", [],
                           "元Picoの実部品ではない参照プリミティブ。実材/性能/製作は未指定。",
                           "調達数0。実ホイール/取付/固定台は別の追加行で必要性を示す。", ids)
            row["readiness"] = "調達対象外"
            row["purchase_unit"] = "購入しない"
            row["new_purchase_for_one_axis"] = 0
        else:
            if family not in CONFIG:
                raise ValueError("Missing C08 procurement policy: " + family)
            category, source_ids, role, request, notes = CONFIG[family]
            quantity = 1 if family == "BEARING_ASSEMBLY" else len(items)
            joint = assembly["joints"].get(items[0].get("joint_id"), {})
            spec = items[0]["material"] + (f" / {joint['size']}" if items[0]["is_fastener"] and "size" in joint else "")
            row = make_row("C08-" + family, re.sub(r"\s+\d+$", "", items[0]["label"]) if family != "BEARING_ASSEMBLY" else "完成軸受（6800寸法系）",
                           role, category, quantity, "個" if family == "BEARING_ASSEMBLY" else "点", "軸ごと",
                           source_ids.split(";"), spec, notes, ids)
            row["request_information"] = "公開STEPの対象IDと2D製作図/公差/材証/仕上げ/検査条件。 " + request
            row["hold_reason"] = "全M3化/所有モーター適合/実材条件が未完了。 " + request
            if family == "WINDING":
                row["current_spec"] += " / 796巻;包絡OD82.6/ID61.4/軸長7.3mm（線径ではない）"
            if category == "対象外":
                row["readiness"] = "実モーター接続用としての発注対象外"
                row["new_purchase_for_one_axis"] = 0
                row["one_axis_quantity"] = 0
                row["three_axis_reference_quantity"] = 0
                row["additional_for_three_axes"] = 0
                row["included_and_duplicates"] = f"元CADの名目は{len(items)}本、実物調達数は0。 " + notes
            if family == "BEARING_ASSEMBLY":
                row.update(current_spec="6800寸法系10×19×5mm、玉10個/2.381mm。NSK6800ZZ(CN/ZZ)は候補。",
                           purchase_unit="完成品1個（内部部品込み）", display_price_jpy=1330,
                           price_basis="NSK公式の税別標準/個。国内EA966ED-800は別流通候補で税別標準820、NSK製と未確認。",
                           readiness="現行C08寸法の候補。最終仕様/はめあい確認後に購入")
            if family == "STATOR_BOLT":
                row.update(purchase_unit="SNS-M3-12-EL:20本/袋（4本使用、3軸現行12本も1袋）",
                           display_price_jpy=594, price_basis="税込/20本袋。バラ別手数料、送料別",
                           shipping_stock="2026-11-15公式表に在庫品表示。確保/納期保証なし",
                           readiness="現行規格の市販候補。M3改訂と表面摩擦/座面照合後")
        b = items[0]["bbox_mm"]
        row["nominal_bbox_mm"] = "×".join(f"{b[i+3]-b[i]:.3f}" for i in range(3)) + "（代表IDの外接箱。素材厚/加工公差ではない）"
        rows.append(row)
    for identifier, name, category, quantity, unit, rule, source_ids, spec, notes in EXTRAS:
        row = make_row(identifier, name, "CAD外の実物・材料・補助品", category, quantity, unit, rule, source_ids, spec, notes)
        row["request_information"] = "役割/数量/相手寸法/温度/絶縁/固定条件を明示し、元C08との適合を確認"
        if category == "手持ち":
            row.update(owned_quantity=1, new_purchase_for_one_axis=0, purchase_unit="所有済み", readiness="買い直し不要・使用適合は別確認")
        elif category == "PLA印刷候補":
            row.update(purchase_unit="適合STLは未作成", readiness="印刷補助品の候補・設計待ち")
        elif identifier in {"TOOL-CALIPER", "TOOL-FEELER"}:
            row.update(purchase_unit="1本・ケース付" if identifier == "TOOL-CALIPER" else "9枚1組・ケース付",
                       display_price_jpy=7876 if identifier == "TOOL-CALIPER" else 1067,
                       price_basis="公式直販の税込/購入単位", readiness="所有/借用を確認して準備",
                       shipping_stock="2026-11-15残数表示あり。未確保・送料未確認")
        elif identifier.startswith("TOOL-"):
            row["readiness"] = "最終公差/頭部/トルク範囲を確認して準備・借用可"
        rows.append(row)
    added_sources, added_rows = electrical_rows(electrical)
    for key, source in added_sources.items():
        if key in sources:
            raise ValueError("Duplicate source: " + key)
        sources[key] = source
    rows.extend(added_rows)
    seen = Counter(part for row in rows for part in row["c08_ids"])
    expected = {p["id"] for p in assembly["parts"]}
    if expected != set(ALLOWED) | set(REFERENCES):
        raise ValueError("Procurement input must match the existing public C08 allowlist")
    if set(seen) != expected or any(n != 1 for n in seen.values()):
        raise ValueError("C08 coverage must contain each of149 IDs exactly once")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate procurement row ID")
    for row in rows:
        if row["physical_qualified"] is not False:
            raise ValueError("An inventory cannot qualify physical hardware")
        if set(row["sources"]) - set(sources):
            raise ValueError("Unknown supplier evidence: " + row["id"])
    return {
        "schema": "c08-one-axis-procurement-v1", "checked_on": CHECKED,
        "scope": "Current public C08 single-axis mechanism toward static attraction/release, then gated low-speed testing; not a completed three-axis machine BOM.",
        "physical_ready": False, "M3_conversion_complete": False, "whole_system_cost_complete": False,
        "source_files": [{"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in SOURCE_FILES],
        "source_part_count": 149, "bearing_shape_count": 12, "bearing_purchase_count_per_axis": 1,
        "reference_part_ids": [p["id"] for p in assembly["parts"] if p["is_reference"]],
        "current_C08_fastener_shape_count": sum(p["is_fastener"] for p in assembly["parts"]),
        "known_C08_limits": assembly["known_limits"],
        "sources": sources, "items": rows,
        "coverage": {pid: next(r["id"] for r in rows if pid in r["c08_ids"]) for pid in sorted(expected)},
        "source_geometry_metadata": [{"id": p["id"], "bbox_mm": p["bbox_mm"], "material": p["material"], "joint_id": p.get("joint_id")}
                                     for p in assembly["parts"]],
    }


FIELDS = {
    "id": "調達ID", "name": "部品名", "role": "用途", "c08_ids": "対応C08_ID", "cad_shape_count": "CAD形状数",
    "category": "調達区分", "current_spec": "現行C08または候補の仕様", "nominal_bbox_mm": "名目外接寸法mm",
    "one_axis_quantity": "現行1軸必要数", "unit": "単位", "three_axis_reference_quantity": "3軸参考数",
    "additional_for_three_axes": "1軸から3軸への参考増分", "quantity_basis": "数量の根拠",
    "after_M3_redesign_quantity": "M3改訂後数量", "purchase_unit": "購入単位", "owned_quantity": "手持ち数",
    "new_purchase_for_one_axis": "1軸新規購入数", "included_and_duplicates": "付属品と重複防止",
    "supplier_names": "候補メーカー販売店", "urls": "具体的URL", "evidence_kinds": "情報源区分",
    "checked_dates": "確認日", "display_price_jpy": "確認価格JPY", "price_basis": "価格単位と税区分",
    "shipping_stock": "送料在庫納期", "readiness": "現時点の手配区分", "hold_reason": "保留理由",
    "request_information": "加工巻線相談に渡す情報",
}


def csv_text(result):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS.values(), lineterminator="\n")
    writer.writeheader()
    for row in result["items"]:
        evidence = [result["sources"][key] for key in row["sources"]]
        expanded = {**row, "supplier_names": ";".join(p["name"] for p in evidence),
                    "urls": ";".join(p["url"] for p in evidence),
                    "evidence_kinds": ";".join(p["kind"] for p in evidence),
                    "checked_dates": ";".join(sorted({p["checked_on"] for p in evidence}))}
        writer.writerow({title: ";".join(expanded[key]) if isinstance(expanded.get(key), list) else expanded.get(key)
                         for key, title in FIELDS.items()})
    return stream.getvalue()


def check_saved(result):
    if json.loads((ROOT / "data/c08-procurement-coverage.json").read_text()) != result:
        raise ValueError("Saved procurement mapping is stale")
    if (ROOT / "data/c08-procurement.csv").read_text() != csv_text(result):
        raise ValueError("Saved procurement CSV is stale")
    checked = (*SOURCE_FILES, "scripts/build_c08_procurement.py", "docs/C08_PROCUREMENT.md",
               "data/c08-procurement.csv", "data/c08-procurement-coverage.json", "tests/test_c08_procurement.py")
    return {
        "schema": "c08-procurement-validation-v1", "status": "PASS",
        "scope": "Reproducible inventory and exact public-ID coverage, not a manufacturing, electrical or physical test.",
        "row_count": len(result["items"]), "covered_source_ids": len(result["coverage"]),
        "c08_group_count": sum(bool(r["c08_ids"]) for r in result["items"]),
        "bearing": {"source_shapes": 12, "one_axis_purchase_quantity": 1},
        "duplicate_ids": [], "missing_ids": [], "whole_system_cost_complete": False,
        "physical_ready": False, "M3_conversion_complete": False,
        "inputs": [{"path": name, "sha256": hashlib.sha256((ROOT / name).read_bytes()).hexdigest()} for name in checked],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check saved outputs and write a data-only validation receipt")
    args = parser.parse_args()
    path = ROOT / "data/c08-procurement-electrical.json"
    if not path.is_file():
        raise FileNotFoundError("Electrical/measurement inventory input is required, even when choices remain gated")
    result = build(json.loads(path.read_text()))
    if args.check:
        receipt = check_saved(result)
        (ROOT / "validation/c08-procurement.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    else:
        (ROOT / "data/c08-procurement.csv").write_text(csv_text(result), encoding="utf-8")
        (ROOT / "data/c08-procurement-coverage.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": len(result["items"]), "covered_C08_ids": len(result["coverage"]),
                      "bearing_shapes_to_one_purchase": result["bearing_shape_count"],
                      "source_count": len(result["sources"]), "physical_ready": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
