# 138 mmの独立名目筐体

主入口: <https://ktanino10.github.io/pico-brake-mechanical-design/enclosure.html>

参照したPico版のframe＋corner外形は138 mm、frame spanは136 mmです。これは現在の用途に基づく暫定基準であり、ユーザーがESP32/Picoの版を選んだ記録ではありません。元全assemblyの突起込み外形は144 mm（−75..+69）で、筐体外形とは区別します。以前の176 mm参考配置図は寸法根拠ではありません。

**実機用の検討案で、製作・通電・回転の指示ではありません。** 部品の名目CADが揃うこと、元motorに適合すること、全機・実機が成立することは別の状態です。

## 部品の範囲

| 対象 | CAD要素数 | 内容 |
|---|---:|---|
| 独立した筐体 | 54 | 6フレーム、8内部corner、8外側cover、24端部ねじ、8coverねじ |
| PCB・MPU保持 | 28 | 2保持部、2参照基板、6フレーム固定ねじ、6絶縁スペーサー、6座金、6基板ねじ |
| 変更していない公開C08形状 | 435 | 145形状をXYZへ配置。元Pico由来の原形状ではない |
| 独立参考円盤 | 3 | 原wheelのスポーク・リム・慣性は再現しない |
| 要求motor interfaceの参考 | 6 | 各軸1受け＋1入力軸。3外部assemblyの参考で、6台のmotorではない |
| 合計 | **526** | 11参照形状を含む。200本の名目ねじに相手と締結条件を定義 |

全数はCADでモデル化した要素の数です。軸受の球や内外輪なども別要素なので、購入数量とは一致しません。元の83 leafは、31筐体・保持部、3wheel、12 motor形状（3外部assembly）、3hub、34ハードウェアに分け、[機能対応表](../data/enclosure-source-coverage.json)に全件を記録しています。

元の3＋12 motor supportの機能は、公開済みC08のCARRIERとPOSTを使った名目の保持経路へ対応付けています。元部品の形状・高さ・取付を再現した互換品ではなく、元motorの支持が成立したとの判定でもありません。

## 何で接合しているか

- 全24フレーム端は新しいM3名目皿ねじと内部cornerの受け穴へ接続。外側coverは実外面を持ち、対角方向の別ねじで保持します。位置決めpinの先端だけを138 mm外形の証拠にはしていません。
- motor側は新しいPCD126・4点の座面からPOST、CARRIER、ナットへ接続。元枠のPCD135とは半径で4.5 mm異なります。旧REF_FRAMEは統合モデルから除外しています。
- PCB・MPUは、フレーム→保持部の3点固定と、ねじ頭→座金→参照基板→絶縁スペーサー→保持部の順で名目接合します。未確認のinsertや浮いたナットを暗黙に追加していません。
- ねじは独自の円筒・円錐等による模式形状です。実ねじ山・駆動部の完全な規格形状ではありません。threadのmajor/minor表現による局所重なりと、面同士の意図した座面接触を分けます。

基板ねじの10 mmは**首下長さ**です。頭3 mmを含むモデル全長は13 mm。皿ねじの「頭を含む呼び長さ」とは区別しています。既定の基板1.6＋スペーサー3＋座金0.5＝grip5.1 mm、ねじのかかり4.9 mmです。基板厚を2.0 mmに変えた検査では、CAD実厚・台帳のgrip5.5／かかり4.5 mmへ追随します。

新しい6061-T6保持部やPEEK絶縁材等は名目材料の仮定であり、材証・強度・絶縁・クリープを資格化していません。締付値は未設定です。旧C08金属用の条件付き計算値を新筐体・printed部品・PCBへ転用しません。

## 測定値と仮定

PCBの49 × 78.73 mm外形範囲と4個のD3.4機械穴は、Picoフォルダーのprofile/drill資料から参照した機械条件です。回路・銅箔・部品配置・基板設計データは含みません。上側の片穴の0.186 mm差も保持しています。厚さ1.6 mm、スペーサー3 mm、実装部品高さや端子の余白は測定確定値ではありません。

MPUは元保持部の基準面・2穴の中心を参照しました。20.2 × 15.8 × 1.6 mmの板包絡とD3.4クリアランス穴は**新しい名目仮定**であり、実MPU基板を測定した値ではありません。

MPU参照板と初期の内部cornerには1.2544205601376728 mm³の干渉があったため、独立cornerの内側を対角面で逃がしています。外形138 mmと元保持部の基準面は変更せず、強度や実装部品のクリアランスは未資格のままです。保持部の斜めリブも基板座面で切りそろえ、スペーサーへ食い込ませていません。

