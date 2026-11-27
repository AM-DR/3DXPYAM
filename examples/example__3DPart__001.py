"""

    Example - 3DPart - 001

    Description:
        Create a new Hybrid Body (Geometrical Set) inside a 3DPart / Physical Product.

        Automatically reuses an open 3DPart/3DShape or creates a new Physical Product
        with a 3DPart (works across R2025x–R2027x and any 3DEXPERIENCE UI language).

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

from pycatia3dx import ThreeDExperience

dx = ThreeDExperience()
editor, part = dx.open_part_in_physical_product(reuse_empty=True)

hybrid_bodies = part.hybrid_bodies
hybrid_body = hybrid_bodies.add()
hybrid_body.name = "My New Hybrid Body"
part.update()

print(f"Created Hybrid Body '{hybrid_body.name}' in part '{part.name}'.")
