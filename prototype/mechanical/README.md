# 機械試作 R1データ

元C08や教材を変更しない、独立軸・ソレノイド摩擦ブレーキの名目試作データです。
**加工形状は選定済みですが、現物適合・通電・回転の合格ではありません。**

- `prototype-mechanical.step`: 82個の独立形状。市販部品・モーターは簡略包絡を含む。
- `stl/`: 低温側PLA支持部17個、各1個印刷。mm単位・底面Z=0。
- `rotor-cut.dxf`: SUS304 t1円板、外径60、内径12.10、6×φ3.2/PCD19。
- `pad-back-cut.dxf` / `link-cut.dxf`: A5052 t1裏板2枚 / t1.5リンク1枚。
- `guard-*-cut.dxf`: PC t3の上1枚、端2枚、側2枚。左端だけ追加グロメット孔は図を参照。
- `*-drawing.svg` / `machine-parts.svg` / `base-drill.svg`: 加工・穴位置・小物の寸法。
- `sensor-track.svg`: 半径13.5〜18.5、黒12/白12の連続円環。100%印刷。
- `joints.csv`: M3使用ねじ75本の接合別スタック。付属ねじと予備は別。
- `manifest.json`: 名目値・座標・出所の区別、幾何検査、計算、SHA-256。

CAD図面にない電気接続を形状から推測しないでください。
組立と採用条件はリポジトリの `docs/PROTOTYPE_MECHANICAL.md` と `docs/PROTOTYPE_SIGNAL.md` を参照します。
ZIPから読む場合はこれらも別途取得してください。ピン配置を検証したハードウェアドライバは含みません。

再生成（リポジトリroot、既存FreeCAD Python環境）:

```sh
PYTHONPATH=/Applications/FreeCAD.app/Contents/Resources/lib \
  /Applications/FreeCAD.app/Contents/Resources/bin/python -B scripts/build_prototype_mechanics.py
```

同じR1出力先だけを更新します。ほかのCAD・配布ZIPは更新しません。
