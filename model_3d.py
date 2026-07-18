"""
JARVIS 3D Modeling Engine
Generates 3D printable STL files from natural language descriptions.
Uses trimesh for mesh operations.
"""
import trimesh
import numpy as np
import uuid
import os
import json
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent.parent / "3d_models"
OUTPUT_DIR.mkdir(exist_ok=True)

MODELS_DB = {}  # id -> {name, description, path, created, params}


def _save_mesh(mesh, name, description=""):
    """Export mesh to STL and register in DB."""
    model_id = str(uuid.uuid4())[:8]
    stl_path = OUTPUT_DIR / f"{model_id}_{name}.stl"
    mesh.export(str(stl_path))
    info = {
        "id": model_id,
        "name": name,
        "description": description,
        "path": str(stl_path),
        "filename": stl_path.name,
        "created": datetime.now().isoformat(),
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
    }
    MODELS_DB[model_id] = info
    return info


def make_box(width=50, height=50, depth=50, wall=2, hollow=False):
    """Create a box. If hollow, creates a box with walls of given thickness."""
    if hollow:
        outer = trimesh.creation.box(extents=[width, height, depth])
        inner = trimesh.creation.box(extents=[width - 2*wall, height - 2*wall, depth - 2*wall])
        mesh = outer.difference(inner)
    else:
        mesh = trimesh.creation.box(extents=[width, height, depth])
    return _save_mesh(mesh, "box", f"{width}x{height}x{depth}mm box")


def make_cylinder(radius=25, height=50, wall=0, segments=64):
    """Create a cylinder. If wall > 0, creates a tube."""
    if wall > 0:
        outer = trimesh.creation.cylinder(radius=radius, height=height, sections=segments)
        inner = trimesh.creation.cylinder(radius=radius - wall, height=height + 0.1, sections=segments)
        mesh = outer.difference(inner)
    else:
        mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=segments)
    return _save_mesh(mesh, "cylinder", f"r{radius}x{height}mm cylinder")


def make_sphere(radius=25):
    """Create a sphere."""
    mesh = trimesh.creation.icosphere(subdivisions=3, radius=radius)
    return _save_mesh(mesh, "sphere", f"r{radius}mm sphere")


def make_phone_holder(phone_w=80, phone_h=160, phone_d=10, wall=3, lip=8, angle=60):
    """Create a phone stand/holder with angled back support."""
    base_w = phone_w + 2 * wall + 10
    base_d = phone_d + 2 * wall + 20
    base_h = wall

    # Base plate
    base = trimesh.creation.box(extents=[base_w, base_d, base_h])
    base.apply_translation([0, 0, base_h / 2])

    # Back support (angled)
    back_h = phone_h * 0.7
    back_w = phone_w + 2 * wall
    back_d = wall
    back = trimesh.creation.box(extents=[back_w, back_d, back_h])
    rad = np.radians(angle)
    back.apply_transform(trimesh.transformations.rotation_matrix(rad, [1, 0, 0]))
    back.apply_translation([0, -base_d/2 + back_d, back_h * 0.4])

    # Bottom lip to hold phone
    lip_w = phone_w + 2 * wall
    lip_h = lip
    lip_d = wall + 5
    lip_mesh = trimesh.creation.box(extents=[lip_w, lip_d, lip_h])
    lip_mesh.apply_translation([0, base_d/2 - lip_d/2, lip_h/2])

    # Side walls
    side_h = phone_h * 0.3
    side_d = wall
    side1 = trimesh.creation.box(extents=[wall, base_d, side_h])
    side1.apply_translation([-(phone_w/2 + wall/2), 0, base_h + side_h/2])
    side2 = trimesh.creation.box(extents=[wall, base_d, side_h])
    side2.apply_translation([(phone_w/2 + wall/2), 0, base_h + side_h/2])

    mesh = trimesh.util.concatenate([base, back, lip_mesh, side1, side2])
    return _save_mesh(mesh, "phone_holder", f"Phone holder {phone_w}x{phone_h}mm")


