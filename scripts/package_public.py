"""Build a curated CAD ZIP and audit only an explicit public-file allowlist."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile
import zipfile

from public_files import PUBLIC_FILES, ZIP_FILES
from public_policy import ROOT, SOURCE_SHA256, validate_request
from public_scan import PublicScanError, inspect_bytes, inspect_file


def record(name):
    path = ROOT / name
    return {"path": name, "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def downloads_ready():
    path = ROOT / "validation/reexport.json"
    if not path.is_file():
        return False
    proof = json.loads(path.read_text())
    cad = json.loads((ROOT / "validation/cad.json").read_text())
    return (
        proof.get("status") == "PASS" and
        proof.get("mesh_compared_to_original_published_moments") is True and
        proof.get("zip_sha256") == record("downloads/public-brake-cad.zip")["sha256"] and
        proof.get("native_input_sha256") == record("downloads/brake-single.FCStd")["sha256"] and
        cad.get("status") == "PASS" and
        cad.get("pose_negative_control", {}).get("result") == "REJECTED" and
        all(document.get("expected_pose_basis") and
            document["max_native_world_bounds_error_mm"] <= 1e-6 and
            document["max_native_world_centroid_error_mm"] <= 1e-6
            for document in cad["documents"].values())
    )


def create_package():
    inner_hashes = [record(name) for name in ZIP_FILES]
    target = ROOT / "downloads/public-brake-cad.zip"
    with tempfile.TemporaryDirectory(prefix=".public-package-", dir=target.parent) as directory:
        candidate = Path(directory) / target.name
        with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in (*ZIP_FILES, "SHA256SUMS.json"):
                data = (json.dumps({"files": inner_hashes}, ensure_ascii=False, indent=2) + "\n").encode() if name == "SHA256SUMS.json" else (ROOT / name).read_bytes()
                inspect_bytes(name, data)
                info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
        inspect_file(candidate)
        candidate.replace(target)
    download_names = [name for name in PUBLIC_FILES if name.startswith("downloads/")]
    hashes = [record(name) for name in download_names + ["data/assembly.json", "data/meshes.json"]]
    ready = downloads_ready()
    (ROOT / "data/checksums.json").write_text(json.dumps({
        "schema": "public-brake-downloads-v1", "algorithm": "SHA-256", "files": hashes,
        "downloads_ready": ready,
        "reason": ("公開データの整合確認済み。実機・製作・物理検証の資格ではありません。" if ready else
                   "公開nativeの独立姿勢照合・ZIP再出力検査が完了するまで、CADのダウンロードを停止します。"),
    }, ensure_ascii=False, indent=2) + "\n")
    return len(ZIP_FILES) + 1


def audit(forbidden_native=None, require_all=True):
    names = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                           cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    unknown = set(names) - set(PUBLIC_FILES)
    if unknown:
        raise PublicScanError("Files outside the public allowlist: " + ", ".join(sorted(unknown)))
    missing = [name for name in PUBLIC_FILES if not (ROOT / name).is_file()
               and name != "validation/public.json"]
    if missing and require_all:
        raise PublicScanError("Missing deliverables: " + ", ".join(missing))
    details = {}
    for name in PUBLIC_FILES:
        if (ROOT / name).is_file() and name != "validation/public.json":
            details[name] = inspect_file(ROOT / name, name)
    cad = json.loads((ROOT / "validation/cad.json").read_text())
    if cad["status"] != "PASS" or not cad["source_unchanged"] or cad["source_sha256"] != SOURCE_SHA256:
        raise PublicScanError("CAD validation is absent or not bound to the reviewed input")
    for document in cad["documents"].values():
        for item in document["files"]:
            if record(item["path"]) != item:
                raise PublicScanError("A CAD file differs from its readback receipt")
    assembly = json.loads((ROOT / "data/assembly.json").read_text())
    if record("data/meshes.json")["sha256"] != assembly["mesh"]["sha256"]:
        raise PublicScanError("Mesh differs from the public assembly identity")
    vendor = json.loads((ROOT / "vendor/manifest.json").read_text())
    for item in vendor["files"]:
        if record(item["path"])["sha256"] != item["sha256"]:
            raise PublicScanError("Vendored dependency differs from its license/version receipt")
    if require_all:
        release = json.loads((ROOT / "data/checksums.json").read_text())
        if not downloads_ready() or release.get("downloads_ready") is not True:
            raise PublicScanError("Independent public CAD validation has not enabled downloads")
        reexport = json.loads((ROOT / "validation/reexport.json").read_text())
        if (reexport["status"] != "PASS" or reexport["private_design_input_used"] or
                reexport["zip_sha256"] != record("downloads/public-brake-cad.zip")["sha256"]):
            raise PublicScanError("Public-only ZIP re-export proof is incomplete or stale")
        browser = json.loads((ROOT / "validation/browser.json").read_text())
        if browser["status"] != "PASS" or len(browser["downloads"]) != 5:
            raise PublicScanError("Real browser validation is incomplete")
        for item in browser["downloads"]:
            if record(item["path"])["sha256"] != item["sha256"]:
                raise PublicScanError("A download changed after the browser check")
    negative = {}
    for name in ["WHEEL", "LOAD_FRAME", "SRC_Part__Feature12", "CORNER_BOLT_0", "YOKE_99"]:
        try:
            validate_request([name])
        except ValueError:
            negative[name] = "REJECTED"
        else:
            raise PublicScanError("Forbidden shape passed the policy")
    if forbidden_native is not None:
        if hashlib.sha256(forbidden_native.read_bytes()).hexdigest() != SOURCE_SHA256:
            raise PublicScanError("Negative-control native must be the fixed original input")
        try:
            inspect_file(forbidden_native, "forbidden-input.FCStd")
        except PublicScanError:
            negative["full-protected-native"] = "REJECTED"
        else:
            raise PublicScanError("Protected whole document passed the scan")
    return {
        "schema": "public-brake-content-audit-v1", "status": "PASS",
        "scope": "Allowlisted bytes, archives and metadata. No claim of whole-machine or physical approval.",
        "original_native_negative_control": negative.get("full-protected-native", "not-supplied"),
        "negative_controls": negative, "checks": details,
        "files": [record(name) for name in sorted(details)],
        "self_excluded_from_hash_list": "validation/public.json",
        "remaining_files": missing,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forbidden-native", type=Path)
    parser.add_argument("--prepare", action="store_true", help="Package before final browser report exists")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    members = None if args.audit_only else create_package()
    report = audit(args.forbidden_native, require_all=not args.prepare)
    if not args.prepare:
        output = ROOT / "validation/public.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        inspect_file(output)
    print(json.dumps({"audit": report["status"], "stage": "preflight" if args.prepare else "freeze-audit",
                      "files": len(report["checks"]), "downloads_ready": downloads_ready(),
                      "zip_members": members, "missing_files": report["remaining_files"],
                      "negative_controls": report["negative_controls"]}, indent=2))


if __name__ == "__main__":
    main()
