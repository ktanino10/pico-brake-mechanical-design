# 履歴: 卓上R1試作資料の根拠と確度

**用途訂正: 旧R1の部品選定は3軸姿勢制御用C08の採用案ではありません。**
調査事実は残しますが、卓上案の判断を本来の用途へ転用しません。
本来の形状はS07と[公開範囲](PUBLIC_SCOPE.md)、XYZ配置は[筐体資料](ENCLOSURE.md)です。
[用途訂正の入口](../PROTOTYPE.md)。

基準日: 2026-11-14。[ガイド](PROTOTYPE.md) / [材料表](../data/prototype-bom.csv) / [記録シート](PROTOTYPE_WORKSHEET.md)。
**R1では機械寸法・数量・信号設計を選定済み。S21〜S27が改訂根拠です。S10のTLP案は不採用です。**
事前に確認された資料と今回の追加カタログ確認を区別します。個人写真・EXIF・シリアル情報・第三者図面本体は収録しません。
リンク先は根拠資料であり、そこにある実装例をそのまま実行する指示ではありません。

## 確度の読み方

| 根拠区分 | 確認できること | 確認できないこと |
|---|---|---|
| 観察 | 所有品の外観・ラベル・色順 | 寸法公差・電気的役割・定格 |
| ユーザー申告実測 | ユーザーが測って申告した寸法とその定義 | 未記録の測定器・公差・測定方法・加工公差の保証 |
| 公式 | メーカー図面・仕様・取扱資料の記載 | 手元の個体や組合せの適合 |
| 販売 | 販売店の価格・商品説明 | メーカー保証や実測性能 |
| 第三者 | 同型とされる個人作例・コード | 手元のピン番号・電圧・安全性 |
| 計算 | 記載された仮定からの算術 | 未測定の摩擦・慣性・熱・実力 |
| 要件 | 今回の構成に必要な種類や条件 | 型番・寸法・数量・購入承認 |
| 設計選定 | 設計者が選んだ寸法・型番・受入れ目標 | 実機試験結果・メーカー保証・製品安全資格 |
| 未確認 | 確認できていない項目 | 「問題なし」「0」「不要」とする根拠にはならない |

根拠は優先度の目安で、公式資料があるだけで実機承認にはなりません。
通電・回転試験結果は現時点でありません。軸寸法の申告値はS19に別記します。
価格の事前調査も基準日付きの記録で、在庫予約ではありません。

## S01: 所有モーター・ケーブルの観察

所有品写真から24H055M020、Dカット軸、12極ケーブルを確認。ケーブルの新規購入数量は0です。
線が左、コネクタが右、黄色が上の観察方向で、
黄・青・白・緑・橙・茶・灰・紫・黒・黒・赤・赤です。
これはメーカーのピン番号や、嵌合面から見た配置の確定ではありません。
写真だけで軸径・突き出し長・取付PCD・ねじ深さ・入力定格は決まりません。追加のコネクタ写真は前提にしていません。
その後に得た軸4寸法のユーザー申告実測値はS19を参照してください。

## S02: 所有品の販売ページ

