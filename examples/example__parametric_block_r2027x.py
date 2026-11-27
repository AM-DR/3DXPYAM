# -*- coding: utf-8 -*-
"""
3DXPYAM Core Example — Parametric Prismatic Block (R2025x–R2027x)

Demonstrates the core mechanical CAD workflow in 3DXPYAM:
  1. Open/create a 3D Part inside a Physical Product (R2027x-safe)
  2. Build an iso-constrained (green) centered rectangular sketch & Pad (60 x 40 x 20 mm)
  3. Apply symmetric 4x4 mm corner chamfers using CSO-safe topology snapshotting
  4. Drill a centered through-hole (Ø12 mm) with an iso-constrained positioning sketch
  5. Link dimensions via validated Knowledgeware formulas
  6. Measure volume, surface area, and center of gravity
"""

from pathlib import Path
import sys

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from pycatia3dx import (
    CATMeasurableType,
    CatChamferMode,
    CatChamferOrientation,
    CatChamferPropagation,
    CatConstraintMode,
    CatConstraintType,
    CatHoleType,
    CatLimitMode,
    ThreeDExperience,
    add_formula,
    constrain_hole_origin,
    measure_body,
    param_name_for_relation,
    snapshot_topology_refs,
)
from pycatia3dx.mode.reference import Reference


def build_parametric_block():
    dx = ThreeDExperience()
    editor, part = dx.open_part_in_physical_product()

    body = part.main_body
    sf = part.shape_factory
    sel = editor.selection
    measurable_svc = editor.get_service("MeasurableService")
    measure_svc = editor.get_service("MeasureService")

    ref_xy = Reference(part.origin_elements.plane_xy.com_object)
    ref = part.create_reference_from_object

    # 1. Centered 60 x 40 mm iso-constrained sketch
    part.in_work_object = body
    sk = body.sketches.add(ref_xy)
    f2d = sk.open_edition()
    pts = [(-30.0, -20.0), (30.0, -20.0), (30.0, 20.0), (-30.0, 20.0)]
    verts = [f2d.create_point(x, y) for x, y in pts]
    lines = []
    for i in range(4):
        ln = f2d.create_line(*pts[i], *pts[(i + 1) % 4])
        ln.start_point, ln.end_point = verts[i], verts[(i + 1) % 4]
        lines.append(ln)

    ax = sk.absolute_axis
    csts = sk.constraints
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(lines[0]))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(lines[2]))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(lines[1]))
    csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(lines[3]))
    csts.add_tri_elt_cst(CatConstraintType.catCstTypeSymmetry, ref(lines[1]), ref(lines[3]), ref(ax.vertical_reference))
    csts.add_tri_elt_cst(CatConstraintType.catCstTypeSymmetry, ref(lines[0]), ref(lines[2]), ref(ax.horizontal_reference))
    c_len = csts.add_mono_elt_cst(CatConstraintType.catCstTypeLength, ref(lines[0]))
    c_len.mode = CatConstraintMode.catCstModeDrivingDimension
    c_wid = csts.add_mono_elt_cst(CatConstraintType.catCstTypeLength, ref(lines[1]))
    c_wid.mode = CatConstraintMode.catCstModeDrivingDimension
    sk.close_edition()

    # 2. Pad (height = width / 2 = 20 mm)
    pad = sf.add_new_pad(sk, 20.0)
    add_formula(part, pad.first_limit.dimension, f"({param_name_for_relation(part, c_wid.dimension)}) / 2")
    part.update()

    # 3. Four vertical corner chamfers (4 x 4 mm)
    edge_refs = snapshot_topology_refs(sel, pad, "Topology.Edge,sel")
    corner_edges = []
    for rf in edge_refs:
        try:
            ml = measurable_svc.get_measurable(rf, CATMeasurableType.CAAMeasurableLine)
            ox, oy, _ = ml.get_origin()
            _, _, dz = ml.get_direction()
            if abs(dz) > 0.99 and abs(abs(ox) - 30.0) < 0.2 and abs(abs(oy) - 20.0) < 0.2:
                corner_edges.append(rf)
        except Exception:
            continue

    if corner_edges:
        ch = sf.add_new_chamfer(
            corner_edges[0],
            CatChamferPropagation.catMinimalChamfer,
            CatChamferMode.catTwoLengthChamfer,
            CatChamferOrientation.catNoReverseChamfer,
            4.0,
            4.0,
        )
        for edge in corner_edges[1:]:
            ch.add_element_to_chamfer(edge)
        add_formula(part, ch.length2, param_name_for_relation(part, ch.length1))
        part.update()

    # 4. Centered Ø12 through-hole on top face (Z = 20 mm)
    face_refs = snapshot_topology_refs(sel, body, "Topology.Face,sel")
    top_face = ref_xy
    for rf in face_refs:
        try:
            ms = measurable_svc.get_measurable(rf, CATMeasurableType.CAAMeasurableSurface)
            if abs(ms.get_c_of_g()[2] - 20.0) < 0.1:
                top_face = rf
                break
        except Exception:
            continue

    vol_before, _, _ = measure_body(measure_svc, body)
    hole = sf.add_new_hole_from_point(0.0, 0.0, 20.0, top_face, 25.0)
    hole.type = CatHoleType.catSimpleHole
    hole.bottom_limit.limit_mode = CatLimitMode.catUpToLastLimit
    hole.diameter.value = 12.0
    constrain_hole_origin(part, hole)
    part.update()
    vol_after, _, _ = measure_body(measure_svc, body)
    if abs(vol_after - vol_before) < 10.0:
        hole.reverse()
        part.update()

    # 5. Metrology readout
    vol_mm3, area_mm2, cog = measure_body(measure_svc, body)
    print(f"SUCCESS ({part.name}) | Volume = {vol_mm3:,.2f} mm³ | Area = {area_mm2:,.2f} mm² | COG = {cog}")


if __name__ == "__main__":
    build_parametric_block()
