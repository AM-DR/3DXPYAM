# 3DXPYAM — Python Automation Library for CATIA 3DEXPERIENCE

**3DXPYAM** is a clean, lightweight Python automation library for **Mechanical CAD** in Dassault Systèmes **CATIA 3DEXPERIENCE** (tested on **R2025x – R2027x**).

It provides a focused, reliable Python interface around the core mechanical design, drafting, metrology, and PLM product structure workbenches.

---

## Included Core Modules

| Domain | Package(s) | What it automates |
|---|---|---|
| **Part Design** | `pycatia3dx.part`, `pycatia3dx.mmr_automation_interfaces` | `Pad`, `Pocket`, `Shaft`, `Groove`, `Hole`, `Chamfer`, `EdgeFillet`, `Draft`, `Mirror`, patterns, `PartBody` & `HybridBody` |
| **Sketcher** | `pycatia3dx.sketcher` | `Factory2D`, lines, circles, arcs, points, geometric & driving dimensional constraints (100% iso-constrained green sketches) |
| **Wireframe & Surface (GSD)** | `pycatia3dx.hybrid_shapes` | Reference planes (`OffsetPlane`), points, lines, curves, surfaces |
| **Knowledgeware** | `pycatia3dx.knowledge_interfaces` | Parameters, lengths, angles, and validated Knowledgeware `Formula` relations |
| **Metrology & Inertia** | `pycatia3dx.measure`, `pycatia3dx.inertia` | `MeasureService` / `MeasurableService` (volume, surface area, COG, B-Rep edge/face radii, normals, distances) |
| **Generative Drafting** | `pycatia3dx.drafting`, `pycatia3dx.ecosystem.drafting_helper` | 3D-linked orthographic/isometric views, automated dimensioning, hatching, and PDF export |
| **Product Structure & PLM** | `pycatia3dx.product_structure_client`, `pycatia3dx.vpm_editor_context`, `pycatia3dx.plm_access`, `pycatia3dx.plm_session_builder` | `Physical Product` / `3D Part` creation, instance traversal, PLM search & open |
| **Core Helpers (R2025x–R2027x)** | `pycatia3dx.ecosystem.core_helpers` | Release-safe `open_part_in_physical_product()`, backtick-safe `add_formula()`, CSO-safe `snapshot_topology_refs()`, `constrain_hole_origin()`, `measure_body()` |

---

## Requirements

- **OS:** Windows 10 / 11 for live CATIA COM automation (installable on macOS/Linux for UI development & offline testing)
- **Python:** 3.11+ (**64-bit** on Windows, running at the same privilege level as `3DEXPERIENCE.exe`)
- **CAD:** Dassault Systèmes **3DEXPERIENCE** rich client (R2025x, R2026x, or R2027x — **any UI language**: English, French, German, Spanish, Italian, Japanese, Chinese, etc.)
- **Dependencies:** `pywin32 >= 306` (Windows only), `psutil >= 5.9`

---

## Installation

```bash
git clone https://github.com/AM-DR/3DXPYAM.git
cd 3DXPYAM
pip install -e .
```

For unit tests (offline, no 3DEXPERIENCE license required):

```bash
python -m unittest discover -s tests/unit -v
# or with pytest:
pytest tests/unit
```

---

## Quick Start