def make_enclosure(width=60, height=40, depth=80, wall=2.5, hole_r=3, mount_r=4):
    """Create an electronics enclosure with mounting posts and screw holes."""
    # Outer shell
    outer = trimesh.creation.box(extents=[width, depth, height])
    outer.apply_translation([0, 0, height/2])

    # Inner cavity
    inner = trimesh.creation.box(extents=[width - 2*wall, depth - 2*wall, height - wall])
    inner.apply_translation([0, 0, height/2 + wall/2])

    shell = outer.difference(inner)

    # Mounting posts in corners
    posts = []
    inset = mount_r + 2
    for x in [-(width/2 - inset), (width/2 - inset)]:
        for y in [-(depth/2 - inset), (depth/2 - inset)]:
            post = trimesh.creation.cylinder(radius=mount_r, height=height - wall)
            post.apply_translation([x, y, (height - wall)/2 + wall])
            # Screw hole
            hole = trimesh.creation.cylinder(radius=hole_r, height=height + 1)
            hole.apply_translation([x, y, height/2])
            post = post.difference(hole)
            posts.append(post)

    mesh = trimesh.util.concatenate([shell] + posts)
    return _save_mesh(mesh, "enclosure", f"{width}x{depth}x{height}mm enclosure")


def make_gear(radius=25, teeth=12, tooth_depth=4, thickness=6):
    """Create a gear-like shape using cylinder + teeth as boxes."""
    # Main body
    mesh = trimesh.creation.cylinder(radius=radius, height=thickness, sections=64)

    # Add teeth around the perimeter
    tooth_w = 2 * np.pi * radius / (teeth * 3)
    tooth_h = tooth_depth
    for i in range(teeth):
        angle = 2 * np.pi * i / teeth
        tooth = trimesh.creation.box(extents=[tooth_w, tooth_h, thickness])
        tooth.apply_translation([
            (radius + tooth_h/2) * np.cos(angle),
            (radius + tooth_h/2) * np.sin(angle),
            0
        ])
        tooth.apply_transform(trimesh.transformations.rotation_matrix(angle, [0, 0, 1]))
        tooth.apply_translation([
            (radius + tooth_h/2) * np.cos(angle),
            (radius + tooth_h/2) * np.sin(angle),
            0
        ])
        mesh = trimesh.util.concatenate([mesh, tooth])

    return _save_mesh(mesh, "gear", f"{teeth}-tooth gear r{radius}mm")


def make_bracket(length=60, width=30, thickness=5, hole_r=3):
    """Create an L-bracket with mounting holes."""
    # Vertical part
    v = trimesh.creation.box(extents=[width, thickness, length])
    v.apply_translation([0, 0, length/2])

    # Horizontal part
    h = trimesh.creation.box(extents=[width, length, thickness])
    h.apply_translation([0, length/2 - thickness/2, thickness/2])

    mesh = trimesh.util.concatenate([v, h])

    # Add holes
    for z in [length * 0.25, length * 0.75]:
        hole1 = trimesh.creation.cylinder(radius=hole_r, height=thickness + 1)
        hole1.apply_translation([0, 0, z])
        mesh = mesh.difference(hole1)

    for y in [length * 0.25, length * 0.75]:
        hole2 = trimesh.creation.cylinder(radius=hole_r, height=thickness + 1)
        hole2.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0]))
        hole2.apply_translation([0, y, thickness/2])
        mesh = mesh.difference(hole2)

    return _save_mesh(mesh, "bracket", f"L-bracket {length}x{width}mm")


def make_hook(width=20, height=40, depth=15, wall=4, hole_r=3):
    """Create a wall-mountable hook."""
    # Back plate
    plate = trimesh.creation.box(extents=[width, wall, height])
    plate.apply_translation([0, 0, height/2])

    # Hook arm
    arm_r = wall / 2
    arm = trimesh.creation.cylinder(radius=arm_r, height=depth)
    arm.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0]))
    arm.apply_translation([0, wall/2 + depth/2, height * 0.6])

    # Hook curve (half torus approximation with boxes)
    curve = trimesh.creation.cylinder(radius=arm_r, height=wall)
    curve.apply_translation([0, wall/2 + depth, height * 0.6 - arm_r])

    mesh = trimesh.util.concatenate([plate, arm, curve])

    # Mounting hole
    hole = trimesh.creation.cylinder(radius=hole_r, height=wall + 1)
    hole.apply_translation([0, 0, height * 0.85])
    mesh = mesh.difference(hole)

    return _save_mesh(mesh, "hook", f"Wall hook {width}x{height}mm")


