# 公開パッケージの検査範囲

検査するのは、**公開してよい部品だけが入っていること、CAD・mesh・表・画面が同じ構成を示すこと**です。
製作、現物適合、電磁力、摩擦、熱、疲労、バランス、起立性能の合格ではありません。

## 形状と単位

単軸149部品、参考三軸447部品をそれぞれ独立した新Documentで保存します。
nativeを再読込みし、独立`Part::Feature`、valid solid、部品名、体積、bbox、参照フラグ、外部リンク不在を照合します。
STEPも再読込みし、同じ部品名・solid数・mmのbboxを確認します。
位置・姿勢の期待値は、保存後のオブジェクトから作りません。Documentへ入れる**前**のZ軸Shapeの
world bbox・体積重心を基準とし、別に書いた座標規約 `X=(z,-y,x)` / `Y=(x,z,-y)` / `Z=(x,y,z)` で
三軸の期待値を導出します。nativeのworld bbox・重心は0.000001 mm以内で照合します。
通常の`BoundBox`は三角化キャッシュで値が変わり得るため、
`optimalBoundingBox(useTriangulation=False, useShapeTolerance=False)`の幾何学的なbboxを使います。
1部品の姿勢を意図的に3度変える負例が拒否されることも確認し、保存nativeを変更せず閉じます。

STEPへの変換では、OCCの体積積分表現に小さな差が生じる場合があります。
許容値は相対体積0.01%、bbox 0.001 mmです。
体積差が通常の丸めより大きい部品にはnative−STEPとSTEP−nativeのBoolean差分も要求し、
合計0.00001 mm³を超えれば拒否します。体積だけ近い別形状で合格させません。
これはデータ変換の検査許容値であって、製造公差の指定ではありません。

表示メッシュはnativeと同じ評価済みShapeからmmで三角化します。
各部品の体積差2%、bbox差0.12 mm、体積重心差0.02 mm以内を上限とし、実測最大値を記録します。
画面読込み時もSHA-256、部品集合、頂点・index、mmのbboxと体積重心を照合し、不一致は表示を止めます。
公開nativeから再生成したmeshは、既存の公開meshから保存したbbox・重心に0.002 mm以内で一致することも要求します。
再出力時に新しい期待値で既存の姿勢情報を上書きして合格させません。
検査値とファイルhashは [`validation/cad.json`](../validation/cad.json) です。

初回抽出後に [`scripts/reexport_public.py`](../scripts/reexport_public.py) で、
公開された単軸nativeと公開コードだけからSTEP・meshを再生成します。
非配布のprivate入力がなくても開けることと、再出力できることは別々に確認します。
また、ZIPを新しいディレクトリーへ展開して、その中のnativeとコードだけで同じ再出力を行います。
この独立した配布物の検査記録は [`validation/reexport.json`](../validation/reexport.json) です。
検査が未完了・失敗の間は、ローカルプレビューのCAD/STEP/ZIPをHTTP 503で停止し、画面にも停止理由を表示します。

## 公開境界・メタデータ

[`scripts/public_files.py`](../scripts/public_files.py) が公開候補ファイルの明示allowlistです。
ZIPはそのうちCAD・表・必要な説明と再出力コードだけを収録し、内部hash一覧を持ちます。
PNGの` tEXt / zTXt / iTXt `はCRCと必要な展開を検査したうえで、不要な文字メタデータを拒否します。
PNGを使っていない配布でも、この検査の負例を保持します。

ZIP・FCStdを再帰的に展開検査し、個人ローカルpath、session識別子、秘密鍵や認証token、
危険なarchive member、元shapeのnative、外部リンク、未承認ファイルを拒否します。
原入力のhashは読取り前後で照合し、原本へ保存しません。
禁止した元wheel・frame・corner名や、保護された全nativeをわざと渡す負例は拒否しなければなりません。
結果は [`validation/public.json`](../validation/public.json) です。

## 実ブラウザー

ブラウザーは隔離された新profileで起動し、個人のログイン済みprofileには接続しません。
desktop/mobile、単軸/参考三軸、部品とねじの選択、相手ID、分解、半断面、リセット、キーボード、
reduced-motion、console/network、native/STEP/ZIPの実ダウンロードとSHA-256、
モデル欠損時の明示エラーを検査します。
結果は [`validation/browser.json`](../validation/browser.json) です。
スクリーンショットは作業セッションの確認用成果であり、原privateレンダーを再利用しません。

画面の3Dは配置を説明するもので、分解移動や断面から実組立経路、工具適合、磁場や構造成立を認定しません。
未資格フラグと、電流・面圧感度・磁気条件の既知の未達を表示したままにします。