[Yahoo!ショッピングの販売説明](https://store.shopping.yahoo.co.jp/homarina/av053104211.html)。
事前調査でDC12V・3900RPM・ドライバ内蔵・100ラインエンコーダと記載。
いずれも販売記載で、実測値や許容上限ではありません。エンコーダ信号を外から利用できるかは未確認です。
内蔵ドライバのあるBLDCとして検討し、外付けESC/Hブリッジを購入リストに追加しません。

## S03: 型式を区別する記事

[24Hモーター記事](https://suzu-mono-gram.com/blog/nidec-24h-motor-guide/)。
事前調査でD軸24H055M020は12V・ZH12P・PFM周波数制御、1000Hzで約150rpmとの作例情報。
ZH型式と換算は第三者情報で、現物適合・保証式ではありません。
8ピン24H404H070/160の記事にある7–24V・負論理duty PWM・配線・電流測定を本品へ転用しません。

## S04: 同型第三者作例と色順照合

[Instructables作例](https://www.instructables.com/Fixing-the-Nidec-24H055M020-Gritters-Achieving-Pre/) /
[公開ラベル図](https://content.instructables.com/FKV/LSMA/MNGJQPQK/FKVLSMAMNGJQPQK.png)。
事前にラベル図を目視し、色順が所有ケーブルの観察と一致しました。画像を再配布せずリンクで参照します。

**次表は第三者の参照番号であり、承認済みピン配置・接続表ではありません。**
番号の見方、GND間の関係、入力電流、許容電圧は別途確認します。色だけで接続しません。

| 作例参照番号 | 観察色 | 作例での役割仮説 | 未確定事項 |
|---|---|---|---|
| 1 | 黄 | PFM | HIGH/LOW閾値、振幅、周波数範囲、無信号時の状態 |
| 2 | 青 | Enable、12Vの記述 | 許容電圧・入力電流・OFF状態。Pico直結不可 |
| 3 | 白 | 内蔵ブレーキ、GNDで作動の記述 | 解放電圧・無接続時・電源断時の状態 |
| 4 | 緑 | 方向 | 極性が作例間で一貫しない。試験中の切替を計画しない |
| 5 | 橙 | 不明/未使用 | 個別絶縁して未接続 |
| 6 | 茶 | 不明/未使用 | 個別絶縁して未接続 |
| 7 | 灰 | 不明/未使用 | 個別絶縁して未接続 |
| 8 | 紫 | 信号GNDとの記述 | 実機関係未確認。初期は5–8を個別絶縁して未接続 |
| 9–10 | 黒・黒 | 電力GND | 各線の対応・導通・許容電流 |
| 11–12 | 赤・赤 | +12V | 各線の対応・極性・電力定格 |

表中の12Vは作例の記述であり、すべての「VCC」が12Vという意味ではありません。
5–8をまとめて短絡したり、紫を未確認のまま共通GNDへつないだりしません。
PFMは周波数指令の仮説で、通常のduty制御を当てはめません。

## S05: PFM作例コード

[固定コミットのspeedoCalibrationSketch.ino](https://github.com/alanesq/misc/blob/d27f3fdaa761b8eb66c4682bcabc17a5a8957b9d/speedoCalibrationSketch.ino)。
PFM/役割の仮説を補強する第三者例です。Unoの5V例であり、3.3V不足のコメントは未試験の伝聞です。
高周波での起動は本試作の回転体に転用せず、コード全文のコピー・実行・ドライバ生成は行いません。
メーカー回路図の代用ではありません。

## S06: 手回し教材の元データ

[GUIDE.txt](https://github.com/ktanino10/electromagnetic-brake-lab/blob/2a7c3ea7845e48343f7ad3036d1cb09c5f737dd7/model-v2/GUIDE.txt) /
[生成スクリプト](https://github.com/ktanino10/electromagnetic-brake-lab/blob/2a7c3ea7845e48343f7ad3036d1cb09c5f737dd7/model-v2/scripts/build_v2_cad.py) /
[組立manifest](https://github.com/ktanino10/electromagnetic-brake-lab/blob/2a7c3ea7845e48343f7ad3036d1cb09c5f737dd7/model-v2/results/assembly-manifest.json)。

事前に確認した非磁性・手操作専用モデルです。名目: 台座外径120mm、
リング外径100/内径60/厚さ5.5mm、ハブ穴8.7mmと固定樹脂軸8mm、
樹脂板ばね3本（幅7/厚さ0.8/自由長約24.03mm）、手動隙間1.5mm。
M3×6を6本・M3×25を1本、ナット/座金を各7個という元モデルの数量は、
**新しい動力試作の買い物数量ではありません**。元CAD・印刷部品を加工する指示は含みません。

## S07: このリポジトリのC08

[基準コミット0b37ee1](https://github.com/ktanino10/pico-brake-mechanical-design/tree/0b37ee1774cca51cbbf63cf4cd5bb149d152c7ee) /
[公開範囲](PUBLIC_SCOPE.md)。
未資格の金属設計と参考形状です。M2/M2.5/M4やカスタム部品を含み、M3の小型試作へ直結しません。
既存149部品や締付・磁気・トルク計算を本案の性能に転記しません。

## S08: Pico H

[秋月118085](https://akizukidenshi.com/catalog/g/g118085/) /
[Raspberry Pi公式データシート](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf)。
事前調査: SC0917、920円。ヘッダ実装品を候補とし、micro-Bデータケーブルを別に確認。
GPIOは3.3V系として扱い、モーター電源・5V/12V信号の直結はしません。

## S09: LVC8T245実装済み基板

[秋月115778](https://akizukidenshi.com/catalog/g/g115778/)。
事前調査: 250円、A/B電源1.65–5.5V、ヘッダ付属、確認時の在庫1。
12V不可。裸基板116214ではありません。3.3→5V PFMの候補で、電源順序・DIR/OE・未使用入力・逆流は要設計です。
「5Vなら必ず動く」「3.3Vは絶対に動かない」とは確定していません。

## S10: TLP291 4bit×2モジュール

**旧案の調査記録。R1ではADA-4409へ変更し、TLP291と専用端子足は購入しません。**
[秋月108029](https://akizukidenshi.com/catalog/g/g108029/) /
[基板回路・寸法](https://akizukidenshi.com/goodsaffix/AE-TLP291-4X2.pdf) /
[TLP291資料](https://akizukidenshi.com/goodsaffix/TLP291.pdf)。
150円、IC実装済み。今回も商品記載を照合。
4ch内のカソード/エミッタ共通、2ブロック間分離。LED抵抗、出力抵抗、端子足は別設計です。
掲載下降応答60µsのため26kHz PFM用にしません。CTRの条件と温度・経年余裕を確認し、50mAを保証駆動値にしません。

## S11: ソレノイド用MOSFET基板

[Switch Science8741](https://www.switch-science.com/products/8741) /
[Adafruit公式端子説明](https://learn.adafruit.com/adafruit-mosfet-driver/pinouts)。
ADA-5648、968円。今回も照合: 負荷3–30V、連続1.5A/ピーク3A、還流ダイオード内蔵。
PHコネクタは連続2Aの記載ですが、基板の連続1.5Aを上書きしません。
入力に3.3Vを使用する候補で、GNDは信号/電力共通。STEMMAのV+は負荷電源、出力はLOW側スイッチです。
モーター電源スイッチ用として選定していません。ダイオード付きでも回生電力の吸収や即時解放の保証はありません。

## S12: CA0830ソレノイド

[タカハ購入先](https://www.takaha-shop.com/SHOP/ca0830.html) /
[公式CA0830図面・巻線表](https://www.takaha.co.jp/product/ca/pdf/CA0830.pdf)。
事前一次資料調査: CA08300480=48Ω、DC12V連続。本体18×22×30.4mm、
プランジャーφ8、リンク穴φ3、筐体取付M3タップ。ねじ有効深さは実物側で未確認です。
系列価格1,320円、名目6mm・1.02Nは参考。力グラフの見出しは**DC24V/冷間20°C**です。
12V48Ωの全行程・温間吸引力の確定には使わず、巻線条件の対応と実測が必要です。

## S13: DP100

[Switch Science9414](https://www.switch-science.com/products/9414) /
[メーカー資料](https://en.alientek.com/Product_Details/45.html)。
8,800円。今回も商品記載を照合: PD/QCまたはDC5–32V入力、CC/CV、
4mmバナナ出力0–30V/0–5A・最大100W。ただし入力電圧・電力以下です。
USB-Aの5V出力には入力条件があり、未検討のままPicoや信号系へ分配しません。
特殊DC→Cケーブルは他機器故障のおそれがあるため今回不使用。
過電圧・逆接等の掲載保護機能だけで、回転負荷からの逆流・回生を処理できるとは判定しません。

## S14: アース端子を要求しないAC入力候補

[サンワACA-PD91BK販売](https://direct.sanwa.co.jp/ItemPage/ACA-PD91BK) /
[公式仕様](https://www.sanwa.co.jp/product/syohin?code=ACA-PD91BK) /
[公式説明書](https://cdn.sanwa.co.jp/support/setsumeisyo/pdf/A/ACA-PD91BK_ver1-0.pdf) /
[公式背面ラベル](https://cdn.sanwa.co.jp/product/syohin_img/A/ACA-PD91BK_BKX.jpg)。
事前調査: 6,028円、65W単ポート、PD20V3.25A、メーカーPSE適合記載。
ラベル画像の二重四角を確認してClass II候補としています。単に2Pから推測していません。
2m・5A/100WのC-Cケーブル付属のため追加購入不要。
DP100とのPD交渉・実負荷動作は未試験です。PE必須のDPS-3003は除外します。

## S15: PH3極ケーブルの追加確認

[Switch Science9800](https://www.switch-science.com/products/9800)。
今回確認: ADA-4336、187円、100mm、両端JST PH3極2mm、22AWG。
片端が端子台用リードになった完成配線ではありません。加工後の長さ・線順・引張保持を設計し、
色をモーターの色表と混同しません。電力をブレッドボードへ逃がす変換ケーブルにしません。

## S16: 光学センサの選定境界

[Pololu QTR-1A公式](https://www.pololu.com/product/2458)を今回確認。
公式記載は5V動作、アナログ出力0–VIN、最適距離3mm/推奨最大6mm、別はんだの2.54mmヘッダ付属。
3.3V動作保証は今回のページから確認できず、**本案の確定候補にはしていません**。
QTR-1RCとは出力方式が異なります。小穴もM3適合とはしません。
国内向けRobotShopの商品ページは403で直接確認できず、検索表示の価格をBOMに採用していません。
R1ではS27のMaker Reflectを3.3Vで使用する構成に決めました。QTR-1Aは採用しません。

## S17: 標準材・工具の探し先

[ミスミ](https://jp.misumi-ec.com/) / [モノタロウ](https://www.monotaro.com/) /
[秋月](https://akizukidenshi.com/)。
M3締結・金属板・軸受・配線・測定器などの調達先の例です。
個別品番・加工公差・材料証明・価格・在庫は未確認。材質が似ているだけの摩擦材を確定品にしません。

## S18: 未読の情報

[Redditの12極24Hスレッド](https://www.reddit.com/r/Motors/comments/1ixdyp4/how_to_use_this_12_pin_variant_nidec_24h/)は
事前調査でJavaScriptアクセス確認により取得できませんでした。内容を読んだとは扱わず、配線根拠に採用せず、再試行していません。

## S19: ユーザー申告の軸寸法

2026-11-14の申告原文: 「A:6mm,B:15mm,C:4mm,D:5mm」。
提示済みの寸法ガイドに対応する定義で記録します。写真からの推定でもメーカー公差でもありません。

| 記号 | 定義 | 申告実測値 |
|---|---|---:|
| A | 軸の円径 | 6mm |
| B | 有効な軸突き出し長 | 15mm |
| C | Dカット面から反対側の曲面までの距離（平面幅ではない） | 4mm |
| D | Dカット部の軸方向長さ | 5mm |

測定器・測定公差・正確な測定位置/方法・D部の軸方向開始位置は未記録です。
4値の取得と継手適合承認は別です。R1ではφ6継手を片側8.5mm挿入する構成に決め、
ハブは別の独立丸軸へ移しました。実公差・D部位置とクランプ面の関係は確認します。
取付穴のピッチ/ねじ/深さ、モーター電気入力・軸受荷重をこの測定から推定しません。

## S20: 6mm軸・M3端面穴の止めねじ式ハブ代替候補

[Pololu 1999公式](https://www.pololu.com/product/1999) /
[公式寸法図](https://www.pololu.com/file/0J667/1999-6mm-m3-hub-dimensions.pdf) /
[公式仕様統合ページ](https://www.pololu.com/product-info-merged/1999) /
[DigiKey日本語購入窓口](https://www.digikey.jp/ja/products/detail/pololu/1999/10449888)。

一次資料の追加確認結果: 丸軸/D軸6mm用、端面6×M3、1個にM3止めねじ2本を使う構造。
分割クランプハブではありません。Pololu1083の#4-40仕様とも別です。
1パックにハブ2個・止めねじ4本・1.5mm六角キー。
公式図の全長5+4.2=9.2mm、外径25.4mm、ボス外径12mm、穴径6mm、穴配置半径9.5mm（PCD19）。
公式の6.8g/個は止めねじなしの公称質量で、試作回転体の実測慣性ではありません。

DigiKey日本語窓口はPololuが出荷するマーケットプレイス品で、国内在庫確認ではありません。
2026-11-14の表示2,033円（税別）から税込参考計算2,236.3円/パック、送料・税端数/最終額は別途確認。
RobotShop日本語検索表示は在庫なしで、即納品として扱いません。
R1ではCSV M21で1パックを購入し、M03に1個を割り当てる独立軸ハブとして採用。
二重購入せず、機械追加分の価格へ移しました。所有モーターB=15mmとの比較では採用判定しません。
止めねじ保持・実はめあい・端面ねじの受入れを実施し、実機回転は未承認のままです。

## S21: 6mm継手の一次資料

[NBK MSTS-25C-6-6](https://www.nbk1560.com/products/coupling/couplicon/slit_type/MSTS-C/MSTS-25C/MSTS-25C-6-6/) /
[メーカー取付方法](https://www.nbk1560.com/resources/coupling/article/couplicon-maintenance/)。
今回確認: 外径25、全長31、ハブ挿入長L8.5、M3クランプ、指定締付1.5N·m、税込10,076円、国内直販在庫品表示。
許容偏心0.15mm・偏角2°・エンドプレイ±0.4mmは継手単体の記載。
スリップ0.7N·mはh7軸などの条件付き試験値で保証値ではない。慣性7.1×10⁻⁶kg·m²/質量78gは最大穴径時。
軸挿入Lを推奨、D面はスリット/座ぐりから避け、複合ずれは各許容の1/2、運用は1/3以下を推奨する記載です。
R1の0.03mm・0.3°は別の設計目標で、継手反力ゼロやモーター軸受適合を保証しません。

## S22: 626ZZ

[NSK626ZZ / AXEL](https://axel.as-1.co.jp/asone/d/62-4984-03/)を直接確認。
内径6、外径19、幅6、参考質量8.15g、税別標準400円。実売/在庫は別確認。
税込440円は標準価格に10%を加えた参考計算です。R1では2個を64mm間隔に配置。
メーカーCADはコピーせず、単純なリングで外形と接触面を表現しています。

## S23: 実験用ゴムパッド

[光KGR-1100 / AXEL](https://axel.as-1.co.jp/asone/d/61-2050-33/)を直接確認。
100×100×1mm、天然ゴムNR、国内製造、パッキン/滑り止め/防振用途、使用温度-30〜70°Cの販売記載。
税別標準90円から税込参考99円を計算。モノタロウの直接取得は403のためその価格を採用していません。
**摩擦係数やブレーキ定格の資料ではありません。** μ=0.2、面荷重1.5N、全系0.1Jは今回の設計/試験仮定です。
実摩擦・接着・局所温度・摩耗を確認し、不足時にこの材料を保証品と扱いません。

## S24: 戻しばね

[サミニの製品検索](https://www.samini.co.jp/products/search_product/search.php)で圧縮ばねを絞り込み、
12-0423のSUS304WPB、線径0.3、外径4、自由長20、k=0.13N/mm、全たわみ15.9mm・最大荷重1.96Nを確認しました。
[国内注文窓口](https://jp.misumi-ec.com/vona2/detail/221000765160/?HissuCode=12-0423)の検索表示でも一致。
メーカーの読取り専用検索はPOST式で、URLだけでは絞り込みを再現しません。品番で照合します。
販売検索の価格は最終実売としてBOMへ採用せず未見積。R1の初期圧縮3.5mmは全たわみの約22%です。

## S25: 独立軸カラー

IWATA SC0605Sの販売記載で内径6、外径12、幅5、SUS304、M3×3止めねじを確認。
[販売参照](https://www.amazon.co.jp/dp/B07N2ST6C5)。
メーカー個別ページの本文は取得できなかったため「公式寸法保証/国内在庫確認」とは表示せず、
受入れ照合が必要な標準品の選定として記録します。価格は未見積です。

## S26: R1の独自設計と計算

[生成コード](../scripts/build_prototype_mechanics.py) /
[機械仕様](PROTOTYPE_MECHANICAL.md) /
[寸法と幾何検査](../prototype/mechanical/manifest.json)。
CADは新規に作った寸法/プリミティブから生成し、元CADやメーカーSTEPをコピーしていません。
選んだ名目寸法と図面公差、仮定密度/摩擦/比熱、申告実測、公式カタログ値を区別しています。
保存前の形状のbbox/重心からSTEP再読込みを照合し、STLの閉鎖性/体積、取付とレバー可動域を検査。
新資料の75本のM3と、この82形状の数は別です。82は購入部品数ではありません。
CA0830の3W曲線の目視参考値は1mmで約3N、2mmで約2N。12V48Ωの実力保証にはせず、
ストローク1.5〜0.3mm・最低1.5Nを**受入れ目標**として選びました。

## S27: 信号・保護の採用設計

[採用回路](PROTOTYPE_SIGNAL.md)に、調査済みの次の一次資料を反映しました。

- [秋月LVC回路](https://akizukidenshi.com/goodsaffix/AE-LLCNV-LVC8T245_sch_20210113.pdf): DIR/OE出荷時10kプルアップ。
- [TI LVC8T245](https://www.ti.com/lit/ds/symlink/sn74lvc8t245.pdf): 電源/入力/Ioffの適用条件。
- [ADA-4409](https://learn.adafruit.com/adafruit-stemma-non-latching-mini-relay/pinouts): 非ラッチSPDT、[国内販売1,485円](https://www.switch-science.com/products/6007)。
- [Maker Reflect図面](https://akizukidenshi.com/goodsaffix/MAKER-REFLECT%20Datasheet.pdf): 18.1×8.4×4.2、ヘッダ5.6、穴φ3。3.3Vアナログで使用。[国内販売420円](https://akizukidenshi.com/catalog/g/g130181/)。
- [Adafruit4739](https://www.adafruit.com/product/4739): MPM3610固定5V、入力6〜21V、実装済み。[マルツ海外調達窓口](https://www.marutsu.co.jp/pc/i/35985826/)。
- [NKK資料](https://www.nkkswitches.com/pdf/MN_ToggleSections_DP.pdf): MN11SS1W01、SPST、DC30V4A、専用取付ねじ1/4-40。
- エーモン[3662主2A](https://www.amon.jp/products2/detail.php?product_code=3662)、[3661分岐1A](https://www.amon.jp/products2/detail.php?product_code=3661)、[3371ホルダ](https://www.amon.jp/products2/detail.php?product_code=3371): φ5.2×20。ホルダ12V30W/0.2sq記載。
- [WAGO221-415](https://www.wago.com/221-415): 5端子は1電位。5個を別の電位/接続点へ使用。

GPIO、抵抗値、CC0.30/0.50/1.00A、50ms待機は設計で選んだ値です。
モーターの5V PFM/12V系Enable/方向GND/白線開放の実適合をこれらのメーカー資料で証明したことにはしません。