def make_raspberry_pi_case(model="3b", wall=2.5):
    """Create a case for Raspberry Pi."""
    sizes = {
        "zero": (65, 30, 5),
        "3b": (85, 56, 16),
        "4b": (85, 56, 16),
        "5": (85, 56, 16),
    }
    w, d, h = sizes.get(model, sizes["4b"])
    return make_enclosure(w, h, d, wall=wall)


def make_arduino_case(wall=2.5):
    """Create an Arduino Uno case."""
    return make_enclosure(70, 18, 55, wall=wall)


def make_servo_bracket(servo_w=40, servo_h=35, servo_d=20, wall=3):
    """Create a bracket to mount a servo motor."""
    bracket_w = servo_w + 2 * wall + 10
    bracket_h = servo_h + 2 * wall
    bracket_d = servo_d + wall

    # Base
    base = trimesh.creation.box(extents=[bracket_w, bracket_d, wall])
    base.apply_translation([0, 0, wall/2])

    # Side walls
    s1 = trimesh.creation.box(extents=[wall, bracket_d, bracket_h])
    s1.apply_translation([-(servo_w/2 + wall/2), 0, wall + bracket_h/2])
    s2 = trimesh.creation.box(extents=[wall, bracket_d, bracket_h])
    s2.apply_translation([(servo_w/2 + wall/2), 0, wall + bracket_h/2])

    # Bottom support
    bottom = trimesh.creation.box(extents=[servo_w, bracket_d, wall])
    bottom.apply_translation([0, 0, wall + wall/2])

    mesh = trimesh.util.concatenate([base, s1, s2, bottom])
    return _save_mesh(mesh, "servo_bracket", f"Servo bracket {servo_w}x{servo_h}mm")


def make_cable_clip(diameter=5, width=15, wall=2):
    """Create a cable management clip."""
    outer_r = diameter/2 + wall
    inner_r = diameter/2

    # Ring
    outer = trimesh.creation.cylinder(radius=outer_r, height=width)
    outer.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0]))
    inner = trimesh.creation.cylinder(radius=inner_r, height=width + 0.1)
    inner.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0]))
    ring = outer.difference(inner)

    # Mount tab
    tab = trimesh.creation.box(extents=[width, outer_r * 2, outer_r + 5])
    tab.apply_translation([0, 0, -outer_r/2])

    mesh = trimesh.util.concatenate([ring, tab])
    return _save_mesh(mesh, "cable_clip", f"Cable clip {diameter}mm")


def make_standoff(height=20, outer_r=4, inner_r=1.5):
    """Create a PCB standoff/insert."""
    outer = trimesh.creation.cylinder(radius=outer_r, height=height, sections=32)
    inner = trimesh.creation.cylinder(radius=inner_r, height=height + 0.1, sections=32)
    mesh = outer.difference(inner)
    return _save_mesh(mesh, "standoff", f"Standoff h{height}mm")


def make_vent_grille(width=60, height=40, slot_w=2, slot_h=30, gap=3):
    """Create a ventilation grille."""
    mesh_parts = []
    n_slots = int(width / (slot_w + gap))
    total_w = n_slots * (slot_w + gap) - gap
    start_x = -total_w / 2

    for i in range(n_slots):
        x = start_x + i * (slot_w + gap) + slot_w / 2
        slot = trimesh.creation.box(extents=[slot_w, 4, slot_h])
        slot.apply_translation([x, 0, height/2])
        mesh_parts.append(slot)

    if mesh_parts:
        mesh = trimesh.util.concatenate(mesh_parts)
    else:
        mesh = trimesh.creation.box(extents=[width, 4, height])

    return _save_mesh(mesh, "vent", f"Vent grille {width}x{height}mm")


