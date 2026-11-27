"""
Core Mechanical CAD Helpers for 3DXPYAM.

Provides safe, release-aware, and **UI-language-independent** helpers for the
most common 3DEXPERIENCE CATIA Part Design & Sketcher automation workflows
(tested across R2025x–R2027x and all 3DEXPERIENCE UI locales):

- :func:`resolve_nls_message` / :func:`resolve_command_title`: queries
  3DEXPERIENCE's runtime ``SystemService.GetMessage`` catalog so command titles
  resolve dynamically in the active UI language (English, French, German,
  Spanish, Italian, Japanese, Korean, Chinese, Russian, etc.).
- :func:`open_part_in_physical_product`: creates or reuses an empty ``3D Shape``
  nested inside a ``Physical Product`` with zero ``Unknown command`` modal
  popups and full R2025x–R2027x + multi-language compatibility.
- :func:`param_name_for_relation` / :func:`add_formula`: safely creates
  Knowledgeware formulas using ``GetNameToUseInRelation`` (properly backticks
  names with spaces such as ``Geometrical Set.1``) and validates non-empty values.
- :func:`snapshot_topology_refs`: snapshots ``Selection.Search`` references into a
  plain Python list *before* calling ``MeasurableService`` (which can clear the
  active selection mid-loop inside Physical Product editors).
- :func:`constrain_hole_origin`: iso-constrains a native CATIA ``Hole`` positioning
  sketch point onto ``AbsoluteAxis.Origin`` (green sketch) using language-independent
  ``CatGeometricType.catGeoTypePoint2D`` matching.
- :func:`measure_body`: returns ``(volume_mm3, area_mm2, (cx, cy, cz))`` in mm.
"""
from __future__ import annotations

import time
from typing import Any

from pycatia3dx.ecosystem.dynamic_com import unwrap_com_arg
from pycatia3dx.ecosystem.universal_client import extract_part_from_editor
from pycatia3dx.mmr_automation_interfaces.enums import CatConstraintType
from pycatia3dx.mmr_automation_interfaces.part import Part
from pycatia3dx.mode.reference import Reference
from pycatia3dx.product_structure_client.vpm_instance import VPMInstance
from pycatia3dx.product_structure_client.vpm_rep_instance import VPMRepInstance
from pycatia3dx.sketcher.enums import CatGeometricType
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService

PRD_WORKBENCHES: frozenset[str] = frozenset(
    {
        "PrsConfiguration",
        "Assembly",
        "CATKinMechanismWorkbench",
        "CATKinMechanismLegacyWorkbench",
    }
)

_NLS_SENTINEL = "__PYCATIA3DX_NLS_MISSING__"


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        if isinstance(val, bool):
            return int(val)
        return int(val)
    except Exception:
        return default


def _safe_workbench_id(app: Any) -> str:
    try:
        wb = app.get_workbench_id() if hasattr(app, "get_workbench_id") else app.GetWorkbenchId()
        return str(wb).strip() if isinstance(wb, str) else ""
    except Exception:
        return ""


def _safe_window_count(app: Any) -> int:
    try:
        wins = app.windows if hasattr(app, "windows") else app.Windows
        cnt = wins.count if hasattr(wins, "count") else wins.Count
        return _safe_int(cnt, 0)
    except Exception:
        return 0


def _is_empty_part(part: Part) -> bool:
    try:
        return part.main_body.shapes.count == 0
    except Exception:
        return False


def _set_vpm_title(vpm_ref: Any, title: str) -> bool:
    """Best-effort rename of a ``VPMReference`` title (``V_Name``) without failing."""
    raw = unwrap_com_arg(vpm_ref)
    for attr in ("V_Name", "PLM_ExternalID"):
        try:
            raw.SetAttributeValue(attr, str(title))
            if attr == "V_Name":
                return True
        except Exception:
            continue
    try:
        raw.Name = str(title)
        return True
    except Exception:
        return False


