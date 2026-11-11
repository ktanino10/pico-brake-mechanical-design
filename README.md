# ブレーキ組立検査台 — C08 公開CAD

**実機用の検討案です。製作・通電・回転の指示ではありません。**
`whole_fit = build_ready = physical_ready = false`。

日本語の3D画面で、ねじのID・サイズ・役割・相手部材と、C08金属案の条件付き締付計算を確認できます。
新規ブレーキ部145点と、独立して作図した参考円盤・支持リング・モーター包絡・入力軸4点を収録します。
元Pico Assy全体、原wheel・frame・corner・motor、そのBoolean改変を再配布するものではありません。

## 画面を開く

[`index.html`](index.html) がビルド不要の静的入口です。GitHub Pagesではリポジトリのsubpathで動作します。
この成果物を用意した段階では、pushやPagesの公開設定は行っていません。

ローカルでリポジトリを取得した場合は、このフォルダーで次を実行します。

```sh
python3 scripts/serve_public.py --port 8767
```

`http://127.0.0.1:8767/pico-brake-mechanical-design/` を開きます。
このサーバーはloopback限定で、許可した公開ファイルだけを配信します。
`.git`、ローカル作業ファイル、ディレクトリー一覧、symlinkは配信しません。
`file://` でHTMLを直接開いた場合は、3Dデータの読み込み方法を示すエラーを表示します。

Three.jsはバージョンを固定し、MIT表示とともにローカル同梱しています。
CDN・解析送信・外部アップロード・フォント取得はありません。
モデルの読み込み失敗、版の混在、WebGLの失敗を空白画面のままにしません。

## 使い方

- **単軸／参考三軸**：参考三軸は公開Zモジュールの剛体複製です。元全機の適合検査ではありません。
- **部品・ねじの選択**：3Dをクリックするか、部品一覧を使用します。接合カードと同じ軸の相手部材が連動します。
- **分解表示**：位置関係を見るために部品を離します。作動ストロークや実組立経路のアニメーションではありません。
- **全体を表示**：現在の分解状態の全部品を画面へ収めます。分解値を変更した時も同じfitを行います。
  視点の方向を保ち、毎フレーム回転・ズームを上書きしません。
- **半断面**：世界X平面で表示を切ります。CADを削りません。切断面のキャップ表示はありません。
- **操作**：ドラッグ・ホイール／ピンチ。3Dへのフォーカス中は矢印キー、`+` / `-`、`Home`。
  部品・軸・分解・断面も通常のキーボード操作が可能です。自動回転・音声はなく、reduced-motionも扱います。

灰色は鋼・磁極、銅色は巻線、青は回転・可動側、緑は固定支持です。
独立参照形状は薄い面と破線で区別します。選択部は金色の線、相手は青緑の線で表示します。

## CAD・表をダウンロード

| 構成 | FreeCAD | STEP | 部品数 |
|---|---|---|---:|
| 単軸 | [brake-single.FCStd](downloads/brake-single.FCStd) | [brake-single.step](downloads/brake-single.step) | 149 |
| 参考三軸 | [brake-reference-three.FCStd](downloads/brake-reference-three.FCStd) | [brake-reference-three.step](downloads/brake-reference-three.step) | 447 |

[CAD・表セットZIP](downloads/public-brake-cad.zip) /
[部品表](data/parts.csv) / [ねじ接合表](data/joints.csv) /
[部品ごとの公開根拠](data/provenance.json) / [SHA-256一覧](data/checksums.json)

ZIPはCAD・表・公開範囲・CAD検査記録・公開nativeの再出力コードを選んでまとめたものです。
HTML画面とローカルvendorはリポジトリ側にあります。ZIPだけを取得した場合も、
FreeCAD nativeとSTEPをそのまま開けます。原private CADや有料部品は不要です。
`.git`、ログ、原資料、フォント原本、作業フォルダーはZIPに含めません。

nativeは新Document内の独立した`Part::Feature`です。形状・配置を編集でき、
原本への外部リンクはありません。**完全なパラメトリック設計履歴ではありません。**
寸法変更で全体が追従する、変更後も実物が適合するとはしていません。
部品ID、mm単位、組付け位置、軸変換はHTML・native・STEP・表で共通です。
三軸でもねじの接尾辞は同一で、`X_` / `Y_` / `Z_` が対象軸を区別します。

## 公開nativeだけから再出力

FreeCAD 1.1系のPythonから次を実行できます。既存のFreeCADのライブラリーが利用できる環境で実行します。
配布された単軸nativeとこのパッケージ内のコードだけを読み、非配布のC08入力を要求しません。

```sh
python scripts/reexport_public.py --output /tmp/brake-public-reexport
```

出力先は未作成のディレクトリーを指定します。既存ファイルは上書きしません。
macOSで同梱Pythonを使用する例：

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python -B \
  scripts/reexport_public.py --output /tmp/brake-public-reexport
```

STEPと表示メッシュを生成し、再読込みで部品数・体積・bboxを照合します。
編集後の形状を再出力できることは、権利・製作・強度・適合の再承認を意味しません。
初回抽出用の`build_cad.py --source`は管理者向けの別入口であり、通常の閲覧・再出力に不要です。

## 未達・未資格の範囲

金属案の条件付き設計計算であり、既存の印刷樹脂への締付値ではありません。
参考部材を含む接合に、元C08の締付計算や強度結果をそのまま適用しません。
PCD30のモーター3孔は名目の参照取付パターンです。実モーターの型番・軸・ねじ深さ・材・許容荷重は不明です。

- 796巻の宣言条件で3軸の最大電流和は約 **1.757 A > 1.5 A**。
- 内周へ偏った面圧の感度では必要力 **500.034 N > 500 N**。
  高温・低電圧時の必要電流約0.33035 Aに対し利用可能約0.32183 Aで、空隙分でも未達です。
- 実材料のB-H・最大吸引力・摩擦・応答・熱・疲労・バランスは未資格です。
  一様面圧の条件付き計算が範囲内でも、これらの合格の代用ではありません。
- 原全機の重い質量感度の起立試算も未達です。公開参考形状へ質量・慣性・起立性能の結果を転記しません。

[公開範囲](docs/PUBLIC_SCOPE.md) / [検査の方法と限界](docs/VALIDATION.md) /
[権利・ライセンス](NOTICE.md)

## 開発用の検査

表示にnpmやビルドは不要です。開発時だけ、このリポジトリの依存を使用します。

```sh
npm ci --ignore-scripts
npm test
python3 -B -m unittest discover -s tests -p 'test_*.py'
npm run test:browser
python3 -B scripts/package_public.py
```

ブラウザー検査には既存のChrome、またはPlaywrightのChromiumが必要です。
Chromeの明示パスは`CHROME_PATH`で指定できます。利用中の個人ブラウザーprofileには接続しません。
第三者依存の更新時のみ`npm run vendor`で、明示したローカルvendorを再生成します。