def make_custom(parametric_desc):
    """
    Parse a natural language description and generate a 3D model.
    Supports: box, cylinder, sphere, phone_holder, enclosure, gear, bracket, hook,
    servo_bracket, cable_clip, standoff, vent, arduino_case, raspberry_pi_case.
    """
    desc = parametric_desc.lower().strip()

    # Phone holder
    if any(w in desc for w in ["phone", "phone holder", "phone stand", "phone case"]):
        w = _extract_num(desc, "wide", 80)
        h = _extract_num(desc, "high", 160)
        return make_phone_holder(phone_w=w, phone_h=h)

    # Enclosure / case
    if any(w in desc for w in ["enclosure", "case", "box with", "housing"]):
        if "arduino" in desc:
            return make_arduino_case()
        if "raspberry" in desc or "rpi" in desc:
            model = "4b"
            for m in ["zero", "3b", "4b", "5"]:
                if m in desc:
                    model = m
                    break
            return make_raspberry_pi_case(model)
        w = _extract_num(desc, "wide", 60)
        d = _extract_num(desc, "deep", 80)
        h = _extract_num(desc, "high", 40)
        return make_enclosure(w, h, d)

    # Gear
    if "gear" in desc:
        teeth = int(_extract_num(desc, "tooth", 12))
        r = _extract_num(desc, "radius", 25)
        return make_gear(radius=r, teeth=teeth)

    # Bracket
    if "bracket" in desc or "l-bracket" in desc:
        l = _extract_num(desc, "long", 60)
        w = _extract_num(desc, "wide", 30)
        return make_bracket(length=l, width=w)

    # Hook
    if "hook" in desc:
        return make_hook()

    # Servo bracket
    if "servo" in desc:
        return make_servo_bracket()

    # Cable clip
    if "cable" in desc or "clip" in desc:
        d = _extract_num(desc, "diameter", 5)
        return make_cable_clip(diameter=d)

    # Standoff
    if "standoff" in desc:
        h = _extract_num(desc, "high", 20)
        return make_standoff(height=h)

    # Vent
    if "vent" in desc or "grille" in desc or "ventilation" in desc:
        return make_vent_grille(60, 40)

    # Cylinder
    if "cylinder" in desc or "tube" in desc or "pipe" in desc:
        r = _extract_num(desc, "radius", 25)
        h = _extract_num(desc, "high", 50)
        wall = _extract_num(desc, "wall", 0)
        return make_cylinder(radius=r, height=h, wall=wall)

    # Sphere
    if "sphere" in desc or "ball" in desc:
        r = _extract_num(desc, "radius", 25)
        return make_sphere(radius=r)

    # Default: box
    w = _extract_num(desc, "wide", 50)
    h = _extract_num(desc, "high", 50)
    d = _extract_num(desc, "deep", 50)
    hollow = "hollow" in desc
    wall = _extract_num(desc, "wall", 2)
    return make_box(width=w, height=h, depth=d, wall=wall, hollow=hollow)


def _extract_num(text, keyword, default):
    """Extract a number near a keyword from text."""
    import re
    words = text.split()
    for i, w in enumerate(words):
        if keyword in w.lower():
            # Check next word
            if i + 1 < len(words):
                nums = re.findall(r'[\d.]+', words[i + 1])
                if nums:
                    return float(nums[0])
            # Check same word for embedded numbers
            nums = re.findall(r'[\d.]+', w)
            if nums:
                return float(nums[0])
    return default


def list_models():
    """List all generated models."""
    return list(MODELS_DB.values())


def get_model(model_id):
    """Get model info by ID."""
    return MODELS_DB.get(model_id)


def delete_model(model_id):
    """Delete a model."""
    info = MODELS_DB.pop(model_id, None)
    if info and os.path.exists(info["path"]):
        os.unlink(info["path"])
    return info is not None