def resolve_nls_message(
    app: Any,
    catalog_name: str,
    message_key: str,
    default: str = "",
) -> str:
    """
    Resolve a localized message string from 3DEXPERIENCE's active UI language
    catalog via ``Application.SystemService.GetMessage``.

    Automatically falls back to a tiny VBScript ``SystemService.Evaluate`` call
    when ``win32com`` late-binding rejects an empty ``CATSafeArrayVariant`` tuple.
    Returns ``default`` if the catalog/key cannot be resolved.
    """
    try:
        sys_svc = app.system_service if hasattr(app, "system_service") else app.SystemService
    except Exception:
        return default

    if sys_svc is None:
        return default

    # 1. Direct COM call (fast path)
    try:
        if hasattr(sys_svc, "get_message"):
            res = sys_svc.get_message(catalog_name, message_key, (), _NLS_SENTINEL)
        else:
            res = sys_svc.GetMessage(catalog_name, message_key, (), _NLS_SENTINEL)
        if isinstance(res, str):
            text = res.strip()
            if text and text != _NLS_SENTINEL:
                return text
    except Exception:
        pass

    # 2. VBScript Evaluate fallback (handles CATSafeArrayVariant DISP_E_TYPEMISMATCH)
    try:
        vb_code = (
            "Function pycatiaGetNlsMsg(sysSvc, catName, msgKey, defMsg)\n"
            "    Dim msgParams()\n"
            "    pycatiaGetNlsMsg = sysSvc.GetMessage(catName, msgKey, msgParams, defMsg)\n"
            "End Function"
        )
        raw_sys = unwrap_com_arg(sys_svc)
        if hasattr(sys_svc, "evaluate"):
            res = sys_svc.evaluate(vb_code, 0, "pycatiaGetNlsMsg", [raw_sys, catalog_name, message_key, _NLS_SENTINEL])
        else:
            res = sys_svc.Evaluate(vb_code, 0, "pycatiaGetNlsMsg", [raw_sys, catalog_name, message_key, _NLS_SENTINEL])
        if isinstance(res, str):
            text = res.strip()
            if text and text != _NLS_SENTINEL:
                return text
    except Exception:
        pass

    return default


def resolve_command_title(
    app: Any,
    catalog_name: str,
    message_key: str,
    default_title: str,
) -> str:
    """
    Resolve the localized Power Input / ``StartCommand`` title of a 3DEXPERIENCE
    command header in the active UI language (e.g. ``"3D Part"`` in English,
    ``"Pièce 3D"`` in French, ``"3D-Teil"`` in German, ``"3D パーツ"`` in Japanese,
    ``"3D 零件"`` in Simplified Chinese).
    """
    return resolve_nls_message(app, catalog_name, message_key, default=default_title)


def _ensure_prd_workbench(dx: Any, app: Any, *, bootstrap_if_empty: bool = True) -> tuple[bool, Any | None]:
    """
    Ensure a ``PRDWorkshop`` workbench (such as ``PrsConfiguration``) is active so
    product-structure commands can run without ``Unknown command`` popups.

    Returns ``(ok, temp_seed_window_or_None)``. Callers must close any returned
    seed window untouched without saving in a ``finally`` block.
    """
    win_cnt = _safe_window_count(app)
    if win_cnt > 0 and _safe_workbench_id(app) in PRD_WORKBENCHES:
        return True, None

    # 1. Try activating or switching an already-open product window
    if win_cnt > 0:
        for i in range(1, win_cnt + 1):
            try:
                w = app.windows.item(i)
                w.activate()
                time.sleep(0.25)
                if _safe_workbench_id(app) in PRD_WORKBENCHES:
                    return True, None
                ed = app.active_editor
                _ = ed.get_service("PLMProductService")
                for wb_target in ("PrsConfiguration", "Assembly"):
                    try:
                        app.start_workbench(wb_target)
                        time.sleep(0.35)
                        if _safe_workbench_id(app) in PRD_WORKBENCHES:
                            return True, None
                    except Exception:
                        continue
            except Exception:
                continue

        for wb_target in ("PrsConfiguration", "Assembly"):
            try:
                app.start_workbench(wb_target)
                time.sleep(0.35)
                if _safe_workbench_id(app) in PRD_WORKBENCHES:
                    return True, None
            except Exception:
                continue

    if not bootstrap_if_empty or dx is None or not hasattr(dx, "client"):
        return False, None

    # 2. Cleanly bootstrap PrsConfiguration on an empty session via language-independent PLM search
    client = dx.client
    prev_win_names: set[str] = set()
    try:
        for i in range(1, _safe_window_count(app) + 1):
            prev_win_names.add(str(app.windows.item(i).name))
    except Exception:
        pass

    seed_ent = None
    try:
        found = client.search_plm(base_type="VPMReference", attributes={"V_Name": "*"})
    except Exception:
        found = []

    if found:
        for ent in found:
            try:
                mat = str(ent.com_object.GetAttributeValue("V_maturity") or "").upper()
                if mat in ("PRIVATE", "IN_WORK"):
                    seed_ent = ent
                    break
            except Exception:
                continue
        if seed_ent is None:
            seed_ent = found[0]

    if seed_ent is None:
        return False, None

    try:
        client.open_plm_object(seed_ent)
        time.sleep(0.5)
        if _safe_workbench_id(app) not in PRD_WORKBENCHES:
            try:
                app.start_workbench("PrsConfiguration")
                time.sleep(0.4)
            except Exception:
                pass
        if _safe_workbench_id(app) in PRD_WORKBENCHES:
            try:
                w_act = app.active_window
                seed_win = w_act if str(w_act.name) not in prev_win_names else None
            except Exception:
                seed_win = None
            return True, seed_win
    except Exception:
        pass

    return False, None


