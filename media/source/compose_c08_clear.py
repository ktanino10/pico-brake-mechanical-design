"""Compose one-view C08 explanation with large Japanese labels and encode silent H.264."""
import argparse
import base64
import json
import math
from pathlib import Path
import shutil
import subprocess
import zipfile

from PySide6 import QtCore, QtGui

ROOT = Path(__file__).resolve().parent
MEDIA_ROOT = ROOT.parent
STAGES = {
    "intro": ("3軸姿勢制御用のブレーキ", "この１軸の動きを見ます"),
    "turn_on": ("1  回る", "モーターON  →  白い印が動き出す"),
    "together": ("1  回る", "ホイールと奥の薄い円盤が、一緒に回る"),
    "coast": ("1  回る", "駆動OFFでも、惰性で回り続ける"),
    "gap_off": ("2  電磁石が引く", "OFF：まだ、すき間がある"),
    "magnet_on": ("2  電磁石が引く", "ON：電磁石が円盤を引き寄せる"),
    "pull": ("2  電磁石が引く", "動くのは薄い円盤。ハブの軸位置はそのまま"),
    "contact": ("3  接触して止まる", "固定された摩擦面に、触れた"),
    "slow_down": ("3  接触して止まる", "接触を保ったまま、摩擦で回転が遅くなる"),
    "stopped": ("3  接触して止まる", "白い印が止まった"),
    "stopped_section": ("3  接触して止まる", "停止。面は接触したまま"),
    "release": ("最後に、ばねで解除", "電磁石OFF  →  ばねで円盤が離れる"),
    "gap_restored": ("最後に、ばねで解除", "すき間が戻った。回転は再開しない"),
    "final": ("離れても、回転は停止したまま", "自動では再始動しない説明です"),
}
BG = "#101c2b"
TEXT = "#eef5fd"
BLUE = "#79bfff"
GRAY = "#b4c0cd"
ORANGE = "#ffbc71"
GREEN = "#b8df82"
YELLOW = "#ffe083"
KEYS = {
    49: "01-xyz", 169: "02-rotation", 289: "03-coast", 385: "04-gap-off",
    457: "05-pull", 541: "06-contact", 625: "07-decelerating",
    709: "08-stopped", 745: "09-stopped-section", 829: "10-release", 913: "11-no-restart",
}


def color(value):
    return QtGui.QColor(value)


def font(size, bold=False):
    f = QtGui.QFont("Hiragino Sans")
    f.setPixelSize(size)
    f.setWeight(QtGui.QFont.Weight.Bold if bold else QtGui.QFont.Weight.Medium)
    return f


def text(p, x, y, value, size=28, fill=TEXT, bold=False):
    p.setFont(font(size, bold))
    p.setPen(color(fill))
    p.drawText(QtCore.QPointF(x, y), value)


def panel(p, x, y, w, h, fill="#142b40", alpha=235):
    c = color(fill)
    c.setAlpha(alpha)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawRoundedRect(QtCore.QRectF(x, y, w, h), 8, 8)


def line(p, a, b, fill=TEXT, width=2):
    pen = QtGui.QPen(color(fill), width)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(*a), QtCore.QPointF(*b))


def arrow(p, a, b, fill=ORANGE, width=11, head=24):
    delta = (b[0]-a[0], b[1]-a[1])
    length = math.hypot(*delta)
    if length < 8:
        return
    ux, uy = delta[0]/length, delta[1]/length
    head = min(head, length*.45)
    neck = (b[0]-head*ux, b[1]-head*uy)
    line(p, a, neck, fill, width)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(color(fill))
    p.drawPolygon(QtGui.QPolygonF([
        QtCore.QPointF(*b), QtCore.QPointF(neck[0]-head*.52*uy, neck[1]+head*.52*ux),
        QtCore.QPointF(neck[0]+head*.52*uy, neck[1]-head*.52*ux)]))


def label(p, x, y, title, point, fill=TEXT, size=27):
    metrics = QtGui.QFontMetrics(font(size, True))
    w = metrics.horizontalAdvance(title) + 28
    line(p, (x+w/2, y+19), point, fill, 2)
    panel(p, x, y, w, 41)
    text(p, x+14, y+30, title, size, fill, True)


