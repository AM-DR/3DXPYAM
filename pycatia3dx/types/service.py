from __future__ import annotations

from typing import Type, Union

from pycatia3dx.drafting.drawing_gen_service import DrawingGenService
from pycatia3dx.drafting.drawing_service import DrawingService
from pycatia3dx.ecosystem.dynamic_com import DynamicCOMService
from pycatia3dx.inertia.inertia_box_service import InertiaBoxService
from pycatia3dx.inertia.inertia_service import InertiaService
from pycatia3dx.interfaces.player_services import PlayerServices
from pycatia3dx.interfaces.service import Service
from pycatia3dx.interfaces.visu_services import VisuServices
from pycatia3dx.knowledge_interfaces.knowledge_services import KnowledgeServices
from pycatia3dx.measure.measurable_service import MeasurableService
from pycatia3dx.measure.measure_service import MeasureService
from pycatia3dx.plm_access.plm_script_service import PLMScriptService
from pycatia3dx.plm_access.plm_search_service import PLMSearchService
from pycatia3dx.plm_access.search_service import SearchService
from pycatia3dx.plm_application_context.plm_app_context import PLMAppContext
from pycatia3dx.plm_application_context.plm_refresh_service import PLMRefreshService
from pycatia3dx.plm_application_context.pn_o_service import PnOService
from pycatia3dx.plm_session_builder.plm_new_service import PLMNewService
from pycatia3dx.plm_session_builder.plm_open_service import PLMOpenService
from pycatia3dx.plm_session_builder.plm_propagate_service import PLMPropagateService
from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService
from pycatia3dx.vpm_editor_context.product_session_service import ProductSessionService

ApplicationService = Union[
    DrawingGenService,
    DrawingService,
    DynamicCOMService,
    KnowledgeServices,
    PLMAppContext,
    PLMNewService,
    PLMOpenService,
    PLMPropagateService,
    PLMRefreshService,
    PLMScriptService,
    PLMSearchService,
    PnOService,
    ProductSessionService,
    SearchService,
    Service,
    VisuServices,
]

EditorService = Union[
    DrawingGenService,
    DrawingService,
    DynamicCOMService,
    InertiaBoxService,
    InertiaService,
    KnowledgeServices,
    MeasurableService,
    MeasureService,
    PlayerServices,
    PLMProductService,
    Service,
    VisuServices,
]

application_service_types: dict[str, dict[str, Type[Service]]] = {
    "CATDrawingGenService": {"type": DrawingGenService},
    "CATDrawingService": {"type": DrawingService},
    "DrawingService": {"type": DrawingService},
    "KnowledgeServices": {"type": KnowledgeServices},
    "PLMAppContext": {"type": PLMAppContext},
    "PLMNewService": {"type": PLMNewService},
    "PLMOpenService": {"type": PLMOpenService},
    "PLMPropagateService": {"type": PLMPropagateService},
    "PLMRefreshService": {"type": PLMRefreshService},
    "PLMScriptService": {"type": PLMScriptService},
    "PLMSearch": {"type": PLMSearchService},
    "PLMSearchService": {"type": PLMSearchService},
    "PnOService": {"type": PnOService},
    "ProductSessionService": {"type": ProductSessionService},
    "Search": {"type": SearchService},
    "SearchService": {"type": SearchService},
    "Service": {"type": Service},
    "VisuServices": {"type": VisuServices},
}

editor_service_types: dict[str, dict[str, Type[Service]]] = {
    "CATDrawingGenService": {"type": DrawingGenService},
    "CATDrawingService": {"type": DrawingService},
    "DrawingService": {"type": DrawingService},
    "InertiaBoxService": {"type": InertiaBoxService},
    "InertiaService": {"type": InertiaService},
    "KnowledgeServices": {"type": KnowledgeServices},
    "MeasurableService": {"type": MeasurableService},
    "MeasureService": {"type": MeasureService},
    "PlayerServices": {"type": PlayerServices},
    "PLMProductService": {"type": PLMProductService},
    "Service": {"type": Service},
    "VisuServices": {"type": VisuServices},
}


def resolve_service_entry(
    service_name: str,
    registry: dict[str, dict[str, Type[Service]]],
) -> tuple[str, Type[Service]] | None:
    """
    Look up ``service_name`` in ``registry`` (exact match first, then
    case-insensitive match), returning ``(canonical_com_name, wrapper_cls)``.
    """
    if service_name in registry:
        return service_name, registry[service_name]["type"]
    lower = service_name.lower()
    for key, entry in registry.items():
        if key.lower() == lower:
            return key, entry["type"]
    return None
