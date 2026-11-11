"""Functional crosswalk from the measured 83-leaf reference roster, not source geometry."""

from enclosure_policy import ENCLOSURE_IDS


def source_coverage(joints):
    rows = {}

    def add(indices, family, targets, disposition, reason, axis=None):
        for index in indices:
            if index in rows:
                raise ValueError("Duplicate reference-leaf disposition")
            rows[index] = {
                "source_leaf":"Part__Feature"+(f"{index:03d}" if index else ""),
                "source_family":family,"reference_axis":axis,"target_parts":targets,
                "disposition":disposition,"reason":reason,
                "original_geometry_redistributed":False,"original_interchangeability_claimed":False,
            }

    motor_note = ("Four geometric leaves represent one external motor assembly per axis, not four purchased motors. "
                  "Only independently generated required interfaces are displayed. Original Z motor CAD/retaining-ring "
                  "common volume 29.606056754452105 mm3 remains unresolved; actual hardware is unverified/blocked.")
    for start, axis in ((0,"Y"),(4,"X"),(8,"Z")):
        add(range(start,start+4),"external motor geometry",
            [f"E_REF_MOTOR_{axis}",f"E_REF_SHAFT_{axis}"],"reference-only/fit-blocked",motor_note,axis)
        for index in range(start,start+4):
            rows[index]["external_assembly_group"] = "motor-"+axis
    octants = ("NNP","PNP","PNN","NNN","NPP","PPP","PPN","NPN")
    for index, octant in enumerate(octants,12):
        add([index],"corner",[f"E_CORNER_{octant}",f"E_CORNER_CAP_{octant}",f"E_CAP_SCREW_{octant}"],
            "independent-replacement","Separate internal connection node and real external cover; no traced original contour.")
    for index, axis in ((20,"Y"),(21,"X"),(22,"Z")):
        add([index],"motor-side frame",[f"E_FRAME_MOTOR_{axis}"],"independent-replacement",
            "New PCD126 pad/seat geometry within 138 mm exterior. Source PCD135 is 4.5 mm radially different.",axis)
    for index, axis in ((23,"Y"),(24,"X"),(25,"Z")):
        add([index],"primary motor support",[axis+"_CARRIER",f"E_REF_MOTOR_{axis}"],
            "nominal-functional-replacement/motor-fit-blocked",
            "C08 carrier-to-required-motor interface and carrier-to-post fastening paths are explicit. "
            "This does not resolve source motor CAD fit or qualify actual motor support.",axis)
    secondary = ((26,"Y",2),(27,"Y",3),(28,"Y",0),(29,"Y",1),
                 (30,"X",0),(31,"X",3),(32,"X",2),(33,"X",1),
                 (34,"Z",3),(35,"Z",2),(36,"Z",1),(37,"Z",0))
    for index, axis, post in secondary:
        add([index],"secondary motor support",
            [f"{axis}_POST_{post}",axis+"_CARRIER",f"E_FRAME_MOTOR_{axis}",
             f"{axis}_FRAME_BOLT_{post}",f"{axis}_FRAME_NUT_{post}"],
            "nominal-functional-replacement",
            "C08 stepped post connects carrier to the new PCD126 frame; axes, bearing faces and through-nut "
            "stack are checked. Original support contours, 18 mm height and PCD135 are not reproduced.",axis)
    for index, axis in ((38,"Y"),(41,"X"),(43,"Z")):
        add([index],"hub",[axis+"_HUB",axis+"_HUB_FACE"],"authored-c08-replacement",
            "Existing published independent split hub. Not the source hub; real shaft fit remains unqualified.",axis)
    for index, axis in ((39,"Y"),(40,"X"),(42,"Z")):
        add([index],"wheel",[axis+"_REF_WHEEL"],"independent-reference",
            "New plain annulus with C08 interface holes, not original wheel/spokes. Original inertia and balance are not reproduced.",axis)
    rim = [f"Y_{kind}_{i}" for i in range(8) for kind in ("RIM_BOLT","RIM_NUT")]
    add(range(44,53),"illustrated M4 rim/weight screws",rim,"superseded-nominal-pattern",
        "Nine nonuniform Y-axis source leaves are not a procurement quantity. The independent reference uses eight "
        "equally spaced screw/nut pairs per axis; no eccentric-mass or inertia equivalence.", "Y")
    add([53,54,55],"illustrated M4 washer/two nuts",rim,"superseded-nominal-stack",
        "Original washer/double-nut stack is omitted. New flat-head/annulus/single-nut joints explicitly replace "
        "this example; no floating or duplicate source hardware is retained.","Y")
    add([56,57,58],"illustrated support screw/washer/nut",
        ["Y_CARRIER",*[f"Y_FRAME_BOLT_{i}" for i in range(4)],*[f"Y_FRAME_NUT_{i}" for i in range(4)]],
        "superseded-nominal-stack","The new carrier/post/frame through-nut chains replace the original support example, not its contour or hardware count.","Y")
    add([59,60],"illustrated motor screw/washer",
        [f"Y_MOTOR_INTERFACE_BOLT_{i}" for i in range(3)]+["E_REF_MOTOR_Y","Y_CARRIER"],
        "reference-only/fit-blocked","Nominal C08 face screws seat directly in the carrier and a new required-interface receiver. Actual motor/washer adoption is not authorized.","Y")
    add(range(61,65),"illustrated M3 hub screws",
        ["Y_HUB","Y_HUB_FACE",*[f"Y_HUB_CONNECT_BOLT_{i}" for i in range(3)]],
        "superseded-nominal-stack","New three-screw split-hub arrangement replaces the original four-screw example; original r8 pattern is not claimed interchangeable.","Y")
    add([65],"illustrated frame/support screw",
        ["E_FRAME_MOTOR_Y",*[f"Y_FRAME_BOLT_{i}" for i in range(4)]],
        "superseded-nominal-stack","New PCD126 frame/post/carrier fastening instead of the original r67.5 example.","Y")
    corner_screws = ((66,"NNP","Y"),(67,"PNP","Y"),(68,"PNN","Y"),(69,"NNN","Y"),
                     (70,"NPP","X"),(71,"NNP","X"),(72,"NNN","X"),(73,"NPN","X"),
                     (74,"NNN","Z"),(75,"PNN","Z"),(76,"PPN","Z"),(77,"NPN","Z"))
    for index, octant, axis in corner_screws:
        add([index],"negative-face corner screw",[f"E_FRAME_SCREW_{octant}_{axis}"],
            "independent-replacement","New nominal M3 receiver and countersink. Twelve additional positive-face connections close all 24 frame ends.",axis)
    for index, axis in ((78,"Y"),(79,"Z"),(80,"X")):
        add([index],"board-side frame",[f"E_FRAME_BOARD_{axis}"],"independent-replacement",
            "New primitive frame/web and PCB/MPU seats. Inner face 62.8 mm is explicitly 2 mm inward from the source 64.8 mm datum.",axis)
    for index, kind in ((81,"MPU"),(82,"PCB")):
        targets = [name for name in ENCLOSURE_IDS if name.startswith((f"E_HOLDER_{kind}",f"E_HOLDER_FIX_{kind}_",
                   f"E_REF_BOARD_{kind}",f"E_SPACER_{kind}_",f"E_WASHER_{kind}_",f"E_BOARD_SCREW_{kind}_"))]
        add([index],kind+" holder",targets,"independent-replacement",
            "New ribs/feet/bosses and complete nominal screw/washer/board/spacer/receiver stack. Measured source datums "
            "are separated from assumed thicknesses and unverified component/connector clearances.")
    if set(rows) != set(range(83)):
        raise ValueError("Not all 83 measured source leaves have a disposition")
    allowed = set(ENCLOSURE_IDS)
    for row in rows.values():
        if not row["target_parts"] or any(name not in allowed for name in row["target_parts"]):
            raise ValueError("Coverage points to an absent new part")
        targets = set(row["target_parts"])
        row["target_joints"] = [
            joint["id"] for joint in joints if targets.intersection(
                [joint["fastener"],*joint.get("stack",[joint["clamped_part"],joint["receiver"]])])
        ]
    return {
        "schema":"independent-enclosure-coverage-v1","source_leaf_count":83,"source_housing_holder_count":31,
        "source_wheel_count":3,"source_motor_geometry_leaves":12,"source_external_motor_assemblies":3,
        "source_hub_leaves":3,"source_hardware_leaves":34,"user_selected_variant":False,
        "working_variant":"Pico provisional, coordinator assumption","original_shapes_copied":0,
        "rows":[rows[index] for index in range(83)],"model_counts_are_not_procurement_quantities":True,
        "additional_new_parts":"External covers/retainers, positive-face screws, explicit board fasteners/spacers and C08 brake parts are separately counted by exact IDs.",
        "battery_and_harness_limit":"No confirmed battery outline or harness routes/strain relief were supplied by the 83-leaf source. The old 176 mm illustration's battery is not adopted. Actual battery/harness retention is unresolved, not modeled as complete.",
        "reference_motor_CAD_nominal_fit":"failed","actual_hardware_compatibility":"unverified/blocked",
        "whole_fit":False,"build_ready":False,"physical_ready":False,
    }
