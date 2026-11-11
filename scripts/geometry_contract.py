"""Independent world-coordinate expectations, without a FreeCAD dependency."""
import math
from itertools import product


def axis_point(point, axis):
    x, y, z = point
    if axis == "Z":
        return [x, y, z]
    if axis == "X":
        return [z, -y, x]
    if axis == "Y":
        return [x, z, -y]
    raise ValueError("Unknown public axis")


def axis_bounds(box, axis):
    corners = [axis_point(point, axis) for point in product(*zip(box[:3], box[3:]))]
    return [min(p[i] for p in corners) for i in range(3)] + [max(p[i] for p in corners) for i in range(3)]


def expected_instances(parts, axes):
    return {
        axis + "_" + part["id"]: {
            "bbox_mm": axis_bounds(part["bbox_mm"], axis),
            "center_of_mass_mm": axis_point(part["center_of_mass_mm"], axis),
            "volume_mm3": part["volume_mm3"], "solid_count": part["solid_count"],
            "is_reference": part["is_reference"],
        }
        for axis in axes for part in parts
    }


def require_pose(box, center, expected, name, bounds_tolerance=1e-6, center_tolerance=1e-6):
    bounds_error = max(abs(a - b) for a, b in zip(box, expected["bbox_mm"]))
    center_error = math.dist(center, expected["center_of_mass_mm"])
    if bounds_error > bounds_tolerance or center_error > center_tolerance:
        raise ValueError(f"Independent world pose mismatch: {name}; bbox={bounds_error:g} mm; centroid={center_error:g} mm")
    return bounds_error, center_error


def mesh_moments(vertices, faces):
    volumes, moments = [], [[], [], []]
    for i, j, k in faces:
        a, b, c = vertices[i], vertices[j], vertices[k]
        volume = (a[0]*(b[1]*c[2]-b[2]*c[1]) +
                  a[1]*(b[2]*c[0]-b[0]*c[2]) +
                  a[2]*(b[0]*c[1]-b[1]*c[0])) / 6
        volumes.append(volume)
        for dimension in range(3):
            moments[dimension].append(volume * (a[dimension] + b[dimension] + c[dimension]) / 4)
    signed_volume = math.fsum(volumes)
    if abs(signed_volume) < 1e-12:
        raise ValueError("Mesh has zero signed volume")
    return abs(signed_volume), [math.fsum(values) / signed_volume for values in moments]