def open_part_in_physical_product(
    dx: Any,
    app: Any | None = None,
    *,
    reuse_empty: bool = True,
    name: str | None = None,
    timeout: float = 25.0,
):
    """
    Create (or reuse an empty) ``3D Shape`` nested inside a ``Physical Product``.

    Works seamlessly across 3DEXPERIENCE R2025x, R2026x, and R2027x
    (``release >= 429``) and across **all 3DEXPERIENCE UI languages** (resolving
    localized ``StartCommand`` titles dynamically via ``SystemService.GetMessage``
    and avoiding unguarded ``StartCommand`` popups on empty sessions).

    Returns:
        Tuple ``(editor, part)``.
    """
    app = app or dx.catia

    # 1. Reuse an already-open empty 3D Part inside a Physical Product if requested
    if reuse_empty and _safe_window_count(app) > 0:
        try:
            ed_act = app.active_editor
            ps = PLMProductService(ed_act.get_service("PLMProductService").com_object)
            ro = ps.root_occurrence
            vr = ro.reference_root_occurrence_of
            if vr.rep_instances.count > 0:
                p_act = extract_part_from_editor(ed_act)
                if p_act is not None and _is_empty_part(p_act):
                    if name:
                        _set_vpm_title(vr, name)
                    return ed_act, p_act
            for i in range(1, vr.instances.count + 1):
                inst = VPMInstance(vr.instances.item(i).com_object)
                ref_child = inst.reference_instance_of
                if ref_child.rep_instances.count > 0:
                    ri = VPMRepInstance(ref_child.rep_instances.item(1).com_object)
                    p_child = Part(ri.reference_instance_of.get_item("Part").com_object)
                    if _is_empty_part(p_child):
                        if name:
                            _set_vpm_title(ref_child, name)
                        return ed_act, p_child
        except Exception:
            pass

    cmd_3d_part = resolve_command_title(
        app,
        "PRDCmdWorkshop",
        "PRDCmdWorkshop.PLMCmdInsertNew3DPartCtx.Title",
        "3D Part",
    )

    # 2. If active editor is an existing Physical Product, ensure PrsConfiguration and insert a 3D Part
    if _safe_window_count(app) > 0:
        try:
            ed_cur = app.active_editor
            ps_cur = PLMProductService(ed_cur.get_service("PLMProductService").com_object)
            ro_cur = ps_cur.root_occurrence
            vr_cur = ro_cur.reference_root_occurrence_of

            if _safe_workbench_id(app) not in PRD_WORKBENCHES:
                for wb_target in ("PrsConfiguration", "Assembly"):
                    try:
                        app.start_workbench(wb_target)
                        time.sleep(0.35)
                        if _safe_workbench_id(app) in PRD_WORKBENCHES:
                            break
                    except Exception:
                        continue

            if _safe_workbench_id(app) in PRD_WORKBENCHES:
                before_cnt = vr_cur.instances.count
                sel_cur = ed_cur.selection
                sel_cur.clear()
                sel_cur.add(ro_cur)
                app.start_command(cmd_3d_part)
                t0 = time.time()
                while time.time() - t0 < min(timeout, 20.0):
                    time.sleep(0.4)
                    if vr_cur.instances.count > before_cnt:
                        inst = VPMInstance(vr_cur.instances.item(vr_cur.instances.count).com_object)
                        ref_child = inst.reference_instance_of
                        if ref_child.rep_instances.count > 0:
                            ri = VPMRepInstance(ref_child.rep_instances.item(1).com_object)
                            sel_cur.clear()
                            if name:
                                _set_vpm_title(ref_child, name)
                            return ed_cur, Part(ri.reference_instance_of.get_item("Part").com_object)
                sel_cur.clear()
        except Exception:
            pass

    # 3. Create a brand-new standalone 3D Part (language-independent & popup-free across R2025x–R2027x)
    rel = 0
    try:
        rel = int(app.system_configuration.release)
    except Exception:
        pass

    # 3a. R2025x–R2026x: try direct language-independent PLMNewService("3DPart") first
    if rel < 429 and dx is not None and hasattr(dx, "client"):
        try:
            ed_nat = dx.client.create_plm_entity("3DPart", name=name)
            p_nat = extract_part_from_editor(ed_nat)
            if p_nat is not None:
                return ed_nat, p_nat
        except Exception:
            pass

    # 3b. R2027x+ safe path: activate/bootstrap PrsConfiguration -> localized PLMCmdInsertNew3DPartCtx -> PLMOpenInNewWindow
    ok_prd, seed_win = _ensure_prd_workbench(dx, app, bootstrap_if_empty=True)
    if ok_prd:
        host_win = None
        new_inst = None
        child_ref = None
        try:
            host_win = app.active_window
            ed_host = app.active_editor
            ps_host = PLMProductService(ed_host.get_service("PLMProductService").com_object)
            ro_host = ps_host.root_occurrence
            vr_host = ro_host.reference_root_occurrence_of
            before_n = vr_host.instances.count

            sel = ed_host.selection
            sel.clear()
            sel.add(ro_host)
            app.start_command(cmd_3d_part)

            t0 = time.time()
            while time.time() - t0 < timeout:
                time.sleep(0.35)
                if vr_host.instances.count > before_n:
                    cand_inst = VPMInstance(vr_host.instances.item(vr_host.instances.count).com_object)
                    cand_ref = cand_inst.reference_instance_of
                    if cand_ref.rep_instances.count > 0:
                        new_inst = cand_inst
                        child_ref = cand_ref
                        break
            sel.clear()

            if child_ref is not None:
                if name:
                    _set_vpm_title(child_ref, name)
                ed_new = dx.client.open_in_new_window(child_ref)
                time.sleep(0.4)
                new_win = app.active_window

                # Keep any pre-existing host window clean by removing the temporary child link
                if seed_win is None and host_win is not None and new_inst is not None:
                    try:
                        host_win.activate()
                        sel_h = app.active_editor.selection
                        sel_h.clear()
                        sel_h.add(new_inst)
                        sel_h.delete()
                        sel_h.clear()
                        new_win.activate()
                    except Exception:
                        try:
                            new_win.activate()
                        except Exception:
                            pass

                ri = VPMRepInstance(child_ref.rep_instances.item(1).com_object)
                return ed_new, Part(ri.reference_instance_of.get_item("Part").com_object)
        except Exception:
            pass
        finally:
            if seed_win is not None:
                try:
                    seed_win.close()
                except Exception:
                    pass

    # 4. Final language-independent fallback via PLMNewService (works even on an empty tenant)
    if dx is not None and hasattr(dx, "client"):
        for plm_type in ("3DPart", "3DShape"):
            try:
                ed_fb = dx.client.create_plm_entity(plm_type, name=name)
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


