"""
    Example - Inertia - 001

    Measures the mass, inertia matrix, principal axes, principal moments, and
    center of gravity of the active 3DPart / 3DShape (creating a 20 x 20 x 20 mm
    demo block automatically if the active part has no solid yet).

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
from pycatia3dx.inertia.inertia import Inertia
from pycatia3dx.mode.reference import Reference
from pycatia3dx.types.service import InertiaService

dx = ThreeDExperience()
application = dx.catia
part = dx.ensure_part(create_if_missing=True)
body = part.main_body

# Ensure there is a solid body to measure if the user ran this on an empty part
if body.shapes.count == 0:
    part.in_work_object = body
    ref_xy = Reference(part.origin_elements.plane_xy.com_object)
    sk = body.sketches.add(ref_xy)
    f2d = sk.open_edition()
    pts = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    verts = [f2d.create_point(x, y) for x, y in pts]
    for i in range(4):
        ln = f2d.create_line(*pts[i], *pts[(i + 1) % 4])
        ln.start_point, ln.end_point = verts[i], verts[(i + 1) % 4]
    sk.close_edition()
    part.shape_factory.add_new_pad(sk, 20.0)

part.update()

inertia_service: InertiaService = InertiaService(
    application.active_editor.get_service("InertiaService").com_object
)

reference = part.create_reference_from_object(body)
inertia: Inertia = inertia_service.get_inertia_element(reference)

print(f"Part={part.name}")
print(f"Density={part.density}\n")
print(f"Mass={inertia.get_mass()}\n")

inertia_matrix = inertia.get_inertia_matrix()
print(
    "--------------\n"
    "Inertia Matrix\n"
    "--------------\n"
    f"Ixx={inertia_matrix[0]}\n"
    f"Ixy={inertia_matrix[1]}\n"
    f"Ixz={inertia_matrix[2]}\n"
    f"Iyx={inertia_matrix[3]}\n"
    f"Iyy={inertia_matrix[4]}\n"
    f"Iyz={inertia_matrix[5]}\n"
    f"Izx={inertia_matrix[6]}\n"
    f"Izy={inertia_matrix[7]}\n"
    f"Izz={inertia_matrix[8]}\n"
)

principal_axis = inertia.get_principal_axes()
print(
    "--------------\n"
    "Principal Axis\n"
    "--------------\n"
    f"A1x={principal_axis[0]}\n"
    f"A2x={principal_axis[1]}\n"
    f"A3x={principal_axis[2]}\n"
    f"A1y={principal_axis[3]}\n"
    f"A2y={principal_axis[4]}\n"
    f"A3y={principal_axis[5]}\n"
    f"A1z={principal_axis[6]}\n"
    f"A2z={principal_axis[7]}\n"
    f"A3z={principal_axis[8]}\n"
)

principal_moments = inertia.get_principal_moments()
print(
    "-----------------\n"
    "Principal Moments\n"
    "-----------------\n"
    f"M1={principal_moments[0]}\n"
    f"M2={principal_moments[1]}\n"
    f"M3={principal_moments[2]}\n"
)

cog = inertia.get_cog_position()
print(
    "-----------------\n"
    "Center Of Gravity\n"
    "-----------------\n"
    f"X={cog[0]}\n"
    f"Y={cog[1]}\n"
    f"Z={cog[2]}"
)
