"""Explicit, fail-closed provenance policy. No input geometry is imported here."""
from pathlib import Path
import argparse
import hashlib
import json
import re

SOURCE_SHA256 = "586682c6e77fc6f597dd80c3d3fab6e1fd390f0adec86c05ac001dd3da9a0f21"
SOURCE_COMMIT = "4cdb9b99f4ac9d4b8e31c9000217f6886a557dd8"
POLICY_VERSION = "public-c08-v1"
ROOT = Path(__file__).resolve().parents[1]

# Counts are deliberate; an unreviewed suffix never becomes publishable.
FAMILIES = {
    "YOKE": 1, "POLE_CAP_INNER": 1, "POLE_CAP_OUTER": 1, "COIL_RETAINER": 1,
    "LINING": 3, "LINING_KEEPER": 3, "RETAINER_BOLT": 6,
    "BOBBIN": 1, "WINDING": 1, "BOBBIN_PAD": 3, "BOBBIN_REAR_INSULATOR": 1,
    "LEAD_BUSHING": 2, "CARRIER": 1, "STATOR_LOCATING_PIN": 2,
    "STATOR_BOLT": 4, "STATOR_WASHER": 4, "POST": 4, "FRAME_BOLT": 4, "FRAME_NUT": 4,
    "BEARING_CAP": 1, "BEARING_OUTER": 1, "BEARING_INNER": 1,
    "HUB_INNER_RACE_REAR_SHIM": 1, "BEARING_BALL": 10, "CAP_BOLT": 3,
    "RIM_BOLT": 8, "RIM_NUT": 8, "HUB": 1, "HUB_FACE": 1,
    "HUB_CONNECT_BOLT": 3, "HUB_CONNECT_PIN": 3, "HUB_RETAINING_RING": 1,
    "HUB_DOWEL": 2, "POSITIVE_CROSSPIN": 1, "WHEEL_BOLT": 4, "WHEEL_NUT": 4,
    "ARMATURE": 1, "SPRING": 3, "SPRING_CLAMP_ROOT": 3, "SPRING_CLAMP_TIP": 3,
    "SPRING_ROOT_BOLT": 6, "SPRING_TIP_BOLT": 6,
    "SPRING_ROOT_NUT_PLATE": 3, "SPRING_TIP_NUT_PLATE": 3, "RELEASE_STOP": 3,
    "MOTOR_INTERFACE_BOLT": 3, "STRAIN_CLAMP": 1, "STRAIN_INSULATOR": 2,
    "STRAIN_INSULATOR_LID": 2, "LEAD_CRIMP_COLLAR": 2, "INSULATED_LEAD": 2,
    "STRAIN_BOLT": 2,
}
ALLOWED = tuple(
    name if count == 1 else f"{name}_{index}"
    for name, count in FAMILIES.items()
    for index in range(count)
)
REFERENCES = {
    "REF_WHEEL": {
        "label": "参考円盤",
        "replaces": "Z_WHEEL",
        "recipe": "New plain annulus OD116 / bore28.4 / thickness3.2, with only authored C08 connection holes and access windows; no original spokes, rim or BREP.",
    },
    "REF_FRAME": {
        "label": "参考支持リング",
        "replaces": "Z_LOAD_FRAME",
        "recipe": "New annulus OD138 / ID120 / thickness5.2 with four PCD126 holes; not the source frame, a corner or a Pico cube.",
    },
    "REF_MOTOR_ENVELOPE": {
        "label": "参考モーター包絡",
        "replaces": None,
        "recipe": "New arbitrary OD28 by22 cylinder for orientation only. No source motor surface, mounting thread, performance or compatibility claim.",
    },
    "REF_SHAFT": {
        "label": "参考入力軸",
        "replaces": "Z_NOMINAL_MOTOR_SHAFT",
        "recipe": "New nominal OD6 cylinder with a diameter2 cross-bore. Required interface illustration, not an actual motor shaft.",
    },
}


def family(name):
    return re.sub(r"_\d+$", "", name)


