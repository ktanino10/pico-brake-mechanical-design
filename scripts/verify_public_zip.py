"""Prove the curated ZIP can re-export without any non-distributed design input."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile

from public_files import ZIP_FILES
from geometry_contract import mesh_moments
from public_policy import ROOT
from public_scan import inspect_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="A new verification directory")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Verification output must be a new directory")
    archive_path = ROOT / "downloads/public-brake-cad.zip"
    inspect_file(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        if set(archive.namelist()) != set(ZIP_FILES) | {"SHA256SUMS.json"}:
            raise ValueError("ZIP file list is not the curated public set")
        proof = json.loads(archive.read("SHA256SUMS.json"))
        for item in proof["files"]:
            if hashlib.sha256(archive.read(item["path"])).hexdigest() != item["sha256"]:
                raise ValueError("An archived public file differs from its manifest")
        unpacked = args.output / "package"
        unpacked.mkdir(parents=True)
        archive.extractall(unpacked)
    result = subprocess.run(
        [sys.executable, "-B", str(unpacked / "scripts/reexport_public.py"),
         "--output", str(args.output / "reexport")],
        cwd=unpacked, check=True, capture_output=True, text=True,
    )
    saved = json.loads((args.output / "reexport/reexport-check.json").read_text())
    if saved["status"] != "PASS" or saved["parts"] != 149 or not saved["public_files_only"]:
        raise ValueError("Public-only re-export did not pass")
    original_mesh = ROOT / "data/meshes.json"
    regenerated_mesh = args.output / "reexport/meshes.json"
    original = {part["id"]: part for part in json.loads(original_mesh.read_text())["parts"]}
    regenerated = {part["id"]: part for part in json.loads(regenerated_mesh.read_text())["parts"]}
    if set(original) != set(regenerated):
        raise ValueError("Re-exported mesh part IDs differ from the actual published JSON")
    max_direct_bounds, max_direct_centroid = 0.0, 0.0
    for name in original:
        metrics = []
        for item in (original[name], regenerated[name]):
            vertices = [item["positions"][i:i + 3] for i in range(0, len(item["positions"]), 3)]
            faces = [item["indices"][i:i + 3] for i in range(0, len(item["indices"]), 3)]
            _, center = mesh_moments(vertices, faces)
            box = [min(v[i] for v in vertices) for i in range(3)] + [max(v[i] for v in vertices) for i in range(3)]
            metrics.append((box, center))
        db = max(abs(a - b) for a, b in zip(metrics[0][0], metrics[1][0]))
        dc = sum((a - b) ** 2 for a, b in zip(metrics[0][1], metrics[1][1])) ** 0.5
        if db > 0.002 or dc > 0.002:
            raise ValueError("Re-exported mesh differs from published JSON: " + name)
        max_direct_bounds = max(max_direct_bounds, db)
        max_direct_centroid = max(max_direct_centroid, dc)
    report = {
        "schema": "public-brake-self-contained-v1", "status": "PASS",
        "source": "Curated public ZIP, unpacked outside the checkout",
        "zip_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "parts": 149, "private_design_input_used": False,
        "native_input_sha256": hashlib.sha256((unpacked / "downloads/brake-single.FCStd").read_bytes()).hexdigest(),
        "reexported_step_valid": saved["step"]["valid_solids"],
        "step_named_parts_match": saved["step"]["step_named_parts_match"],
        "mesh_parts": saved["mesh"]["parts"],
        "mesh_compared_to_original_published_moments": saved["mesh"]["compared_to_published_mesh_moments"],
        "max_reexport_mesh_bounds_error_mm": saved["mesh"]["max_reexport_mesh_bounds_error_mm"],
        "max_reexport_mesh_centroid_error_mm": saved["mesh"]["max_reexport_mesh_centroid_error_mm"],
        "direct_existing_mesh_json_comparison": {
            "parts": len(original), "max_bounds_error_mm": max_direct_bounds,
            "max_centroid_error_mm": max_direct_centroid,
            "original_sha256": hashlib.sha256(original_mesh.read_bytes()).hexdigest(),
            "regenerated_sha256": hashlib.sha256(regenerated_mesh.read_bytes()).hexdigest(),
        },
        "reference_interface_checks": len(saved["reference_interfaces"]["checks"]),
        "whole_fit": False, "build_ready": False, "physical_ready": False,
    }
    (ROOT / "validation/reexport.json").write_text(json.dumps(report, indent=2) + "\n")
    release_path = ROOT / "data/checksums.json"
    release = json.loads(release_path.read_text())
    for item in release["files"]:
        if hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("A release file changed during independent ZIP verification")
    release["downloads_ready"] = True
    release["reason"] = "公開データの整合確認済み。実機・製作・物理検証の資格ではありません。"
    release_path.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n")
    print(result.stdout.strip())
    print("Curated ZIP opened and re-exported using only its public contents.")


if __name__ == "__main__":
    main()
