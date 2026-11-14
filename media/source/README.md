# 40秒C08動画の再生成ソース

`c08-clear-animation.blend`は、公開C08を使用した40秒版のベイク済みデータです。
立体主モデルと明示的な拡大模式断面を別シーンにしています。モデルは今回再設計していません。
動画は1場面につき1ビューだけを表示し、同時に小さな窓を並べません。

## 必要なもの

既存FreeCAD Python、Blender 5.1系、FreeCAD同梱PySide6、FFmpeg。
日本語はシステムフォントを使い、第三者フォントやユーザー写真は配布しません。
閲覧者にはこれらの生成ツールは不要です。

リポジトリrootから実行します。すべてこの作業コピー内の相対参照です。

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
 /Applications/FreeCAD.app/Contents/Resources/bin/python -B media/source/export_c08.py --repo .
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup \
 --python media/source/render_c08_clear.py -- --all
QT_QPA_PLATFORM=offscreen PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
 /Applications/FreeCAD.app/Contents/Resources/bin/python -B media/source/compose_c08_clear.py
```

生成する最終成果は `media/c08-motion.mp4`、`media/c08-poster.png`、`media/player.html`です。
途中のJSON/連番画像/キー画像はこのsourceフォルダーに生成しますが、再生成可能なのでgitへ収録しません。
Blenderの保存時だけ `c08-clear-animation.blend` を更新します。公開C08のnative/STEPは保存しません。

`render_c08.py`は従来のC08レンダリング関数を再利用する補助コードです。
その旧22秒版のmainは今回のコマンドでは実行しません。
`clarity_timeline.py`が40秒の演出時刻を決め、Web側の`motion-contract.js`が同じ動作値を使います。

## 原理と未検証事項

ハブの軸位置は固定、可動円盤だけが0.20mm移動します。
ばねは根元が残り先端が動く補間で、構造/磁気解析ではありません。
模式断面はすき間だけを分かりやすく拡大した別の説明図で、加工寸法図ではありません。
回転マークは部品のローカル座標に追随し、摩擦矢印は接触後から停止前だけです。
機体の起立/姿勢保持成功や、全M3化・実機適合の達成は示しません。

元C08の配布境界と権利はリポジトリの `NOTICE.md` / `docs/PUBLIC_SCOPE.md` を参照します。
非公開のPico原CADやメーカー形状は含みません。旧卓上R1は別の用途違いの履歴です。
