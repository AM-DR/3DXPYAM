"""
Core Mechanical CAD Helpers for 3DXPYAM.

Provides safe, release-aware helpers for the most common 3DEXPERIENCE CATIA
Part Design & Sketcher automation workflows (tested on R2025x–R2027x):

- :func:`open_part_in_physical_product`: creates or reuses an empty ``3D Shape``
  nested inside a ``Physical Product`` (handles R2027x+ ``release >= 429`` where
  ``StartCommand("3D Part")`` is no longer available from the Welcome Page).
- :func:`param_name_for_relation` / :func:`add_formula`: safely creates
  Knowledgeware formulas using ``GetNameToUseInRelation`` (properly backticks
  names with spaces such as ``Geometrical Set.1``) and validates non-empty values.
- :func:`snapshot_topology_refs`: snapshots ``Selection.Search`` references into a
  plain Python list *before* calling ``MeasurableService`` (which can clear the
  active selection mid-loop inside Physical Product editors).
- :func:`constrain_hole_origin`: iso-constrains a native CATIA ``Hole`` positioning
  sketch point onto ``AbsoluteAxis.Origin`` (green sketch).
- :func:`measure_body`: returns ``(volume_mm3, area_mm2, (cx, cy, cz))`` in mm.
"""
from __future__ import annotations

import time
from typing import Any

from pycatia3dx.ecosystem.universal_client import extract_part_from_editor
from pycatia3dx.mmr_automation_interfaces.enums import CatConstraintType
from pycatia3dx.mmr_automation_interfaces.part import Part
from pycatia3dx.mode.reference import Reference
from pycatia3dx.product_structure_client.vpm_instance import VPMInstance
from pycatia3dx.product_structure_client.vpm_rep_instance import VPMRepInstance
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService


def _is_empty_part(part: Part) -> bool:
    try:
        return part.main_body.shapes.count == 0
    except Exception:
        return False


def open_part_in_physical_product(dx: Any, app: Any | None = None, *, reuse_empty: bool = True):
    """
    Create (or reuse an empty) ``3D Shape`` nested inside a ``Physical Product``.

    Works seamlessly across 3DEXPERIENCE R2025x, R2026x, and R2027x (``release >= 429``).

    Returns:
        Tuple ``(editor, part)``.
    """
    app = app or dx.catia

    # 1. Reuse an already-open empty 3D Part inside a Physical Product if requested
    if reuse_empty:
        try:
            ed_act = app.active_editor
            ps = PLMProductService(ed_act.get_service("PLMProductService").com_object)
            ro = ps.root_occurrence
            vr = ro.reference_root_occurrence_of
            if vr.rep_instances.count > 0:
                p_act = extract_part_from_editor(ed_act)
                if p_act is not None and _is_empty_part(p_act):
                    return ed_act, p_act
            for i in range(1, vr.instances.count + 1):
                inst = VPMInstance(vr.instances.item(i).com_object)
                ref_child = inst.reference_instance_of
                if ref_child.rep_instances.count > 0:
                    ri = VPMRepInstance(ref_child.rep_instances.item(1).com_object)
                    p_child = Part(ri.reference_instance_of.get_item("Part").com_object)
                    if _is_empty_part(p_child):
                        return ed_act, p_child
        except Exception:
            pass

    # 2. Check if active editor is an existing Physical Product — insert a new 3D Part
    try:
        ed_cur = app.active_editor
        ps_cur = PLMProductService(ed_cur.get_service("PLMProductService").com_object)
        ro_cur = ps_cur.root_occurrence
        vr_cur = ro_cur.reference_root_occurrence_of
        before_cnt = vr_cur.instances.count
        sel_cur = ed_cur.selection
        sel_cur.clear()
        sel_cur.add(ro_cur)
        app.start_command("3D Part")
        t0 = time.time()
        while time.time() - t0 < 20.0:
            time.sleep(0.4)
            if vr_cur.instances.count > before_cnt:
                inst = VPMInstance(vr_cur.instances.item(vr_cur.instances.count).com_object)
                ref_child = inst.reference_instance_of
                if ref_child.rep_instances.count > 0:
                    ri = VPMRepInstance(ref_child.rep_instances.item(1).com_object)
                    sel_cur.clear()
                    return ed_cur, Part(ri.reference_instance_of.get_item("Part").com_object)
        sel_cur.clear()
    except Exception:
        pass

    # 3. Create a brand-new Physical Product + 3D Part (R2027x-safe)
    rel = 0
    try:
        rel = int(app.system_configuration.release)
    except Exception:
        pass

    prev_editors = set()
    try:
        for i in range(1, app.editors.count + 1):
            prev_editors.add(app.editors.item(i).com_object.Name)
    except Exception:
        pass

    cmd_init = "Physical Product" if rel >= 429 else "3D Part"
    try:
        app.start_command(cmd_init)
    except Exception:
        pass

    t0 = time.time()
    ed_new = None
    while time.time() - t0 < 25.0:
        time.sleep(0.5)
        try:
            cur = app.active_editor
            if cur.com_object.Name not in prev_editors:
                ed_new = cur
                break
        except Exception:
            continue

    if ed_new is not None:
        if rel < 429:
            p_new = extract_part_from_editor(ed_new)
            if p_new is not None:
                return ed_new, p_new
        try:
            ps_new = PLMProductService(ed_new.get_service("PLMProductService").com_object)
            ro_new = ps_new.root_occurrence
            vr_new = ro_new.reference_root_occurrence_of
            if vr_new.rep_instances.count > 0:
                p_new = extract_part_from_editor(ed_new)
                if p_new is not None:
                    return ed_new, p_new
            before_n = vr_new.instances.count
            sel_new = ed_new.selection
            sel_new.clear()
            sel_new.add(ro_new)
            app.start_command("3D Part")
            t1 = time.time()
            while time.time() - t1 < 25.0:
                time.sleep(0.5)
                if vr_new.instances.count > before_n:
                    inst = VPMInstance(vr_new.instances.item(vr_new.instances.count).com_object)
                    child_ref = inst.reference_instance_of
                    if child_ref.rep_instances.count > 0:
                        ri = VPMRepInstance(child_ref.rep_instances.item(1).com_object)
                        sel_new.clear()
                        return ed_new, Part(ri.reference_instance_of.get_item("Part").com_object)
            sel_new.clear()
        except Exception:
            pass

    # 4. Fallback via PLMNewService
    for plm_type in ("3DPart", "3DShape"):
        try:
            ed_fb = dx.client.create_plm_entity(plm_type)
            p_fb = extract_part_from_editor(ed_fb)
            if p_fb is not None:
                return ed_fb, p_fb
        except Exception:
            continue
    raise RuntimeError("Unable to create a 3D Part inside a Physical Product.")


