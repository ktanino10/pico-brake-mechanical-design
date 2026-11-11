"""Exact independent enclosure roster; original assembly geometry is never an input."""
import itertools

from public_policy import ALLOWED

PUBLIC_BRAKE_SHA256 = "2bc12d2f0d1617789a57f9b00b3c5fa6d835092e4c1f49f1e0f846dda7ed9116"
PUBLIC_CATALOG_SHA256 = "8fac1425bad538abeb5d72476914b830abf35994b332522016e9c7baeaae8505"
OCTANTS = tuple("".join(signs) for signs in itertools.product("NP", repeat=3))
CAGE_IDS = tuple(
    [f"E_FRAME_{kind}_{axis}" for kind in ("MOTOR", "BOARD") for axis in "XYZ"] +
    [prefix+octant for octant in OCTANTS for prefix in ("E_CORNER_", "E_CORNER_CAP_", "E_CAP_SCREW_")] +
    [f"E_FRAME_SCREW_{octant}_{axis}" for octant in OCTANTS for axis in "XYZ"]
)
HOLDER_IDS = tuple(
    [prefix+kind for kind in ("PCB", "MPU") for prefix in ("E_HOLDER_", "E_REF_BOARD_")] +
    [f"E_HOLDER_FIX_{kind}_{axis}" for kind in ("PCB", "MPU") for axis in "XYZ"] +
    [f"{prefix}{kind}_{index}" for kind, count in (("PCB", 4), ("MPU", 2))
     for index in range(count) for prefix in ("E_SPACER_", "E_WASHER_", "E_BOARD_SCREW_")]
)
INTERFACE_IDS = tuple(f"E_REF_{kind}_{axis}" for axis in "XYZ" for kind in ("MOTOR", "SHAFT"))
BRAKE_IDS = tuple(f"{axis}_{part}" for axis in "XYZ" for part in (*ALLOWED, "REF_WHEEL"))
ENCLOSURE_IDS = (*CAGE_IDS, *HOLDER_IDS, *INTERFACE_IDS, *BRAKE_IDS)


def validate_enclosure_ids(names):
    names = list(names)
    if len(names) != len(set(names)) or set(names) != set(ENCLOSURE_IDS):
        raise ValueError("Incomplete or unapproved enclosure part roster; original source geometry is forbidden")


def validate_public_brake_identity(native_hash, catalog_hash):
    if native_hash != PUBLIC_BRAKE_SHA256 or catalog_hash != PUBLIC_CATALOG_SHA256:
        raise ValueError("Only the frozen, reviewed public brake input is allowed; private/original inputs are forbidden")