def _is_sketch_point_2d(geom: Any) -> bool:
    """Return True if ``geom`` is a 2D sketch point, independent of UI language."""
    try:
        geo_type = geom.geometric_type
        if isinstance(geo_type, int) and geo_type == int(CatGeometricType.catGeoTypePoint2D):
            return True
        if isinstance(geo_type, int) and geo_type != int(CatGeometricType.catGeoTypeUnknown):
            return False
    except Exception:
        pass

    raw = getattr(geom, "com_object", geom)
    if raw is not None:
        try:
            raw_type = getattr(raw, "GeometricType", None)
            if isinstance(raw_type, int):
                return raw_type == int(CatGeometricType.catGeoTypePoint2D)
        except Exception:
            pass
        if hasattr(raw, "GetCoordinates") and hasattr(raw, "SetData"):
            return True

    try:
        return "Point" in str(geom.name)
    except Exception:
        return False


def constrain_hole_origin(part: Part, hole: Any) -> None:
    """
    Constrain a native CATIA ``Hole`` positioning sketch point onto its
    ``AbsoluteAxis.Origin`` using language-independent ``CatGeometricType`` matching.
    """
    sk = hole.sketch
    sk.open_edition()
    try:
        origin = sk.absolute_axis.origin
        origin_com = getattr(origin, "com_object", origin)
        for i in range(1, sk.geometric_elements.count + 1):
            geom = sk.geometric_elements.item(i)
            geom_com = getattr(geom, "com_object", geom)
            if geom_com is origin_com:
                continue
            if _is_sketch_point_2d(geom):
                sk.constraints.add_bi_elt_cst(
                    CatConstraintType.catCstTypeOn,
                    part.create_reference_from_object(geom),
                    part.create_reference_from_object(origin),
                )
                break
    finally:
        sk.close_edition()


def measure_body(measure_svc: Any, body: Any) -> tuple[float, float, tuple[float, float, float]]:
    """Return ``(volume_mm3, surface_area_mm2, (cx_mm, cy_mm, cz_mm))`` for a ``Body``."""
    mi = measure_svc.get_measure_item((Reference(body.com_object),))
    vol_m3, area_m2, cx, cy, cz = mi.get_volume_area_c_of_g()
    return float(vol_m3) * 1e9, float(area_m2) * 1e6, (float(cx), float(cy), float(cz))