def draw_frame(frame, points):
    path = ROOT / "clarity-frames" / f'{frame["frame"]:04d}.png'
    raw = QtGui.QImage(str(path))
    if raw.isNull():
        raise ValueError("Missing render: " + str(path))
    image = QtGui.QImage(1280, 720, QtGui.QImage.Format.Format_RGB32)
    image.fill(color(BG))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.drawImage(QtCore.QPoint(0, 104), raw)
    title, sub = STAGES[frame["stage"]]
    text(painter, 26, 53, title, 42, TEXT, True)
    text(painter, 29, 92, sub, 27, "#c4d8eb")
    for x, fill, title in [(770,BLUE,"回る側"),(940,GRAY,"固定側"),(1100,ORANGE,"電磁石")]:
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(color(fill))
        painter.drawRect(QtCore.QRectF(x, 28, 18, 18))
        text(painter, x+28, 46, title, 24, fill, True)

    if frame["view"] == "Overview":
        panel(painter, 380, 557, 520, 53)
        text(painter, 410, 594, "３軸のうち、１つを大きく見ます", 28, TEXT, True)
    elif frame["view"] == "Mechanism":
        if frame["stage"] in ("turn_on","together"):
            a = points["actual"]
            label(painter, 34, 409, "ホイール", a["wheel"], BLUE)
            label(painter, 930, 191, "奥の薄い円盤", a["armature"], BLUE)
            label(painter, 925, 370, "固定側は動かない", a["fixed"], GRAY, 23)
        if frame["stage"] == "slow_down":
            panel(painter, 28, 482, 345, 46, "#3c2424")
            text(painter, 42, 515, "摩擦は、回転と逆向き", 28, "#ffa393", True)
            if 26.2 <= frame["time_s"] < 29:
                panel(painter, 28, 543, 400, 42)
                text(painter, 42, 573, "力は固定部から機体へ伝わる", 25, GRAY)
        elif frame["stage"] == "stopped":
            panel(painter, 34, 406, 185, 72)
            text(painter, 63, 458, "停止", 47, YELLOW, True)
        panel(painter, 24, 153, 449, 40)
        status = "駆動 " + ("ON" if frame["drive_on"] else "OFF") + "     電磁石 " + ("ON" if frame["coil_on"] else "OFF")
        text(painter, 38, 183, status, 25, ORANGE if frame["coil_on"] else GRAY, True)
        text(painter, 26, 135, "実CADの形状／見やすく一部を省略・透過", 20, "#acc1d7")
    else:
        progress = frame["armature_axial_mm"] / .2
        displacement_px = .36*progress*1280/3.75
        xdisc = points["schematic"]["disc"][0] + displacement_px
        label(painter, 360, 185, "動く円盤", (xdisc, 246), BLUE, 30)
        label(painter, 842, 141, "固定の摩擦面", (817.5, 309), GRAY, 26)
        panel(painter, 902, 317, 206, 60, "#6e381a")
        text(painter, 916, 358, "電磁石 " + ("ON" if frame["coil_on"] else "OFF"), 30, ORANGE, True)
        panel(painter, 145, 548, 270, 47)
        text(painter, 160, 581, "ハブの軸位置は固定", 26, TEXT, True)
        label(painter, 435, 506, "ばね", (510, 474), GREEN, 25)
        if frame["stage"] in ("gap_off","gap_restored"):
            x0 = 682
            line(painter, (x0,432), (800,432), "#dce9f5", 2)
            line(painter, (x0,422), (x0,442), "#dce9f5", 2)
            line(painter, (800,422), (800,442), "#dce9f5", 2)
            text(painter, 696, 474, "すき間", 29, TEXT, True)
        if frame["pull_arrow"]:
            start = (688+displacement_px, 375)
            end = (797,375)
            arrow(painter,start,end,ORANGE,11,22)
            if end[0]-start[0] > 38:
                text(painter, start[0]-6, 351, "引く", 28, ORANGE, True)
        if frame["return_arrow"]:
            arrow(painter,(793,376),(688+displacement_px,376),GREEN,11,22)
            text(painter, 575, 386, "戻る", 27, GREEN, True)
        if frame["contact"]:
            label(painter, 433, 337, "接触", (804,415), YELLOW, 39)
            if frame["stage"] == "stopped_section":
                panel(painter, 430, 405, 225, 47)
                text(painter, 451, 439, "接触したまま停止", 25, YELLOW, True)
        panel(painter, 455, 621, 800, 55)
        text(painter, 475, 646, "模式断面：すき間・動きは説明用に拡大", 23, "#e4ce9c", True)
        text(painter, 475, 669, "実C08の名目すき間は0.20mm。電磁石そのものには接触しません。", 18, "#c4d8eb")
    painter.fillRect(0, 680, 1280, 40, color(BG))
    text(painter, 27, 708, "説明用CG｜時間・速度は演出｜実機未検証", 21, "#d6c296", True)
    painter.end()
    return image