```python
from pycatia3dx import (
    CatConstraintMode,
    CatConstraintType,
    ThreeDExperience,
    add_formula,
    measure_body,
    param_name_for_relation,
)
from pycatia3dx.mode.reference import Reference

dx = ThreeDExperience()
editor, part = dx.open_part_in_physical_product()

body = part.main_body
sf = part.shape_factory
ref_xy = Reference(part.origin_elements.plane_xy.com_object)

# Create an iso-constrained (green) centered rectangle sketch
sk = body.sketches.add(ref_xy)
f2d = sk.open_edition()
pts = [(-30.0, -20.0), (30.0, -20.0), (30.0, 20.0), (-30.0, 20.0)]
verts = [f2d.create_point(x, y) for x, y in pts]
lines = []
for i in range(4):
    ln = f2d.create_line(*pts[i], *pts[(i + 1) % 4])
    ln.start_point, ln.end_point = verts[i], verts[(i + 1) % 4]
    lines.append(ln)

ax = sk.absolute_axis
csts = sk.constraints
ref = part.create_reference_from_object
csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(lines[0]))
csts.add_mono_elt_cst(CatConstraintType.catCstTypeHorizontality, ref(lines[2]))
csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(lines[1]))
csts.add_mono_elt_cst(CatConstraintType.catCstTypeVerticality, ref(lines[3]))
csts.add_tri_elt_cst(CatConstraintType.catCstTypeSymmetry, ref(lines[1]), ref(lines[3]), ref(ax.vertical_reference))
csts.add_tri_elt_cst(CatConstraintType.catCstTypeSymmetry, ref(lines[0]), ref(lines[2]), ref(ax.horizontal_reference))
c_len = csts.add_mono_elt_cst(CatConstraintType.catCstTypeLength, ref(lines[0]))
c_len.mode = CatConstraintMode.catCstModeDrivingDimension
c_wid = csts.add_mono_elt_cst(CatConstraintType.catCstTypeLength, ref(lines[1]))
c_wid.mode = CatConstraintMode.catCstModeDrivingDimension
sk.close_edition()

# Extrude & drive pad height with a Knowledgeware formula (height = width / 2)
pad = sf.add_new_pad(sk, 20.0)
add_formula(part, pad.first_limit.dimension, f"({param_name_for_relation(part, c_wid.dimension)}) / 2")
part.update()

measure_svc = editor.get_service("MeasureService")
vol_mm3, area_mm2, cog = measure_body(measure_svc, body)
print(f"Volume = {vol_mm3:,.2f} mm³ | Area = {area_mm2:,.2f} mm² | COG = {cog}")
```

See [`examples/example__parametric_block_r2027x.py`](examples/example__parametric_block_r2027x.py) for a complete runnable script including chamfers, counterbored holes, formulas, and metrology.

---

## R2027x, Multi-Language & UI Compatibility Highlights

- **Any 3DEXPERIENCE UI language:** Command titles are resolved dynamically from 3DEXPERIENCE's own runtime message catalog (`SystemService.GetMessage` via `resolve_command_title()`), drawing views are indexed numerically instead of by English name (`View.1`/`View.2`), hole sketch points are matched by `CatGeometricType.catGeoTypePoint2D`, and PDF export auto-discovers any installed PDF virtual printer.
- **Physical Product + 3D Part workflow (popup-free):** `dx.open_part_in_physical_product()` works cleanly across R2025x–R2027x (`release >= 429`) without triggering blocking `Unknown command` modal dialogs on empty sessions or non-English locales.
- **Safe Knowledgeware formulas:** `add_formula()` uses `Parameters.GetNameToUseInRelation()` so references containing spaces or localized feature names (e.g., `` `Geometrical Set.1\Plane.1\Offset` ``) are properly escaped and validated.
- **CSO-safe B-Rep inspection:** `snapshot_topology_refs()` captures `Selection.Search` references before calling `MeasurableService`, avoiding mid-loop selection resets inside `Physical Product` editors.
- **GUI / Web Backend integration note:** Windows COM is single-threaded (STA). When embedding `3DXPYAM` inside a desktop GUI (Tkinter, PyQt/PySide) or web backend (FastAPI, Flask, Streamlit), run all `ThreeDExperience` calls on a **single dedicated worker thread** so COM objects are never shared across threads.

---

## Credits & License

- **Author / Maintainer:** Drissi Amjad
- **Original Upstream:** [evereux/pycatia3dx](https://github.com/evereux/pycatia3dx) (Paul Bourne)

Licensed under the [MIT License](LICENSE).