電池の確定寸法とハーネスの経路・保持条件は、元83 leafだけでは得られていません。以前の仮電池を転用せず、実電池・ハーネスの保持は未解決として残しています。

## 元motorの干渉は解消していない

元STEPの `Part__Feature009` と `Z_HUB_RETAINING_RING` は、名目配置で **29.606056754452105 mm³** の正体積干渉です。

- `reference_motor_CAD_nominal_fit: failed`
- `actual_hardware_compatibility: unverified/blocked`

統合表示の受け形状は、新規作図した「要求interfaceの参考」です。元motorのpilotを含まない参考形状で干渉が消えても、元motorの適合解決とはしません。実motor選定・加工・C08形状変更は行っていません。

3軸最大約1.757 A > 1.5 A、面圧感度・高温側磁気条件の未達、材料/B-H・実摩擦・熱・疲労等の未資格も保持します。元全機の質量・fit・起立性能の結果をこの独立筐体へ転用しません。

## CADとHTML

`downloads/enclosure-nominal.FCStd` は新しいDocumentの独立Part::Feature群です。外部入力へのリンクはなく、公開ファイルだけで開けます。形状と位置を編集できるスナップショットで、完全なparametric設計履歴ではありません。STEPも同じ526要素とIDです。

HTMLは同じCAD形状から生成したmeshをworld XYZ・mmで表示します。操作開始時は組付け位置で、自動回転・音声はありません。分解スライダーは配置説明であり、実組立順・全挿入経路・工具アクセスを保証しません。断面は描画だけを切ります。

外側capは3つの閉じた直交穴でなく、対角方向に開いた導入slotを使います。既存の局所着脱経路の確認を保持し、追加部品がその進入側の対角平面より内側にあることを別途確認しています。全機の実組立経路や接触安全性の資格化ではありません。

検査はfresh native/STEPのID・数量・solid・体積・bbox・重心、同じmeshの整合、全200ねじの実長・局所thread上限/下限・座面、外側の実部材、欠落相手・誤姿勢・禁止入力・過大受け穴の負例を含みます。[CAD receipt](../validation/enclosure-cad.json)は成功した**名目モデルの静的検査**であり、現物適合証明ではありません。

ローカルはrepository rootで `python3 scripts/serve_public.py` を実行し、<http://127.0.0.1:8767/pico-brake-mechanical-design/enclosure.html> を開きます。CDN、解析、外部fontを読み込みません。Three.js 0.186.1はローカルvendorとMIT noticeを保持しています。平面のCAD面を曲がって見せないflat shadingを使います。利用API: [OrbitControls](https://threejs.org/docs/pages/OrbitControls.html)、[Material clippingPlanes](https://threejs.org/docs/pages/Material.html#clippingPlanes)、[MeshStandardMaterial flatShading](https://threejs.org/docs/pages/MeshStandardMaterial.html#flatShading)。

## ZIPと再生成

新ZIPはCAD・表・検査・再生成コードに限定し、HTMLや全meshは同梱しません。READMEの公開URLから3Dを開いてください。旧ブレーキZIP・native・STEP・meshは変更していません。

ZIPには再生成入力として、変更していない**公開ブレーキ単軸native**とその台帳を含みます。元のprivate C08や有料Pico CADではありません。新規生成器は入力SHAを固定し、元PicoのSTL/STEP/3MFを読みません。

FreeCAD 1.1.3のPython環境で、展開したrootから新しい出力directoryを指定します。

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python -B \
  scripts/build_enclosure.py --output /tmp/enclosure-candidate
```

このmacOS例は既存FreeCADを使うものです。入力ファイルを原本から取り直したり、既存出力へ上書きする必要はありません。ソリッド検査・STEP読戻しには時間がかかります。再生成しても実物の採用・製作承認にはなりません。

## 公開境界

元資料の輪郭トレース・Boolean改変を独自作図とは呼びません。本候補は新規primitive部品と、既にレビューした公開C08 authored形状のみで構成します。原STL/STEP/3MF・原motor・原wheel・原frame・メーカーCAD・回路資料・private全nativeは配布しません。自作CAD全体に未確認の第三者包括ライセンスを付けず、[NOTICE](../NOTICE.md)の境界を継続します。

`whole_fit: false / build_ready: false / physical_ready: false`