def players():
    template = """<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>3軸姿勢制御用 C08ブレーキ｜回る・引く・止まる</title>
<style>body{margin:0;background:#101c2b;color:#eef5fd;font:17px/1.7 system-ui,sans-serif}
main{max-width:1280px;padding:24px;margin:auto}h1{font-size:26px;margin:0 0 10px}
video{width:100%;display:block;border-radius:10px;background:#101c2b}p{margin:10px 0;color:#bed1e5}
button{background:#244663;color:#eff6ff;border:1px solid #89b7d6;border-radius:7px;padding:10px 18px;font:inherit;cursor:pointer}
nav{display:flex;gap:12px;flex-wrap:wrap;margin:15px 0}.notice{color:#e5cd96}details{margin-top:18px}summary{cursor:pointer}</style>
<main><h1>3軸姿勢制御用 C08ブレーキ：回る → 引く → 止まる</h1>
<video id="motion" controls autoplay muted playsinline preload="auto" poster="POSTER" aria-label="C08ブレーキを三つの大きな場面で示す無音CG">
<source src="MOVIE" type="video/mp4">動画対応ブラウザーで開いてください。</video>
<nav aria-label="場面を選ぶ"><button type="button" data-time="3">1 回る</button><button type="button" data-time="14">2 引く・断面</button><button type="button" data-time="22">3 接触して止まる</button></nav>
<p id="playback" role="status">無音で再生します。</p>
<p>青は回る側、灰は固定側、橙は電磁石。白い回転マークと、接触前後の大きな断面に注目してください。</p>
<p class="notice">説明用CG・時間と速度は演出・実機未検証。</p>
<p>模式断面は「すき間・動き」を説明用に拡大した別の図です。実C08の名目すき間は0.20mm。
立体主モデルでは元の寸法を維持し、ハブは軸方向に動かさず、可動円盤だけを動かしています。</p>
<details><summary>原機構と、映像では証明していないこと</summary>
<p>磁力は軸方向へ円盤を引き、停止を生む摩擦は回転の接線方向です。接触前は制動矢印を出さず、停止後は消しています。
外力がない停止状態で、一定の保持トルクが発生し続けるとは表していません。</p>
<p>元の公開C08にはM2/M2.5/M3/M4があり、全M3化していません。独立参考ホイール・モーター・138mm筐体は現物適合の証明ではありません。
起立・姿勢保持の成功や、磁気・ばね・摩擦を解いた実機検証ではありません。解除後の非再始動も説明上の動作で、制御FWは未実装です。</p>
<p>旧卓上R1は用途違いの履歴です。直前の22秒C08版も別名で保存し、この40秒版で説明を改訂しました。
新しいBOM、配線、実機CADは作成・変更していません。</p></details>
<script>const v=document.getElementById('motion');const status=document.getElementById('playback');
v.defaultMuted=true;v.muted=true;v.volume=0;
function start(){return v.play().then(()=>{status.textContent='無音で再生中。停止・シーク・場面選択を使えます。';})
.catch(()=>{status.textContent='自動再生が制限されています。再生ボタンで無音再生できます。';});}
for(const b of document.querySelectorAll('[data-time]'))b.addEventListener('click',()=>{v.currentTime=Number(b.dataset.time);start();});
v.addEventListener('error',()=>{status.textContent='動画を読み込めません。相対ファイル版はZIPを展開して開いてください。';});
start();</script></main></html>"""
    (MEDIA_ROOT/"player.html").write_text(template.replace("POSTER","c08-poster.png").replace("MOVIE","c08-motion.mp4"))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--preview",default="")
    args=parser.parse_args()
    app=QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    data=json.loads((ROOT/"clarity-timeline.json").read_text())
    points=json.loads((ROOT/"clarity-label-points.json").read_text())
    if args.preview:
        out=ROOT/"clarity-previews";out.mkdir(exist_ok=True)
        for number in [int(v) for v in args.preview.split(",")]:
            image=draw_frame(data["frames"][number-1],points)
            if not image.save(str(out/f"{number:04d}.png")):
                raise ValueError("Could not save preview")
        return
    command=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24",
             "-s","1280x720","-r","24","-i","pipe:0","-an","-frames:v","960","-c:v","libx264",
             "-preset","medium","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart",str(MEDIA_ROOT/"c08-motion.mp4")]
    with subprocess.Popen(command,stdin=subprocess.PIPE) as process:
        for frame in data["frames"]:
            image=draw_frame(frame,points).convertToFormat(QtGui.QImage.Format.Format_RGB888)
            if image.bytesPerLine()!=1280*3:
                raise ValueError("Unexpected RGB stride")
            process.stdin.write(bytes(image.constBits()))
        process.stdin.close()
        code=process.wait()
        if code!=0:
            raise RuntimeError(f"ffmpeg failed:{code}")
    out=ROOT/"clarity-keyframes";out.mkdir(exist_ok=True)
    for frame,name in KEYS.items():
        subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss",str((frame-1)/24),
                        "-i",str(MEDIA_ROOT/"c08-motion.mp4"),"-frames:v","1","-update","1",str(out/(name+".png"))],check=True)
    shutil.copyfile(out/"04-gap-off.png",MEDIA_ROOT/"c08-poster.png")
    players()
    print("40s / 960 frames / one full-screen view at a time; MP4 and portable players updated.")


if __name__=="__main__":
    main()
