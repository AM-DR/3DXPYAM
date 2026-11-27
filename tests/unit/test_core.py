"""Offline unit tests for 3DXPYAM.

Compatible with both ``python -m unittest discover tests/unit`` and ``pytest``.
"""
from __future__ import annotations

import tomllib
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class TestCorePackage(unittest.TestCase):
    def test_top_level_imports_and_version(self):
        import pycatia3dx
        from pycatia3dx import (
            CATMeasurableType,
            CatConstraintMode,
            CatConstraintType,
            CatHoleType,
            CatLimitMode,
            DraftingAutomation,
            DynamicCOMObject,
            DynamicCOMService,
            PRD_WORKBENCHES,
            ThreeDExperience,
            UniversalClientController,
            Workbenches,
            add_formula,
            constrain_hole_origin,
            measure_body,
            open_part_in_physical_product,
            param_name_for_relation,
            resolve_command_title,
            resolve_nls_message,
            snapshot_topology_refs,
        )

        self.assertEqual(pycatia3dx.__project__, "3DXPYAM")
        self.assertNotEqual(pycatia3dx.__version__, "0.0.0")
        self.assertEqual(pycatia3dx.__version__, "0.1.0")
        self.assertIn("PrsConfiguration", PRD_WORKBENCHES)
        self.assertIsNotNone(ThreeDExperience)
        for fn in (
            open_part_in_physical_product,
            add_formula,
            snapshot_topology_refs,
            constrain_hole_origin,
            measure_body,
            param_name_for_relation,
            resolve_command_title,
            resolve_nls_message,
        ):
            self.assertTrue(callable(fn))
        for sym in (
            CATMeasurableType,
            CatConstraintMode,
            CatConstraintType,
            CatHoleType,
            CatLimitMode,
            DraftingAutomation,
            DynamicCOMObject,
            DynamicCOMService,
            UniversalClientController,
            Workbenches,
        ):
            self.assertIsNotNone(sym)

    def test_pyproject_cross_platform_packaging(self):
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            cfg = tomllib.load(f)
        deps = cfg["project"]["dependencies"]
        pywin_deps = [d for d in deps if "pywin32" in d.lower()]
        self.assertTrue(pywin_deps, "Expected pywin32 in project dependencies")
        self.assertTrue(
            all("sys_platform" in d and "win32" in d for d in pywin_deps),
            f"pywin32 must be guarded by sys_platform == 'win32': {pywin_deps}",
        )

    def test_hub_lightweight_init(self):
        from pycatia3dx import ThreeDExperience

        dx = ThreeDExperience()
        summary = dx.discover()
        self.assertIn("3dexperience_installations", summary)
        self.assertIn("catenv_files", summary)

    def test_service_registry_core_only(self):
        from pycatia3dx.types.service import (
            application_service_types,
            editor_service_types,
            resolve_service_entry,
        )

        self.assertIsNotNone(resolve_service_entry("MeasurableService", editor_service_types))
        self.assertIsNotNone(resolve_service_entry("measureservice", editor_service_types))
        self.assertIsNotNone(resolve_service_entry("PLMProductService", editor_service_types))
        self.assertIsNotNone(resolve_service_entry("PLMNewService", application_service_types))
        self.assertIsNotNone(resolve_service_entry("CATDrawingService", editor_service_types))
        self.assertIsNone(resolve_service_entry("NonExistentService", application_service_types))

    def test_resolve_nls_message_direct_and_vbscript_fallback(self):
        from pycatia3dx.ecosystem.core_helpers import resolve_command_title

        # Direct GetMessage returning French / German / Japanese localized titles
        for localized in ("Pièce 3D", "3D-Teil", "3D パーツ", "3D 零件"):
            app = MagicMock()
            app.system_service.get_message.return_value = localized
            resolved = resolve_command_title(
                app,
                "PRDCmdWorkshop",
                "PRDCmdWorkshop.PLMCmdInsertNew3DPartCtx.Title",
                "3D Part",
            )
            self.assertEqual(resolved, localized)

        # Fallback to VBScript Evaluate when direct COM raises DISP_E_TYPEMISMATCH
        app_vb = MagicMock()
        app_vb.system_service.get_message.side_effect = RuntimeError("DISP_E_TYPEMISMATCH")
        app_vb.system_service.evaluate.return_value = "Pièce 3D"
        resolved_vb = resolve_command_title(
            app_vb,
            "PRDCmdWorkshop",
            "PRDCmdWorkshop.PLMCmdInsertNew3DPartCtx.Title",
            "3D Part",
        )
        self.assertEqual(resolved_vb, "Pièce 3D")
        eval_call = app_vb.system_service.evaluate.call_args
        fn_name = eval_call.args[2]
        self.assertFalse(fn_name.startswith("_"), f"VBScript function cannot start with '_': {fn_name}")

        # Fallback to default when sentinel is returned
        app_missing = MagicMock()
        app_missing.system_service.get_message.side_effect = lambda cat, key, params, default: default
        app_missing.system_service.evaluate.side_effect = RuntimeError("unavailable")
        self.assertEqual(
            resolve_command_title(app_missing, "PRDCmdWorkshop", "Missing.Key", "3D Part"),
            "3D Part",
        )

    def test_open_part_uses_localized_command_and_avoids_empty_popups(self):
        from pycatia3dx.ecosystem.core_helpers import open_part_in_physical_product

        # 1. Active Physical Product on French 3DEXPERIENCE -> must invoke "Pièce 3D", never "3D Part"
        app = MagicMock()
        app.windows.count = 1
        app.get_workbench_id.return_value = "PrsConfiguration"
        app.system_service.get_message.return_value = "Pièce 3D"

        ed = MagicMock()
        app.active_editor = ed
        ps_com = MagicMock()
        ed.get_service.return_value = MagicMock(com_object=ps_com)
        ro_com = ps_com.RootOccurrence
        vr_com = ro_com.ReferenceRootOccurrenceOf
        vr_com.RepInstances.Count = 0

        # Simulate child instance appearing after StartCommand("Pièce 3D")
        inst_count = [0]

        def _start_cmd(cmd):
            if cmd == "Pièce 3D":
                inst_count[0] = 1

        app.start_command.side_effect = _start_cmd
        type(vr_com.Instances).Count = property(lambda _self: inst_count[0])

        child_part_com = MagicMock()
        child_ref_com = MagicMock()
        child_ref_com.RepInstances.Count = 1
        child_ref_com.RepInstances.Item.return_value.ReferenceInstanceOf.GetItem.return_value = child_part_com
        vr_com.Instances.Item.return_value.ReferenceInstanceOf = child_ref_com

        dx = MagicMock()
        ed_res, part_res = open_part_in_physical_product(dx, app, reuse_empty=False, timeout=2.0)
        self.assertIs(ed_res, ed)
        self.assertIs(part_res.com_object, child_part_com)
        app.start_command.assert_called_once_with("Pièce 3D")

        # 2. Empty R2027x session (0 windows, no PLM seed) -> must NEVER call start_command("Physical Product")
        app_empty = MagicMock()
        app_empty.windows.count = 0
        app_empty.get_workbench_id.return_value = ""
        app_empty.system_configuration.release = 429
        app_empty.system_service.get_message.return_value = "Pièce 3D"

        dx_empty = MagicMock()
        dx_empty.client.search_plm.return_value = []
        ed_fb = MagicMock()
        part_fb_com = MagicMock()
        part_fb_com.MainBody = MagicMock()
        ed_fb.active_com_object = part_fb_com
        dx_empty.client.create_plm_entity.return_value = ed_fb

        ed_out, part_out = open_part_in_physical_product(dx_empty, app_empty, reuse_empty=False)
        self.assertIs(ed_out, ed_fb)
        self.assertIs(part_out.com_object, part_fb_com)
        app_empty.start_command.assert_not_called()

    def test_constrain_hole_origin_language_independent(self):
        from pycatia3dx.ecosystem.core_helpers import constrain_hole_origin
        from pycatia3dx.sketcher.enums import CatGeometricType

        part = MagicMock()
        hole = MagicMock()
        sk = hole.sketch
        origin = MagicMock(name="Origin", com_object=object())
        sk.absolute_axis.origin = origin

        axis_el = MagicMock(name="Achsensystem", geometric_type=int(CatGeometricType.catGeoTypeAxis2D), com_object=object())
        pt_de = MagicMock(name="Punkt.1", geometric_type=int(CatGeometricType.catGeoTypePoint2D), com_object=object())
        sk.geometric_elements.count = 2
        sk.geometric_elements.item.side_effect = [axis_el, pt_de]

        constrain_hole_origin(part, hole)
        sk.open_edition.assert_called_once()
        sk.close_edition.assert_called_once()
        sk.constraints.add_bi_elt_cst.assert_called_once()
        part.create_reference_from_object.assert_any_call(pt_de)
        part.create_reference_from_object.assert_any_call(origin)

    def test_dynamic_com_vbscript_identifier_valid(self):
        from pycatia3dx.ecosystem.dynamic_com import DynamicCOMObject

        raw_com = MagicMock()
        raw_com.Application.SystemService.Evaluate.return_value = (1.0, 2.0, 3.0)
        dyn = DynamicCOMObject(raw_com)
        res = dyn.call_vba_array_method("GetCoordinates", 3)
        self.assertEqual(res, (1.0, 2.0, 3.0))
        vb_code, _lang, fn_name, _params = raw_com.Application.SystemService.Evaluate.call_args.args
        self.assertFalse(fn_name.startswith("_"))
        self.assertIn(f"Function {fn_name}(", vb_code)

    def test_drafting_language_independent_views_and_pdf_printer(self):
        from pycatia3dx.ecosystem.drafting_helper import TechnicalDrawingBuilder

        app = MagicMock()
        editor = MagicMock()
        drw_root = MagicMock()
        views = drw_root.active_sheet.views

        # Views named in French ("Vue principale", "Calque de fond") -> must be accessed by 1-based index
        main_v_com = MagicMock(Name="Vue principale")
        bg_v_com = MagicMock(Name="Calque de fond")

        def _views_item(idx):
            if idx == 1:
                return MagicMock(com_object=main_v_com)
            if idx == 2:
                return MagicMock(com_object=bg_v_com)
            raise KeyError(f"Unknown view {idx!r}")

        views.item.side_effect = _views_item

        builder = TechnicalDrawingBuilder(app, editor, drw_root, MagicMock())
        self.assertIs(builder._get_builtin_view(2, "View.2").com_object, bg_v_com)
        self.assertIs(builder._get_builtin_view(1, "View.1").com_object, main_v_com)

        # PDF printer fallback when "Microsoft Print to PDF" is missing / renamed
        alt_pdf = MagicMock(device_name="Adobe PDF", name="Adobe PDF")
        other_pr = MagicMock(device_name="HP LaserJet", name="HP LaserJet")

        def _printer_item(idx):
            if isinstance(idx, str):
                raise KeyError("not found")
            return other_pr if idx == 1 else alt_pdf

        app.printers.count = 2
        app.printers.item.side_effect = _printer_item
        self.assertIs(builder._resolve_pdf_printer("Microsoft Print to PDF"), alt_pdf)

    def test_add_formula_and_validation(self):
        from pycatia3dx.ecosystem.core_helpers import add_formula, param_name_for_relation

        part = MagicMock()
        part.parameters.get_name_to_use_in_relation.return_value = "`Geometrical Set.1\\Plane.1\\Offset`"
        self.assertEqual(
            param_name_for_relation(part, MagicMock()),
            "`Geometrical Set.1\\Plane.1\\Offset`",
        )

        good_formula = MagicMock(value="10mm")
        part.relations.create_formula.return_value = good_formula
        self.assertIs(add_formula(part, MagicMock(name="Depth"), "10mm"), good_formula)

        bad_formula = MagicMock(value="")
        part.relations.create_formula.return_value = bad_formula
        with self.assertRaises(RuntimeError):
            add_formula(part, MagicMock(name="Depth"), "invalid_expr")

    def test_snapshot_topology_refs_clears_cso(self):
        from pycatia3dx.ecosystem.core_helpers import snapshot_topology_refs

        sel = MagicMock()
        sel.count = 2
        ref1, ref2 = MagicMock(), MagicMock()
        sel.item.side_effect = [MagicMock(reference=ref1), MagicMock(reference=ref2)]

        refs = snapshot_topology_refs(sel, MagicMock(), "Topology.Face,sel")
        self.assertEqual(refs, [ref1, ref2])
        self.assertEqual(sel.clear.call_count, 2)
        sel.search.assert_called_once_with("Topology.Face,sel")

    def test_measure_body_unit_conversion(self):
        from pycatia3dx.ecosystem.core_helpers import measure_body

        measure_svc = MagicMock()
        measure_svc.get_measure_item.return_value.get_volume_area_c_of_g.return_value = (
            1e-6,   # 1,000 mm^3
            5e-4,   # 500 mm^2
            10.0,
            20.0,
            30.0,
        )
        vol, area, cog = measure_body(measure_svc, MagicMock(com_object=object()))
        self.assertAlmostEqual(vol, 1000.0)
        self.assertAlmostEqual(area, 500.0)
        self.assertEqual(cog, (10.0, 20.0, 30.0))

    def test_examples_never_shadow_stdlib_and_self_healing_guards_work(self):
        import subprocess
        import sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        pkg_dir = repo_root / "pycatia3dx"

        # 1. No example script may insert `..\pycatia3dx` into sys.path
        for ex in sorted((repo_root / "examples").glob("*.py")):
            src = ex.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("..\\pycatia3dx", src, f"{ex.name} inserts inner pycatia3dx/ into sys.path")
            self.assertNotIn("../pycatia3dx", src, f"{ex.name} inserts inner pycatia3dx/ into sys.path")

        # 2. Even if someone mistakenly puts pycatia3dx/ on sys.path[0], stdlib types & os still load cleanly
        code = (
            f"import sys; sys.path.insert(0, {str(pkg_dir)!r}); sys.path.insert(1, {str(repo_root)!r}); "
            "import enum, types, os; "
            "assert hasattr(types, 'GenericAlias') and hasattr(types, 'MappingProxyType'); "
            "assert hasattr(os, 'path'); "
            "from pycatia3dx import ThreeDExperience, catia3dx; "
            "from pycatia3dx.types.general import CATVariant; "
            "print('GUARD_OK')"
        )
        proc = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, f"Subprocess failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
        self.assertIn("GUARD_OK", proc.stdout)

    def test_plm_product_service_root_occurrence_friendly_error(self):
        from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService

        bad_com = MagicMock()
        type(bad_com).RootOccurrence = property(lambda _self: (_ for _ in ()).throw(RuntimeError("COM E_NOINTERFACE")))
        svc = PLMProductService(bad_com)
        with self.assertRaises(RuntimeError) as ctx:
            _ = svc.root_occurrence
        self.assertIn("open_part_in_physical_product", str(ctx.exception))

    def test_ribbed_bracket_example_analytical_volume_and_importable(self):
        import importlib.util
        from pathlib import Path

        ex_path = Path(__file__).resolve().parents[2] / "examples" / "example__ribbed_bracket_full_part.py"
        spec = importlib.util.spec_from_file_location("example_ribbed_bracket", ex_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Base (18,651.86) + Upper Boss (18,762.01) + Rib (3,087.00) - Hole (5,301.44) = 35,199.44 mm^3
        vol = mod.analytical_volume_mm3()
        self.assertAlmostEqual(vol, 35199.4376, places=2)


if __name__ == "__main__":
    unittest.main()
