"""The only files eligible for serving, packaging and local public freeze."""

PUBLIC_FILES = (
    ".gitignore", ".gitattributes", ".nojekyll", "README.md", "NOTICE.md", "index.html", "styles.css",
    "app.js", "bootstrap.js", "contract.js", "package.json", "package-lock.json",
    "overview.html", "overview.js", "overview.css", "overview-bootstrap.js",
    "data/overview-layout.json", "docs/OVERVIEW.md", "scripts/build_overview_layout.py",
    "tests/overview.test.mjs", "tests/overview-browser.mjs", "validation/overview.json",
    "docs/PUBLIC_SCOPE.md", "docs/VALIDATION.md",
    "data/provenance.json", "data/assembly.json", "data/meshes.json",
    "data/parts.csv", "data/joints.csv", "data/checksums.json",
    "downloads/brake-single.FCStd", "downloads/brake-single.step",
    "downloads/brake-reference-three.FCStd", "downloads/brake-reference-three.step",
    "downloads/public-brake-cad.zip",
    "vendor/three.module.js", "vendor/three.core.js", "vendor/OrbitControls.js",
    "vendor/THREE-LICENSE.txt", "vendor/manifest.json",
    "scripts/public_policy.py", "scripts/catalog.py", "scripts/build_cad.py", "scripts/geometry_contract.py",
    "scripts/enclosure_geometry.py", "scripts/check_corner_slice.py",
    "scripts/enclosure_holders.py", "data/enclosure-nominal-conditions.json",
    "scripts/enclosure_policy.py", "scripts/enclosure_assembly.py",
    "scripts/enclosure_coverage.py",
    "scripts/build_enclosure.py",
    "enclosure.html", "enclosure.js", "enclosure.css", "enclosure-bootstrap.js", "enclosure-contract.js",
    "data/enclosure-assembly.json", "data/enclosure-meshes.json", "data/enclosure-source-coverage.json",
    "data/enclosure-parts.csv", "data/enclosure-joints.csv", "data/enclosure-provenance.json",
    "data/enclosure-checksums.json", "downloads/enclosure-nominal.FCStd", "downloads/enclosure-nominal.step",
    "downloads/enclosure-nominal.zip", "validation/enclosure-cad.json",
    "docs/ENCLOSURE.md", "scripts/package_enclosure.py",
    "tests/enclosure.test.mjs", "tests/test_enclosure.py", "tests/enclosure-browser.mjs",
    "validation/enclosure-browser.json",
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

ENCLOSURE_DOWNLOADS = (
    "downloads/enclosure-nominal.FCStd", "downloads/enclosure-nominal.step", "downloads/enclosure-nominal.zip",
)

ENCLOSURE_ZIP_FILES = (
    "README.md", "NOTICE.md", "docs/ENCLOSURE.md", "docs/PUBLIC_SCOPE.md",
    "downloads/enclosure-nominal.FCStd", "downloads/enclosure-nominal.step",
    "data/enclosure-assembly.json", "data/enclosure-parts.csv", "data/enclosure-joints.csv",
    "data/enclosure-source-coverage.json", "data/enclosure-provenance.json", "data/enclosure-nominal-conditions.json",
    "validation/enclosure-cad.json",
    "downloads/brake-single.FCStd", "data/assembly.json",
    "scripts/build_enclosure.py", "scripts/enclosure_assembly.py", "scripts/enclosure_geometry.py",
    "scripts/enclosure_holders.py", "scripts/enclosure_policy.py", "scripts/enclosure_coverage.py",
    "scripts/check_corner_slice.py", "scripts/build_cad.py", "scripts/geometry_contract.py",
    "scripts/catalog.py", "scripts/public_policy.py", "scripts/public_scan.py",
)
