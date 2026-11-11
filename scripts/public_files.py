"""The only files eligible for serving, packaging and local public freeze."""

PUBLIC_FILES = (
    ".gitignore", ".gitattributes", "README.md", "NOTICE.md", "index.html", "styles.css",
    "app.js", "bootstrap.js", "contract.js", "package.json", "package-lock.json",
    "docs/PUBLIC_SCOPE.md", "docs/VALIDATION.md",
    "data/provenance.json", "data/assembly.json", "data/meshes.json",
    "data/parts.csv", "data/joints.csv", "data/checksums.json",
    "downloads/brake-single.FCStd", "downloads/brake-single.step",
    "downloads/brake-reference-three.FCStd", "downloads/brake-reference-three.step",
    "downloads/public-brake-cad.zip",
    "vendor/three.module.js", "vendor/three.core.js", "vendor/OrbitControls.js",
    "vendor/THREE-LICENSE.txt", "vendor/manifest.json",
    "scripts/public_policy.py", "scripts/catalog.py", "scripts/build_cad.py", "scripts/geometry_contract.py",
    "scripts/reexport_public.py", "scripts/public_files.py", "scripts/serve_public.py",
    "scripts/public_scan.py", "scripts/package_public.py", "scripts/verify_public_zip.py", "scripts/vendor.mjs",
    "tests/contract.test.mjs", "tests/browser.mjs", "tests/test_public.py",
    "validation/cad.json", "validation/browser.json", "validation/reexport.json", "validation/public.json",
)

WEB_FILES = tuple(name for name in PUBLIC_FILES if not name.startswith((".", "tests/", "scripts/")))

ZIP_FILES = (
    "README.md", "NOTICE.md", "docs/PUBLIC_SCOPE.md",
    "data/provenance.json", "data/assembly.json", "data/parts.csv", "data/joints.csv",
    "downloads/brake-single.FCStd", "downloads/brake-single.step",
    "downloads/brake-reference-three.FCStd", "downloads/brake-reference-three.step",
    "scripts/reexport_public.py", "scripts/build_cad.py", "scripts/catalog.py", "scripts/geometry_contract.py",
    "scripts/public_policy.py", "validation/cad.json",
)