def provenance_for(name):
    if name not in ALLOWED:
        raise ValueError(f"Unreviewed source geometry is forbidden: {name}")
    base = family(name)
    if base in {"CARRIER", "HUB"}:
        return {
            "kind": "authored-c08-primitives",
            "evidence": "mechanism.py:221-281,350-394,491-525",
            "basis": "Created with cylinders, annuli and boxes. No source BREP is an operand. Only three nominal PCD30 hole-center coordinates were read from source motor CAD; those coordinates do not establish actual motor compatibility.",
        }
    if base.startswith("BEARING_") or base == "HUB_RETAINING_RING":
        return {
            "kind": "authored-standard-schematic",
            "evidence": "mechanism.py:312-326,401-405",
            "basis": "Independently constructed annuli, torus grooves, spheres or slotted ring from nominal dimensions. No manufacturer CAD, catalog drawing or detailed commercial geometry is imported. Not a bearing/ring stress model.",
        }
    if "BOLT" in base or base.endswith("_NUT") or base.endswith("_WASHER"):
        return {
            "kind": "authored-fastener-schematic",
            "evidence": "mechanism.py:111-146 and its explicit screw() call sites",
            "basis": "Independent cylinder/cone/hexagonal primitives, major-diameter thread representation. No third-party fastener library or manufacturer file. Custom shoulder and head forms are labelled as design forms.",
        }
    return {
        "kind": "authored-c08-primitives",
        "evidence": "mechanism.py:147-232,277-326,350-550",
        "basis": "Evaluated new component made by the authored primitive/curve operations. No original wheel, frame, corner or motor BREP is an operand for this part. Only this allowlisted Shape is copied to a new document.",
    }


def excluded_reason(name):
    if name.endswith("_WHEEL"):
        return "Original wheel plus Boolean modifications; redistribution permission unknown. Replaced with independent REF_WHEEL."
    if name.endswith("_LOAD_FRAME"):
        return "Original frame plus Boolean bosses/holes; a metal variant is not independent authorship. Replaced with independent REF_FRAME."
    if name.startswith("SRC_"):
        return "Retained or modified original assembly leaf (including metal corner variants); redistribution permission unknown."
    if name.endswith("_NOMINAL_MOTOR_SHAFT"):
        return "Nominal interface illustration not imported; a new REF_SHAFT is constructed without source shape access."
    if "_CORNER_BOLT_" in name:
        return "The associated original corner is excluded. Its disconnected fastener is not part of this public fixture."
    if name.startswith(("X_", "Y_")):
        return "Not extracted. Reference three-axis mode uses rigid copies of the reviewed public Z module, not a reconstruction of the original whole machine."
    if "WindingOuter" in name or "WindingInner" in name:
        return "Construction operand only; publish only the evaluated WINDING solid without links or design dependencies."
    if "_FREE_" in name or name.startswith("BUDGET_"):
        return "Uninstalled free-shape/electronics reservation reference omitted; not part of the public assembly."
    return "Not on the explicit public shape allowlist; excluded by default."


def make_policy(source_names):
    selected = {"Z_" + name for name in ALLOWED}
    missing = selected - set(source_names)
    if missing:
        raise ValueError("Missing audited source parts: " + ", ".join(sorted(missing)))
    inclusions = [{
        "source_part": "Z_" + name, "public_part": name,
        "method": "copy-evaluated-authored-shape-to-new-document",
        **provenance_for(name),
        "external_links_copied": False,
    } for name in ALLOWED]
    inclusions.extend({
        "source_part": row["replaces"], "public_part": name,
        "method": "generate-independent-reference-primitive",
        "kind": "independent-reference", "basis": row["recipe"],
        "external_links_copied": False,
    } for name, row in REFERENCES.items())
    return {
        "schema": POLICY_VERSION,
        "source_identity": {"revision": "C08", "commit": SOURCE_COMMIT, "sha256": SOURCE_SHA256},
        "original_geometry_redistribution": "UNKNOWN / NOT PERMITTED BY THIS PACKAGE",
        "source_documents_are_not_payloads": True,
        "module_count": len(inclusions),
        "included": inclusions,
        "excluded": [{"source_part": name, "reason": excluded_reason(name)}
                     for name in sorted(set(source_names) - selected)],
        "three_axis_rule": "Rigid repetitions of the public Z module; reference layout only; not original C08 whole-machine fit evidence.",
        "whole_fit": False, "build_ready": False, "physical_ready": False,
    }


def validate_request(names):
    if len(names) != len(set(names)):
        raise ValueError("Duplicate requested parts")
    for name in names:
        provenance_for(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    if source.is_relative_to(ROOT):
        raise ValueError("The private input must remain outside the public worktree")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != SOURCE_SHA256:
        raise ValueError("C08 input hash mismatch")
    import FreeCAD as App
    document = App.openDocument(str(source))
    try:
        names = [obj.Name for obj in document.Objects if hasattr(obj, "Shape")]
        policy = make_policy(names)
    finally:
        App.closeDocument(document.Name)
    if hashlib.sha256(source.read_bytes()).hexdigest() != before:
        raise ValueError("Read-only source changed")
    output = ROOT / "data/provenance.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n")
    print(f"Policy: {len(policy['included'])} public parts; {len(policy['excluded'])} excluded source objects")


if __name__ == "__main__":
    main()
