# -*- coding: utf-8 -*-
"""
3DXPYAM Complete Part Example — Parametric Ribbed Bracket (R2025x–R2027x)

Models a complete industrial mechanical part from an engineering drawing
using 100% iso-constrained (green) sketches, parametric Part Design features,
and automatic metrology self-verification:

    Dimensions (mm):
        - Back cylindrical boss : Ø30 (R15), straight length = 18, height = 30
        - Coaxial through-hole  : R7.5 (Ø15), full depth through boss
        - Base plate            : total length from boss axis = 60, width = 30,
                                  thickness = 9, front symmetric 9 x 9 mm chamfers
                                  (front tip flat = 12 mm; 9 + 12 + 9 = 30 mm)
        - Central triangular rib: thickness = 7 (symmetric), spanning from
                                  (X=18, Z=30) down to (X=60, Z=9)

    Exact analytical volume: 35,199.44 mm³ (35.20 cm³)

Requirements:
    - 3DEXPERIENCE CATIA running (any UI language: English, French, German, ...).
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

# Insert the repository root (NOT the inner pycatia3dx/ folder) so this example
# runs directly after `git clone` without shadowing Python stdlib modules.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from pycatia3dx import (
    CatConstraintMode,
    CatConstraintType,
    ThreeDExperience,
    measure_body,
)
from pycatia3dx.mode.reference import Reference

# ---------------------------------------------------------------------------
# Engineering Drawing Dimensions (mm)
# ---------------------------------------------------------------------------
BOSS_RADIUS = 15.0        # Ø30 outer cylindrical boss
HOLE_RADIUS = 7.5         # R7.5 (Ø15) coaxial through-hole
BOSS_FLAT_LEN = 18.0      # Straight length from boss center to front boss face
BOSS_HEIGHT = 30.0        # Total vertical height of boss tower
BASE_LEN = 60.0           # Length from boss center to front tip
BASE_THICKNESS = 9.0      # Base shelf vertical thickness
CHAMFER_X = 9.0           # Front corner chamfer setback in X
CHAMFER_Y = 9.0           # Front corner chamfer width in Y (9 + 12 + 9 = 30)
RIB_THICKNESS = 7.0       # Central triangular stiffener thickness


def analytical_volume_mm3() -> float:
    """Return the exact analytical volume (mm³) of the ribbed bracket."""
    half_w = BOSS_RADIUS
    semi_area = 0.5 * math.pi * (BOSS_RADIUS ** 2)
    base_area = semi_area + (BASE_LEN * (2.0 * half_w)) - (CHAMFER_X * CHAMFER_Y)
    v_base = base_area * BASE_THICKNESS

    boss_upper_area = semi_area + (BOSS_FLAT_LEN * (2.0 * half_w))
    v_boss_upper = boss_upper_area * (BOSS_HEIGHT - BASE_THICKNESS)

    rib_run = BASE_LEN - BOSS_FLAT_LEN
    rib_rise = BOSS_HEIGHT - BASE_THICKNESS
    v_rib = 0.5 * rib_run * rib_rise * RIB_THICKNESS

    v_hole = math.pi * (HOLE_RADIUS ** 2) * BOSS_HEIGHT
    return v_base + v_boss_upper + v_rib - v_hole


def _sketch_horizontal_vertical_axes(sk):
    ax = sk.absolute_axis
    return ax.horizontal_reference, ax.vertical_reference, ax.origin


def _detect_zx_axis_order(sk) -> tuple[bool, bool]:
    """
    Detect how CATIA maps 3D (X, Z) onto the 2D (H, V) axes of PlaneZX.

    In standard CATIA 3DEXPERIENCE right-handed Sketcher coordinates:
        PlaneZX has H = +Z, V = +X (so H x V = +Y).
    We read ``GetAbsoluteAxisData`` when available to stay 100% geometry-safe.
    """
    try:
        raw = sk.com_object
        # GetAbsoluteAxisData fills [Ox, Oy, Oz, Hx, Hy, Hz, Vx, Vy, Vz]
        data = raw.GetAbsoluteAxisData()
        if data and len(data) >= 9:
            hx, hy, hz = float(data[3]), float(data[4]), float(data[5])
            vx, vy, vz = float(data[6]), float(data[7]), float(data[8])
            # h_is_z: True when H aligns with Z axis; signs handle +/- flips
            h_is_z = abs(hz) > abs(hx)
            return h_is_z, (hz >= 0.0 if h_is_z else hx >= 0.0)
    except Exception:
        pass
    # Standard CATIA PlaneZX default: H = +Z, V = +X
    return True, True


def _add_distance_cst(csts, ref_a, ref_b, value: float, ctype=CatConstraintType.catCstTypeDistance):
    cst = csts.add_bi_elt_cst(ctype, ref_a, ref_b)
    cst.mode = CatConstraintMode.catCstModeDrivingDimension
    cst.dimension.value = float(value)
    return cst


def _add_radius_cst(csts, ref_circle, radius: float):
    cst = csts.add_mono_elt_cst(CatConstraintType.catCstTypeRadius, ref_circle)
    cst.mode = CatConstraintMode.catCstModeDrivingDimension
    cst.dimension.value = float(radius)
    return cst


def build_ribbed_bracket(name: str = "Ribbed_Bracket_3DXPYAM"):
    """Build the complete parametric ribbed bracket in 3DEXPERIENCE CATIA."""
    dx = ThreeDExperience()
    editor, part = dx.open_part_in_physical_product(reuse_empty=True, name=name)

    body = part.main_body
    sf = part.shape_factory
    ref = part.create_reference_from_object
    ref_xy = Reference(part.origin_elements.plane_xy.com_object)
    ref_zx = Reference(part.origin_elements.plane_zx.com_object)

    part.in_work_object = body

    # =========================================================================
    # 1. BASE PLATE (XY Plane, Z = 0 -> 9 mm)
    #    Back semicircle R15 at (0,0), sides Y = ±15, front 9x9 mm chamfers
    # =========================================================================
    sk_base = body.sketches.add(ref_xy)
    sk_base.name = "Sketch_Base_Profile"
    f2d = sk_base.open_edition()

    r = BOSS_RADIUS
    x_chamf = BASE_LEN - CHAMFER_X        # 51.0 mm
    y_tip = BOSS_RADIUS - CHAMFER_Y       #  6.0 mm (front flat = 12.0 mm)

    p_top_tan = f2d.create_point(0.0, r)
    p_bot_tan = f2d.create_point(0.0, -r)
    p_bot_ch = f2d.create_point(x_chamf, -r)
    p_bot_tip = f2d.create_point(BASE_LEN, -y_tip)
    p_top_tip = f2d.create_point(BASE_LEN, y_tip)
    p_top_ch = f2d.create_point(x_chamf, r)

    # Back semicircular arc centered at (0, 0), sweeping from +90° (0, +15) to +270° (0, -15) through (-15, 0)
    arc_base = f2d.create_circle(0.0, 0.0, r, math.pi / 2.0, 1.5 * math.pi)
    arc_base.start_point = p_top_tan
    arc_base.end_point = p_bot_tan

    l_bot = f2d.create_line(0.0, -r, x_chamf, -r)
    l_bot.start_point, l_bot.end_point = p_bot_tan, p_bot_ch

    l_ch_bot = f2d.create_line(x_chamf, -r, BASE_LEN, -y_tip)
    l_ch_bot.start_point, l_ch_bot.end_point = p_bot_ch, p_bot_tip

    l_front = f2d.create_line(BASE_LEN, -y_tip, BASE_LEN, y_tip)
    l_front.start_point, l_front.end_point = p_bot_tip, p_top_tip

    l_ch_top = f2d.create_line(BASE_LEN, y_tip, x_chamf, r)
    l_ch_top.start_point, l_ch_top.end_point = p_top_tip, p_top_ch

    l_top = f2d.create_line(x_chamf, r, 0.0, r)
    l_top.start_point, l_top.end_point = p_top_ch, p_top_tan

    # Iso-constrain base sketch (100% green)
    h_ax, v_ax, origin = _sketch_horizontal_vertical_axes(sk_base)
    csts = sk_base.constraints
    csts.add_bi_elt_cst(CatConstraintType.catCstTypeOn, ref(arc_base.center_point), ref(origin))
    _add_radius_cst(csts, ref(arc_base), r)
    csts.add_bi_elt_cst(CatConstraintType.catCstTypeOn, ref(p_top_tan), ref(v_ax))
    csts.add_bi_elt_cst(CatConstraintType.catCstTypeOn, ref(p_bot_tan), ref(v_ax))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(l_bot))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(l_top))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(l_front))
    _add_distance_cst(csts, ref(v_ax), ref(l_front), BASE_LEN)
    _add_distance_cst(csts, ref(p_bot_ch), ref(l_front), CHAMFER_X)
    _add_distance_cst(csts, ref(p_top_ch), ref(l_front), CHAMFER_X)
    _add_distance_cst(csts, ref(h_ax), ref(p_top_tip), y_tip)
    _add_distance_cst(csts, ref(h_ax), ref(p_bot_tip), y_tip)
    sk_base.close_edition()

    pad_base = sf.add_new_pad(sk_base, BASE_THICKNESS)
    pad_base.name = "Pad_Base_Plate"
    part.update()

    # =========================================================================
    # 2. CYLINDRICAL BOSS TOWER (XY Plane, Z = 0 -> 30 mm)
    #    Back semicircle R15 at (0,0) + straight section to X = 18 mm
    # =========================================================================
    sk_boss = body.sketches.add(ref_xy)
    sk_boss.name = "Sketch_Boss_Tower"
    f2d = sk_boss.open_edition()

    b_top_tan = f2d.create_point(0.0, r)
    b_bot_tan = f2d.create_point(0.0, -r)
    b_bot_fr = f2d.create_point(BOSS_FLAT_LEN, -r)
    b_top_fr = f2d.create_point(BOSS_FLAT_LEN, r)

    arc_boss = f2d.create_circle(0.0, 0.0, r, math.pi / 2.0, 1.5 * math.pi)
    arc_boss.start_point = b_top_tan
    arc_boss.end_point = b_bot_tan

    bl_bot = f2d.create_line(0.0, -r, BOSS_FLAT_LEN, -r)
    bl_bot.start_point, bl_bot.end_point = b_bot_tan, b_bot_fr

    bl_fr = f2d.create_line(BOSS_FLAT_LEN, -r, BOSS_FLAT_LEN, r)
    bl_fr.start_point, bl_fr.end_point = b_bot_fr, b_top_fr

    bl_top = f2d.create_line(BOSS_FLAT_LEN, r, 0.0, r)
    bl_top.start_point, bl_top.end_point = b_top_fr, b_top_tan

    h_ax, v_ax, origin = _sketch_horizontal_vertical_axes(sk_boss)
    csts = sk_boss.constraints
    csts.add_bi_elt_cst(CatConstraintType.catCstTypeOn, ref(arc_boss.center_point), ref(origin))
    _add_radius_cst(csts, ref(arc_boss), r)
    csts.add_bi_elt_cst(CatConstraintType.catCstTypeOn, ref(b_top_tan), ref(v_ax))
    csts.add_bi_elt_cst(CatConstraintType.catCstTypeOn, ref(b_bot_tan), ref(v_ax))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(bl_bot))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(bl_top))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(bl_fr))
    _add_distance_cst(csts, ref(v_ax), ref(bl_fr), BOSS_FLAT_LEN)
    sk_boss.close_edition()

    pad_boss = sf.add_new_pad(sk_boss, BOSS_HEIGHT)
    pad_boss.name = "Pad_Boss_Tower"
    part.update()

    # =========================================================================
    # 3. CENTRAL TRIANGULAR STIFFENER RIB (ZX Plane, Y = 0, symmetric ±3.5 mm)
    #    Right triangle connecting (X=18, Z=9), (X=60, Z=9), and (X=18, Z=30)
    # =========================================================================
    sk_rib = body.sketches.add(ref_zx)
    sk_rib.name = "Sketch_Central_Rib"
    h_is_z, _ = _detect_zx_axis_order(sk_rib)

    def _xz_to_2d(x_val: float, z_val: float) -> tuple[float, float]:
        # Standard CATIA PlaneZX maps (H, V) = (Z, X)
        return (z_val, x_val) if h_is_z else (x_val, z_val)

    f2d = sk_rib.open_edition()
    c1 = _xz_to_2d(BOSS_FLAT_LEN, BASE_THICKNESS)  # (X=18, Z=9)
    c2 = _xz_to_2d(BASE_LEN, BASE_THICKNESS)       # (X=60, Z=9)
    c3 = _xz_to_2d(BOSS_FLAT_LEN, BOSS_HEIGHT)     # (X=18, Z=30)

    rp1 = f2d.create_point(*c1)
    rp2 = f2d.create_point(*c2)
    rp3 = f2d.create_point(*c3)

    rl_base = f2d.create_line(*c1, *c2)
    rl_base.start_point, rl_base.end_point = rp1, rp2

    rl_hyp = f2d.create_line(*c2, *c3)
    rl_hyp.start_point, rl_hyp.end_point = rp2, rp3

    rl_back = f2d.create_line(*c3, *c1)
    rl_back.start_point, rl_back.end_point = rp3, rp1

    h_ax, v_ax, _ = _sketch_horizontal_vertical_axes(sk_rib)
    csts = sk_rib.constraints
    if h_is_z:
        # H = Z, V = X -> rl_base has constant Z (vertical in sketch), rl_back has constant X (horizontal in sketch)
        csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(rl_base))
        csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(rl_back))
        _add_distance_cst(csts, ref(v_ax), ref(rl_base), BASE_THICKNESS)
        _add_distance_cst(csts, ref(h_ax), ref(rl_back), BOSS_FLAT_LEN)
        _add_distance_cst(csts, ref(h_ax), ref(rp2), BASE_LEN)
        _add_distance_cst(csts, ref(v_ax), ref(rp3), BOSS_HEIGHT)
    else:
        csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(rl_base))
        csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(rl_back))
        _add_distance_cst(csts, ref(h_ax), ref(rl_base), BASE_THICKNESS)
        _add_distance_cst(csts, ref(v_ax), ref(rl_back), BOSS_FLAT_LEN)
        _add_distance_cst(csts, ref(v_ax), ref(rp2), BASE_LEN)
        _add_distance_cst(csts, ref(h_ax), ref(rp3), BOSS_HEIGHT)
    sk_rib.close_edition()

    pad_rib = sf.add_new_pad(sk_rib, RIB_THICKNESS / 2.0)
    pad_rib.is_symmetric = True
    pad_rib.name = "Pad_Central_Rib"
    part.update()

    # =========================================================================
    # 4. COAXIAL THROUGH-HOLE (XY Plane, R7.5 / Ø15 mm through full 30 mm boss)
    # =========================================================================
    sk_hole = body.sketches.add(ref_xy)
    sk_hole.name = "Sketch_Boss_Hole"
    f2d = sk_hole.open_edition()

    circ_hole = f2d.create_closed_circle(0.0, 0.0, HOLE_RADIUS)
    _, _, origin = _sketch_horizontal_vertical_axes(sk_hole)
    csts = sk_hole.constraints
    csts.add_bi_elt_cst(CatConstraintType.catCstTypeOn, ref(circ_hole.center_point), ref(origin))
    _add_radius_cst(csts, ref(circ_hole), HOLE_RADIUS)
    sk_hole.close_edition()

    pocket_hole = sf.add_new_pocket(sk_hole, BOSS_HEIGHT + 5.0)
    pocket_hole.is_symmetric = True
    pocket_hole.name = "Pocket_Boss_Through_Hole"
    part.update()

    # =========================================================================
    # 5. METROLOGY SELF-VERIFICATION AGAINST ANALYTICAL VOLUME
    # =========================================================================
    expected_vol = analytical_volume_mm3()
    try:
        measure_svc = editor.get_service("MeasureService")
        vol_mm3, area_mm2, cog = measure_body(measure_svc, body)
        err_pct = abs(vol_mm3 - expected_vol) / expected_vol * 100.0
        print(f"Built '{part.name}' successfully!")
        print(f"  Measured Volume  : {vol_mm3:,.2f} mm³ ({vol_mm3 / 1000.0:.2f} cm³)")
        print(f"  Analytical Volume: {expected_vol:,.2f} mm³ (delta: {err_pct:.3f}%)")
        print(f"  Surface Area     : {area_mm2:,.2f} mm²")
        print(f"  Center of Gravity: X={cog[0]:.2f}, Y={cog[1]:.2f}, Z={cog[2]:.2f} mm")
    except Exception as exc:
        print(f"Built '{part.name}' successfully (Analytical Volume = {expected_vol:,.2f} mm³; measure note: {exc})")

    return editor, part


if __name__ == "__main__":
    build_ribbed_bracket()
