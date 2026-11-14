"""A sequential explanatory timeline; time is presentation, not a measured response."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FPS = 24
DURATION = 40
PULL_START = 18.0
CONTACT = 22.0
STOP = 29.0
RELEASE_START = 32.5
RELEASE_END = 35.5


def smooth(value):
    u = min(1.0, max(0.0, value))
    return u * u * (3 - 2 * u)


def make_timeline():
    frames = []
    angle = 20.0
    for i in range(FPS * DURATION):
        t = i / FPS
        if t < 3:
            stage, view = "intro", "Overview"
        elif t < 6:
            stage, view = "turn_on", "Mechanism"
        elif t < 11:
            stage, view = "together", "Mechanism"
        elif t < 14:
            stage, view = "coast", "Mechanism"
        elif t < 17:
            stage, view = "gap_off", "Schematic"
        elif t < 18:
            stage, view = "magnet_on", "Schematic"
        elif t < CONTACT:
            stage, view = "pull", "Schematic"
        elif t < 24:
            stage, view = "contact", "Schematic"
        elif t < STOP:
            stage, view = "slow_down", "Mechanism"
        elif t < 30.5:
            stage, view = "stopped", "Mechanism"
        elif t < 32:
            stage, view = "stopped_section", "Schematic"
        elif t < RELEASE_END:
            stage, view = "release", "Schematic"
        elif t < 37:
            stage, view = "gap_restored", "Schematic"
        else:
            stage, view = "final", "Mechanism"

        speed = 0.0
        if 4 <= t < 11:
            speed = 76 * smooth((t - 4) / .8)
        elif 11 <= t < CONTACT:
            speed = 76 - 6 * min(1, (t - 11) / 3)
        elif CONTACT <= t < STOP:
            speed = 70 * (1 - smooth((t - CONTACT) / (STOP - CONTACT)))
        angle += speed / FPS
        delta = .2 * smooth((t - PULL_START) / (CONTACT - PULL_START))
        if t >= RELEASE_START:
            delta = .2 * (1 - smooth((t - RELEASE_START) / (RELEASE_END - RELEASE_START)))
        frames.append({
            "frame": i + 1, "time_s": t, "stage": stage, "view": view,
            "rotor_angle_deg": angle, "render_speed_deg_s": speed,
            "armature_axial_mm": delta, "hub_axial_mm": 0.0,
            "drive_on": 4 <= t < 11, "coil_on": 17 <= t < 32,
            "contact": delta >= .2 - 1e-10,
            "friction_arrow": CONTACT <= t < STOP,
            "pull_arrow": 17 <= t < CONTACT,
            "return_arrow": RELEASE_START <= t < RELEASE_END,
        })
    return {
        "schema": "c08-sequential-clarity-v2", "fps": FPS, "duration_s": DURATION,
        "nominal_C08_gap_mm": .2, "actual_CAD_displacement_amplification": 1,
        "schematic": {
            "not_fabrication_geometry": True, "screen_gap_model_units": .36,
            "mapping": "0.20mm source closure ->0.36 visual units; only the conceptual axial gap is amplified",
            "required_label": "模式断面：すき間・動きは説明用に拡大",
            "hub_position_fixed": True, "root_fixed_tip_follows": True,
        },
        "events_s": {"drive_on": 4, "drive_off": 11, "coil_on": 17,
                     "pull_begins": PULL_START, "contact": CONTACT,
                     "stop": STOP, "coil_off": 32, "release_begins": RELEASE_START,
                     "release_complete": RELEASE_END},
        "frames": frames, "physical_ready": False, "attitude_success_shown": False,
    }


if __name__ == "__main__":
    data = make_timeline()
    (ROOT / "clarity-timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("40seconds / 960frames; one view at a time; source displacement0.20mm.")
