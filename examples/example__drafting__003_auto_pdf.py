"""
Example - Drafting - 003 (Automated 3D-Linked Generative Drawing & PDF Export)

Description:
    Demonstrates the high-level ``dx.drafting`` automation helper in 3DXPYAM
    (pycatia3dx) to automatically generate a complete ISO A4 technical drawing
    with true 3D-linked Generative Views (Front, Projection, Section A-A,
    Section B-B, Isometric), ISO title block, annotations, and direct PDF export
    from any open Physical Product (``VPMReference`` + ``3DShape``).

Requirements:
    - 3DEXPERIENCE running with an open Physical Product containing a 3DShape.
"""

from pathlib import Path
from pycatia3dx import ThreeDExperience


def main():
    dx = ThreeDExperience()

    # 1. Create an ISO A4 Landscape drawing linked to the open Physical Product
    dwg = dx.drafting.create_technical_drawing(
        drawing_name="Auto_3D_Technical_Drawing",
        standard="ISO",
        paper_size="A4",
        orientation="landscape",
        first_angle=True,
        scale=1.0,
    )

    # 2. Add ISO frame, zone grid, and title block in Background View
    dwg.add_iso_title_block(
        title="AUTOMATED TECHNICAL DRAWING",
        organization="3DXPYAM / pycatia3dx",
        author="Drissi Amjad",
        scale_label="1:1",
        paper_label="A4",
        sheet_number="1/1",
        first_angle=True,
    )

    # 3. Create true 3D-linked Generative Views
    front = dwg.add_front_view(70.0, 95.0, plane=(1.0, 0.0, 0.0, 0.0, 0.0, 1.0))
    left = dwg.add_projection_view(140.0, 95.0, front, "left")
    top = dwg.add_projection_view(140.0, 160.0, left, "bottom")
    iso = dwg.add_isometric_view(220.0, 155.0)

    # 4. Generate associative 3D dimensions and auto-arrange them without overlaps
    dwg.generate_and_arrange_dimensions(remove_duplicates=True, color_black=True)

    # 5. Export directly to PDF
    out_pdf = Path.cwd() / "technical_drawing.pdf"
    dwg.export_pdf(out_pdf)
    print(f"Exported 3D-linked technical drawing PDF to: {out_pdf}")


if __name__ == "__main__":
    main()