def param_name_for_relation(part: Part, param: Any) -> str:
    """Return the Knowledgeware-safe parameter identifier (auto-backticked if needed)."""
    return part.parameters.get_name_to_use_in_relation(param)


def add_formula(part: Part, target: Any, expr: str, name: str = ""):
    """
    Create and validate a Knowledgeware formula on ``target = expr``.

    Raises ``RuntimeError`` if CATIA rejects the formula expression (empty value).
    """
    relations = part.relations
    try:
        formula = relations.create_formula(name, "", target, expr)
    except Exception:
        fallback_name = name or f"Formula.{relations.count + 1}"
        formula = relations.create_formula(fallback_name, "", target, expr)
    if not formula.value:
        raise RuntimeError(f"Invalid or empty Knowledgeware formula for {target.name} = {expr}")
    return formula


def snapshot_topology_refs(selection: Any, target: Any, query: str = "Topology.Face,sel") -> list[Reference]:
    """
    Snapshot B-Rep references from ``Selection.Search`` into a Python list and clear
    the CSO immediately so subsequent ``MeasurableService`` calls cannot invalidate iteration.
    """
    selection.clear()
    selection.add(target)
    selection.search(query)
    refs = []
    for i in range(1, selection.count + 1):
        try:
            refs.append(selection.item(i).reference)
        except Exception:
            break
    selection.clear()
    return refs


def constrain_hole_origin(part: Part, hole: Any) -> None:
    """Constrain a native CATIA ``Hole`` positioning sketch point onto its ``AbsoluteAxis.Origin``."""
    sk = hole.sketch
    sk.open_edition()
    try:
        for i in range(1, sk.geometric_elements.count + 1):
            geom = sk.geometric_elements.item(i)
            if "Point" in geom.name:
                sk.constraints.add_bi_elt_cst(
                    CatConstraintType.catCstTypeOn,
                    part.create_reference_from_object(geom),
                    part.create_reference_from_object(sk.absolute_axis.origin),
                )
                break
    finally:
        sk.close_edition()


def measure_body(measure_svc: Any, body: Any) -> tuple[float, float, tuple[float, float, float]]:
    """Return ``(volume_mm3, surface_area_mm2, (cx_mm, cy_mm, cz_mm))`` for a ``Body``."""
    mi = measure_svc.get_measure_item((Reference(body.com_object),))
    vol_m3, area_m2, cx, cy, cz = mi.get_volume_area_c_of_g()
    return float(vol_m3) * 1e9, float(area_m2) * 1e6, (float(cx), float(cy), float(cz))
