"""
3DXPYAM — Python Automation Library for CATIA 3DEXPERIENCE Mechanical CAD.

    >>> from pycatia3dx import ThreeDExperience
    >>> dx = ThreeDExperience()
    >>> editor, part = dx.open_part_in_physical_product()
"""

from pycatia3dx.annotation.enums import *
from pycatia3dx.drafting.enums import *
from pycatia3dx.hybrid_shapes.enums import *
from pycatia3dx.interfaces.enums import *
from pycatia3dx.knowledge_interfaces.enums import *
from pycatia3dx.measure.enums import *
from pycatia3dx.mmr_automation_interfaces.enums import *
from pycatia3dx.os.enums import *
from pycatia3dx.part.enums import *
from pycatia3dx.plm_access.enums import *
from pycatia3dx.sketcher.enums import *
from pycatia3dx.system.enums import *
from pycatia3dx.version import version

from pycatia3dx.base_interfaces.base_application import catia_application as catia3dx
from pycatia3dx.ecosystem import (
    DraftingAutomation,
    DynamicCOMObject,
    DynamicCOMService,
    TechnicalDrawingBuilder,
    UniversalClientController,
    Workbenches,
    add_formula,
    constrain_hole_origin,
    measure_body,
    open_part_in_physical_product,
    param_name_for_relation,
    snapshot_topology_refs,
)
from pycatia3dx.hub import ThreeDExperience

__author__ = "Drissi Amjad"
__author_email = "17amjad2004@gmail.com"
__maintainer__ = "Drissi Amjad"
__maintainer_email = "17amjad2004@gmail.com"
__credits__ = ["Drissi Amjad", "Paul Bourne"]
__description__ = (
    "Python automation library for CATIA 3DEXPERIENCE Mechanical CAD "
    "(Part Design, Sketcher, GSD, Knowledgeware, Measure & Drafting)."
)
__project__ = "3DXPYAM"
__version__ = version
__url__ = "https://github.com/AM-DR/3DXPYAM"

name = __project__
