"""
Core 3DEXPERIENCE Mechanical CAD Helpers (3DXPYAM).

Includes:
- Dynamic COM & universal service dispatch (:class:`DynamicCOMObject`, :class:`DynamicCOMService`)
- Universal rich-client controller & workbench catalog (:class:`UniversalClientController`, :class:`Workbenches`)
- Installation & CATEnv discovery (:func:`discover_3dx_installations`, :func:`discover_ecosystem_summary`)
- Generative Drafting & PDF export automation (:class:`DraftingAutomation`, :class:`TechnicalDrawingBuilder`)
- Release-safe mechanical helpers (:func:`open_part_in_physical_product`, :func:`add_formula`,
  :func:`snapshot_topology_refs`, :func:`constrain_hole_origin`, :func:`measure_body`)
"""
from __future__ import annotations

from pycatia3dx.ecosystem.core_helpers import (
    add_formula,
    constrain_hole_origin,
    measure_body,
    open_part_in_physical_product,
    param_name_for_relation,
    snapshot_topology_refs,
)
from pycatia3dx.ecosystem.discovery import (
    ThreeDXInstallation,
    discover_3dx_installations,
    discover_ecosystem_summary,
    get_primary_3dx_installation,
    parse_catenv_file,
)
from pycatia3dx.ecosystem.drafting_helper import (
    DraftingAutomation,
    TechnicalDrawingBuilder,
)
from pycatia3dx.ecosystem.dynamic_com import (
    DynamicCOMObject,
    DynamicCOMService,
    snake_to_com_candidates,
    unwrap_com_arg,
    wrap_com_result,
)
from pycatia3dx.ecosystem.universal_client import (
    UniversalClientController,
    Workbenches,
    extract_part_from_editor,
)

__all__ = [
    "DraftingAutomation",
    "DynamicCOMObject",
    "DynamicCOMService",
    "TechnicalDrawingBuilder",
    "ThreeDXInstallation",
    "UniversalClientController",
    "Workbenches",
    "add_formula",
    "constrain_hole_origin",
    "discover_3dx_installations",
    "discover_ecosystem_summary",
    "extract_part_from_editor",
    "get_primary_3dx_installation",
    "measure_body",
    "open_part_in_physical_product",
    "param_name_for_relation",
    "parse_catenv_file",
    "snapshot_topology_refs",
    "snake_to_com_candidates",
    "unwrap_com_arg",
    "wrap_com_result",
]
