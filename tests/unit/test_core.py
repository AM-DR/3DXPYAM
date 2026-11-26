"""Offline unit tests for 3DXPYAM.

Compatible with both ``python -m unittest discover tests/unit`` and ``pytest``.
"""
from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock


class TestCorePackage(unittest.TestCase):
    def test_top_level_imports(self):
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
            ThreeDExperience,
            UniversalClientController,
            Workbenches,
            add_formula,
            constrain_hole_origin,
            measure_body,
            open_part_in_physical_product,
            param_name_for_relation,
            snapshot_topology_refs,
        )

        self.assertEqual(pycatia3dx.__project__, "3DXPYAM")
        self.assertIsNotNone(ThreeDExperience)
        for fn in (
            open_part_in_physical_product,
            add_formula,
            snapshot_topology_refs,
            constrain_hole_origin,
            measure_body,
            param_name_for_relation,
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


if __name__ == "__main__":
    unittest.main()
