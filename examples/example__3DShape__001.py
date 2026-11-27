"""

    Example - Part - 001

    Description:
        Create a new 3DShape.

    Requirements:
        - 3DEXPERIENCE CATIA running.

"""
from pathlib import Path
import sys

# Insert the repository root (NOT the inner pycatia3dx/ folder) so examples can
# be run directly without `pip install -e .` and without shadowing stdlib modules.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from pycatia3dx import catia3dx
from pycatia3dx.mmr_automation_interfaces.part import Part
from pycatia3dx.plm_session_builder.plm_new_service import PLMNewService

application = catia3dx()

plm_service: PLMNewService = application.get_session_service("PLMNewService")
editor = plm_service.plm_create("3DShape")

part = Part(editor.active_com_object)
print(f"Created 3DShape part: '{part.name}'.")
