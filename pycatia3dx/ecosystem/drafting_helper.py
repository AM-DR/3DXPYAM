"""
High-Level 3D-Linked Generative Drafting & PDF Export Automation for 3DEXPERIENCE.

Allows any ``pycatia3dx`` / ``3dxpy`` user to generate a complete ISO technical
drawing (with true 3D-linked generative views, section cuts, title block,
annotations/dimensions, and direct PDF export) from an open Physical Product
(``VPMReference`` / ``VPMRootOccurrence``) in just a few lines of Python.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Sequence

from pycatia3dx.annotation.drawing_dimension import DrawingDimension
from pycatia3dx.annotation.drawing_text_properties import DrawingTextProperties
from pycatia3dx.annotation.enums import CatDimLineRep, CatDimType, CatTextAnchorPosition
from pycatia3dx.drafting.drawing_gen_service import DrawingGenService
from pycatia3dx.drafting.drawing_root import DrawingRoot
from pycatia3dx.drafting.drawing_view import DrawingView
from pycatia3dx.drafting.enums import CatProjViewType, CatSheetProjectionMethod
from pycatia3dx.interfaces.enums import CatPaperOrientation, CatPaperSize


_PAPER_SIZES: dict[str, tuple[int, float, float]] = {
    "A0": (CatPaperSize.catPaperA0, 1189.0, 841.0),
    "A1": (CatPaperSize.catPaperA1, 841.0, 594.0),
    "A2": (CatPaperSize.catPaperA2, 594.0, 420.0),
    "A3": (CatPaperSize.catPaperA3, 420.0, 297.0),
    "A4": (CatPaperSize.catPaperA4, 297.0, 210.0),
}

_PROJ_DIRS: dict[str, int] = {
    "right": CatProjViewType.catRightView,
    "left": CatProjViewType.catLeftView,
    "top": CatProjViewType.catTopView,
    "bottom": CatProjViewType.catBottomView,
    "rear": CatProjViewType.catRearView,
}


def _set_vis_style(sel, items: Sequence[Any], *, width: int | None = None, line_type: int | None = None) -> None:
    if not items:
        return
    # Skip redundant CSO mutations for CATIA's default thin solid style (width=1, line_type=1)
    if (width is None or width == 1) and (line_type is None or line_type == 1):
        return
    sel_com = getattr(sel, "com_object", sel)
    try:
        sel_com.Clear()
        for it in items:
            sel_com.Add(getattr(it, "com_object", it))
        vp = sel_com.VisProperties
        if width is not None and width != 1:
            vp.SetRealWidth(int(width), 1)
        if line_type is not None and line_type != 1:
            vp.SetRealLineType(int(line_type), 1)
    finally:
        try:
            sel_com.Clear()
        except Exception:
            pass


def _add_poly(f2d, pts: Sequence[tuple[float, float]], *, closed: bool = True, bucket: list | None = None) -> list:
    segs = []
    n = len(pts)
    count = n if closed else n - 1
    for i in range(count):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if abs(x2 - x1) < 1e-6 and abs(y2 - y1) < 1e-6:
            continue
        ln = f2d.create_line(float(x1), float(y1), float(x2), float(y2))
        segs.append(ln)
        if bucket is not None:
            bucket.append(ln)
    return segs


def _add_text(
    texts,
    content: str,
    x: float,
    y: float,
    *,
    size: float = 2.8,
    anchor: int = CatTextAnchorPosition.catMiddleCenter,
    bold: bool = False,
    angle: float = 0.0,
):
    txt = texts.add(content, float(x), float(y))
    if abs(angle) > 1e-6:
        txt.angle = float(angle)
    tp = DrawingTextProperties(txt.com_object.TextProperties)
    tp.font_size = float(size)
    tp.anchor_point = anchor
    if bold:
        tp.bold = 1
    tp.update()
    return txt


class TechnicalDrawingBuilder:
    """
    Builder for an associative CATIA 3DEXPERIENCE ``Drawing`` linked to a 3D
    Physical Product (``VPMRootOccurrence``).
    """

    def __init__(
        self,
        application,
        editor,
        drawing_root: DrawingRoot,
        root_occurrence,
        *,
        width: float = 297.0,
        height: float = 210.0,
    ):
        self.app = application
        self.editor = editor
        self.drawing_root = drawing_root
        self.sheet = drawing_root.active_sheet
        self.views = self.sheet.views
        self.root_occurrence = root_occurrence
        self.link = (root_occurrence,)
        self.width = width
        self.height = height

        self._dgs = DrawingGenService(
            self.app.get_session_service("CATDrawingGenService").com_object
        )
        self._ddgv = self.views.drawing_define_gen_view
        self._gen_view_prop = self._dgs.drawing_gen_view_prop
        self._sel = self.editor.selection

    # ------------------------------------------------------------------
    # ISO Border & Title Block (Background View)
    # ------------------------------------------------------------------
    def add_iso_title_block(
        self,
        *,
        title: str,
        organization: str = "",
        author: str = "",
        date_str: str = "",
        scale_label: str = "1:1",
        paper_label: str = "A4",
        sheet_number: str = "1/1",
        note: str = "Generated with 3dxpy (pycatia3dx)",
        first_angle: bool = True,
    ) -> None:
        """Draw an ISO frame, zone grid (D-C-B-A / 4-3-2-1), and title block in View.2."""
        bg_view = DrawingView(self.views.item("View.2").com_object)
        bg_view.activate()
        f_bg = bg_view.factory_2d
        t_bg = bg_view.texts

        W, H, M = self.width, self.height, 10.0
        thick: list = []
        thin: list = []

        # Outer & inner border
        _add_poly(f_bg, [(0, 0), (W, 0), (W, H), (0, H)], closed=True, bucket=thin)
        _add_poly(f_bg, [(M, M), (W - M, M), (W - M, H - M), (M, H - M)], closed=True, bucket=thick)

        # Zone grid markers
        cols = ["D", "C", "B", "A"]
        rows = ["1", "2", "3", "4"]
        cw = (W - 2 * M) / 4.0
        rh = (H - 2 * M) / 4.0
        for idx, ch in enumerate(cols):
            cx = M + (idx + 0.5) * cw
            _add_text(t_bg, ch, cx, H - M * 0.5, size=3.2)
            _add_text(t_bg, ch, cx, M * 0.5, size=3.2)
            if idx > 0:
                x_div = M + idx * cw
                _add_poly(f_bg, [(x_div, M), (x_div, M - 4.0)], closed=False, bucket=thin)
                _add_poly(f_bg, [(x_div, H - M), (x_div, H - M + 4.0)], closed=False, bucket=thin)
        for idx, rn in enumerate(rows):
            ry = M + (idx + 0.5) * rh
            _add_text(t_bg, rn, M * 0.5, ry, size=3.2)
            _add_text(t_bg, rn, W - M * 0.5, ry, size=3.2)
            if idx > 0:
                y_div = M + idx * rh
                _add_poly(f_bg, [(M, y_div), (M - 4.0, y_div)], closed=False, bucket=thin)
                _add_poly(f_bg, [(W - M, y_div), (W - M + 4.0, y_div)], closed=False, bucket=thin)

        # Title block in bottom-right corner (180 mm wide x 48 mm tall)
        tx1 = W - M
        tx0 = max(M, tx1 - 180.0)
        ty0 = M
        ty1 = M + 48.0
        c1 = tx0 + 45.0
        c2 = tx1 - 25.0
        _add_poly(f_bg, [(tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1)], closed=True, bucket=thick)
        _add_poly(f_bg, [(c1, ty0), (c1, ty1)], closed=False, bucket=thin)
        _add_poly(f_bg, [(c2, ty0), (c2, ty1)], closed=False, bucket=thin)
        _add_poly(f_bg, [(tx0, ty0 + 22.0), (c2, ty0 + 22.0)], closed=False, bucket=thin)
        _add_poly(f_bg, [(tx0, ty0 + 11.0), (c2, ty0 + 11.0)], closed=False, bucket=thin)
        _add_poly(f_bg, [(tx0, ty0 + 35.0), (c1, ty0 + 35.0)], closed=False, bucket=thin)
        _add_poly(f_bg, [(tx0 + 18.0, ty0), (tx0 + 18.0, ty0 + 22.0)], closed=False, bucket=thin)
        _add_poly(f_bg, [(c2 - 22.0, ty0), (c2 - 22.0, ty0 + 11.0)], closed=False, bucket=thin)

        # Projection symbol (ISO First-Angle / Third-Angle)
        sx = tx0 + 22.0
        sy = ty0 + 16.5
        if first_angle:
            _add_poly(f_bg, [(sx, sy - 2.0), (sx + 6.0, sy - 3.5), (sx + 6.0, sy + 3.5), (sx, sy + 2.0)], closed=True, bucket=thin)
            f_bg.create_circle(sx + 14.0, sy, 3.5, 0.0, 2.0 * math.pi)
            f_bg.create_circle(sx + 14.0, sy, 1.8, 0.0, 2.0 * math.pi)
        else:
            f_bg.create_circle(sx + 4.0, sy, 3.5, 0.0, 2.0 * math.pi)
            f_bg.create_circle(sx + 4.0, sy, 1.8, 0.0, 2.0 * math.pi)
            _add_poly(f_bg, [(sx + 11.0, sy - 2.0), (sx + 17.0, sy - 3.5), (sx + 17.0, sy + 3.5), (sx + 11.0, sy + 2.0)], closed=True, bucket=thin)

        # Texts
        _add_text(t_bg, "DESIGNED BY:", tx0 + 2.0, ty1 - 1.5, size=1.7, anchor=CatTextAnchorPosition.catTopLeft)
        if author:
            _add_text(t_bg, author, tx0 + 22.5, ty1 - 6.0, size=2.8)
        if date_str:
            _add_text(t_bg, f"DATE: {date_str}", tx0 + 2.0, ty0 + 36.2, size=1.8, anchor=CatTextAnchorPosition.catBottomLeft)
        _add_text(t_bg, "CHECKED BY:", tx0 + 2.0, ty0 + 33.8, size=1.7, anchor=CatTextAnchorPosition.catTopLeft)
        _add_text(t_bg, "SIZE", tx0 + 9.0, ty0 + 19.5, size=1.7)
        _add_text(t_bg, paper_label, tx0 + 9.0, ty0 + 14.5, size=3.4, bold=True)
        _add_text(t_bg, "SCALE", tx0 + 9.0, ty0 + 8.5, size=1.7)
        _add_text(t_bg, scale_label, tx0 + 9.0, ty0 + 3.5, size=3.2, bold=True)

        title_cx = (c1 + c2) / 2.0
        _add_text(t_bg, title, title_cx, ty0 + 35.0, size=4.6, bold=True)
        if organization:
            _add_text(t_bg, organization, title_cx, ty0 + 16.5, size=3.8)
        _add_text(t_bg, "SHEET", c2 - 11.0, ty0 + 8.5, size=1.7)
        _add_text(t_bg, sheet_number, c2 - 11.0, ty0 + 3.5, size=2.9)
        if note:
            _add_text(t_bg, note, (c1 + (c2 - 22.0)) / 2.0, ty0 + 5.5, size=2.1)

        # Revision rows
        for k, lettre in enumerate(["A", "B", "C", "D", "E", "F", "G"]):
            yk = ty0 + 3.4 + k * 6.4
            if k < 6:
                _add_poly(f_bg, [(c2, ty0 + (k + 1) * 6.4), (tx1, ty0 + (k + 1) * 6.4)], closed=False, bucket=thin)
            _add_text(t_bg, f"{lettre}   -", (c2 + tx1) / 2.0, yk, size=2.2)

        try:
            self.sheet.update()
        except Exception:
            pass
        fresh_sel = self.editor.selection
        _set_vis_style(fresh_sel, thick, width=3, line_type=1)
        _set_vis_style(fresh_sel, thin, width=1, line_type=1)

        # Reactivate main working view
        DrawingView(self.views.item("View.1").com_object).activate()

    # ------------------------------------------------------------------
    # True 3D-Linked Generative Views
    # ------------------------------------------------------------------
    def _configure_view_caption(
        self,
        view: DrawingView,
        caption: str | None,
        show_caption: bool,
        caption_pos: tuple[float, float] | None = None,
    ) -> None:
        view.frame_visualization = False
        if not show_caption and caption is None:
            while view.texts.count > 0:
                view.texts.remove(1)
        elif caption is not None and view.texts.count > 0:
            t0 = view.texts.item(1)
            t0.text = caption
            if caption_pos is not None:
                t0.x = float(caption_pos[0])
                t0.y = float(caption_pos[1])

    def add_front_view(
        self,
        x: float,
        y: float,
        *,
        plane: tuple[float, float, float, float, float, float] = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
        caption: str | None = None,
        show_caption: bool = False,
    ) -> DrawingView:
        """Create a true 3D-linked Generative Front View."""
        view = self._ddgv.define_front_view(
            float(x), float(y), self.link, plane, "", False, self._gen_view_prop
        )
        view.drawing_gen_view.put_links(1, self.link)
        view.drawing_gen_view.update()
        self._configure_view_caption(view, caption, show_caption)
        return view

    def add_projection_view(
        self,
        x: float,
        y: float,
        parent_view: DrawingView,
        direction: str | int = "left",
        *,
        unalign: bool = False,
        caption: str | None = None,
        show_caption: bool = False,
    ) -> DrawingView:
        """Create a true 3D-linked Generative Projection View (left/right/top/bottom/rear)."""
        proj_type = _PROJ_DIRS[direction.lower()] if isinstance(direction, str) else int(direction)
        view = self._ddgv.define_projection_view(
            float(x), float(y), parent_view, proj_type, "", True, self._gen_view_prop
        )
        if unalign:
            view.un_aligned_with_reference_view()
            view.x_axis_data = float(x)
            view.y_axis_data = float(y)
        self._configure_view_caption(view, caption, show_caption)
        return view

    def add_section_view(
        self,
        x: float,
        y: float,
        parent_view: DrawingView,
        profile: Sequence[float],
        *,
        side: int = 0,
        section_type: str = "SectionView",
        profile_type: str = "CatOffsetSectionProfile",
        unalign: bool = False,
        caption: str | None = None,
        show_caption: bool = True,
        caption_pos: tuple[float, float] | None = None,
    ) -> DrawingView:
        """Create a true 3D-linked Generative Section View (with automatic CATIA hatching & callouts)."""
        view = self._ddgv.define_section_view(
            float(x),
            float(y),
            tuple(float(v) for v in profile),
            section_type,
            profile_type,
            int(side),
            parent_view,
            "",
            True,
            self._gen_view_prop,
        )
        if unalign:
            view.un_aligned_with_reference_view()
            view.x_axis_data = float(x)
            view.y_axis_data = float(y)
        self._configure_view_caption(view, caption, show_caption, caption_pos=caption_pos)
        return view

    def add_isometric_view(
        self,
        x: float,
        y: float,
        *,
        plane: tuple[float, float, float, float, float, float] = (
            0.70710678,
            -0.70710678,
            0.0,
            0.40824829,
            0.40824829,
            0.81649658,
        ),
        caption: str | None = None,
        show_caption: bool = False,
    ) -> DrawingView:
        """Create a true 3D-linked Generative Isometric View."""
        view = self._ddgv.define_isometric_view(
            float(x), float(y), self.link, plane, "", False, self._gen_view_prop
        )
        view.drawing_gen_view.put_links(1, self.link)
        view.drawing_gen_view.update()
        self._configure_view_caption(view, caption, show_caption)
        return view

    # ------------------------------------------------------------------
    # Native CATIA DrawingDimension Objects & 3D Associative Dimensions
    # ------------------------------------------------------------------
    def _hide_elements(self, elements: Sequence[Any]) -> None:
        if not elements:
            return
        self._sel.clear()
        for el in elements:
            self._sel.add(el)
        self._sel.vis_properties.set_show(1)  # catVisPropertyNoShowAttr
        self._sel.clear()

    def set_dimensions_color(self, dims: Sequence[DrawingDimension], rgb: tuple[int, int, int] = (0, 0, 0)) -> None:
        """Set visual color (default ISO black) on one or more CATIA ``DrawingDimension`` objects."""
        if not dims:
            return
        self._sel.clear()
        for d in dims:
            self._sel.add(d)
        self._sel.vis_properties.set_real_color(int(rgb[0]), int(rgb[1]), int(rgb[2]), 1)
        self._sel.clear()

    def generate_dimensions(self) -> None:
        """Invoke CATIA's associative 3D-to-2D ``GenerateDimensions`` across the sheet."""
        self.sheet.generate_dimensions()
        self.sheet.update()

    def generate_dimensions_for_view(
        self,
        view: DrawingView,
        *,
        selector=None,
        color_black: bool = True,
    ) -> list[DrawingDimension]:
        """
        Generate 100% genuine 3D-associative dimensions exclusively onto ``view``
        by temporarily locking all other generative views on the sheet and calling
        CATIA's native ``sheet.generate_dimensions()``.

        Parameters
        ----------
        view:
            Target ``DrawingView`` that should receive the 3D-linked dimensions.
        selector:
            Optional callable ``selector(dim, dim_type, value, bbox)`` called for
            each generated dimension on ``view``:
            - Return ``None`` or ``False`` to discard the dimension.
            - Return ``True`` to keep it at CATIA's default position.
            - Return ``(tx, ty)`` to keep it and place its value at ``(tx, ty)``.
            - Return a ``dict`` supporting ``pos=(tx, ty)``, ``prefix`` (str),
              ``suffix`` (str), ``symbols_side`` (int) to keep and style it.
        color_black:
            If ``True``, set the kept dimensions to crisp ISO black ``(0, 0, 0)``.
        """
        gen_views = [
            DrawingView(self.views.item(i).com_object)
            for i in range(3, self.views.count + 1)
        ]
        prev_locks = [v.lock_status for v in gen_views]
        target_name = view.name
        try:
            for v in gen_views:
                v.lock_status = (v.name != target_name)
            self.sheet.generate_dimensions()
            self.sheet.update()
        finally:
            for v, prev in zip(gen_views, prev_locks):
                v.lock_status = prev

        kept: list[DrawingDimension] = []
        to_remove: list[int] = []
        for idx in range(1, view.dimensions.count + 1):
            d = view.dimensions.item(idx)
            if selector is None:
                kept.append(d)
                continue
            dt = int(d.dim_type)
            val = float(d.get_value().value)
            try:
                bx = tuple(float(c) for c in d.get_boundary_box())
            except Exception:
                bx = ()
            decision = selector(d, dt, val, bx)
            if decision is None or decision is False:
                to_remove.append(idx)
                continue
            if isinstance(decision, dict):
                if "prefix" in decision or "suffix" in decision:
                    d.get_value().set_bault_text(
                        1,
                        str(decision.get("prefix", "")),
                        str(decision.get("suffix", "")),
                        "",
                        "",
                    )
                if "symbols_side" in decision:
                    d.symbols_side = int(decision["symbols_side"])
                if "pos" in decision and decision["pos"] is not None:
                    tx, ty = decision["pos"]
                    d.move_value(float(tx), float(ty), 0, 0)
            elif isinstance(decision, (tuple, list)) and len(decision) == 2:
                d.move_value(float(decision[0]), float(decision[1]), 0, 0)
            kept.append(d)

        for idx in reversed(to_remove):
            view.dimensions.remove(idx)

        if color_black and kept:
            self.set_dimensions_color(kept, (0, 0, 0))
        return kept

    def generate_and_arrange_dimensions(
        self,
        *,
        views: Sequence[DrawingView] | None = None,
        remove_duplicates: bool = True,
        ignore_values: Sequence[float] = (),
        color_black: bool = True,
        margin: float = 6.0,
        step: float = 6.5,
    ) -> list[DrawingDimension]:
        """
        Invoke CATIA's associative 3D-to-2D ``GenerateDimensions()``, optionally
        remove duplicate/unwanted dimensions, and automatically space out the
        resulting genuine CATIA ``DrawingDimension`` objects around each view's
        bounding box so they do not pile on top of each other.
        """
        self.sheet.generate_dimensions()
        self.sheet.update()

        target_views = list(views) if views is not None else [
            DrawingView(self.views.item(i).com_object)
            for i in range(3, self.views.count + 1)
        ]

        kept: list[DrawingDimension] = []
        for view in target_views:
            # Remove ignored or duplicate dimensions (iterate backwards when removing)
            seen_keys: set[tuple[int, float]] = set()
            to_remove: list[int] = []
            for idx in range(1, view.dimensions.count + 1):
                d = view.dimensions.item(idx)
                val = round(float(d.get_value().value), 3)
                if any(abs(val - ig) < 1e-2 for ig in ignore_values):
                    to_remove.append(idx)
                    continue
                key = (int(d.dim_type), val)
                if remove_duplicates and key in seen_keys:
                    to_remove.append(idx)
                else:
                    seen_keys.add(key)

            for idx in reversed(to_remove):
                view.dimensions.remove(idx)

            if view.dimensions.count == 0:
                continue

            # Determine local view bounding box relative to the view's axis origin
            try:
                xmin, xmax, ymin, ymax = view.size()
                lx0 = xmin - view.x_axis_data
                lx1 = xmax - view.x_axis_data
                ly0 = ymin - view.y_axis_data
                ly1 = ymax - view.y_axis_data
            except Exception:
                lx0, lx1, ly0, ly1 = -20.0, 20.0, -10.0, 30.0

            cx = (lx0 + lx1) / 2.0
            cy = (ly0 + ly1) / 2.0

            # Fan out dimensions neatly across top, right, bottom, left slots
            slot_counts = {"top": 0, "right": 0, "bottom": 0, "left": 0}
            view_dims: list[DrawingDimension] = []
            for idx in range(1, view.dimensions.count + 1):
                d = view.dimensions.item(idx)
                dt = int(d.dim_type)
                # Angles/Radii/Diameters -> top or left; Distances -> right or bottom
                if dt in (4, 5, 6, 9, 10, 11):
                    side = "top" if slot_counts["top"] <= slot_counts["left"] else "left"
                else:
                    side = "right" if slot_counts["right"] <= slot_counts["bottom"] else "bottom"

                k = slot_counts[side]
                slot_counts[side] += 1

                if side == "top":
                    tx, ty = lx0 + 4.0 + k * 14.0, ly1 + margin + (k % 2) * step
                elif side == "right":
                    tx, ty = lx1 + margin + k * step, cy + (k - 1) * 4.5
                elif side == "bottom":
                    tx, ty = cx + (k - 1) * 12.0, ly0 - margin - (k % 2) * step
                else:
                    tx, ty = lx0 - margin - k * step, cy + (k - 1) * 5.0

                try:
                    d.move_value(float(tx), float(ty), 0, 0)
                except Exception:
                    pass
                view_dims.append(d)

            if color_black and view_dims:
                self.set_dimensions_color(view_dims, (0, 0, 0))
            kept.extend(view_dims)

        self.sheet.update()
        return kept

    def add_dimension(
        self,
        view: DrawingView,
        p1: tuple[float, float],
        p2: tuple[float, float],
        pos: tuple[float, float],
        *,
        vertical: bool = False,
        prefix: str = "",
        suffix: str = "",
        black: bool = True,
    ) -> DrawingDimension:
        """
        Create a genuine native CATIA ``DrawingDimension`` (distance) inside ``view``
        between 2D local points ``p1`` and ``p2``, positioned at ``pos``.
        """
        view.activate()
        f2d = view.factory_2d
        pt1 = f2d.create_point(float(p1[0]), float(p1[1]))
        pt2 = f2d.create_point(float(p2[0]), float(p2[1]))
        self._hide_elements((pt1, pt2))

        rep = CatDimLineRep.catDimVert if vertical else CatDimLineRep.catDimHoriz
        dim = view.dimensions.add(
            CatDimType.catDimDistance,
            (pt1, pt2),
            (float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1])),
            rep,
        )
        if prefix or suffix:
            dim.get_value().set_bault_text(1, prefix, suffix, "", "")
        dim.move_value(float(pos[0]), float(pos[1]), 0, 0)
        if black:
            self.set_dimensions_color((dim,), (0, 0, 0))
        return dim

    def add_diameter_dimension(
        self,
        view: DrawingView,
        center: tuple[float, float],
        radius: float,
        pos: tuple[float, float],
        *,
        touch_angle_deg: float = 135.0,
        black: bool = True,
    ) -> DrawingDimension:
        """Create a genuine native CATIA diameter ``DrawingDimension`` inside ``view``."""
        view.activate()
        f2d = view.factory_2d
        cx, cy = float(center[0]), float(center[1])
        r = float(radius)
        circ = f2d.create_closed_circle(cx, cy, r)
        self._hide_elements((circ,))

        ang = math.radians(touch_angle_deg)
        sx, sy = cx + r * math.cos(ang), cy + r * math.sin(ang)
        dim = view.dimensions.add(
            CatDimType.catDimDiameter,
            (circ,),
            (sx, sy),
            CatDimLineRep.catDimAuto,
        )
        dim.move_value(float(pos[0]), float(pos[1]), 0, 0)
        if black:
            self.set_dimensions_color((dim,), (0, 0, 0))
        return dim

    def add_radius_dimension(
        self,
        view: DrawingView,
        center: tuple[float, float],
        radius: float,
        pos: tuple[float, float],
        *,
        touch_angle_deg: float = 45.0,
        black: bool = True,
    ) -> DrawingDimension:
        """Create a genuine native CATIA radius ``DrawingDimension`` inside ``view``."""
        view.activate()
        f2d = view.factory_2d
        cx, cy = float(center[0]), float(center[1])
        r = float(radius)
        circ = f2d.create_closed_circle(cx, cy, r)
        self._hide_elements((circ,))

        ang = math.radians(touch_angle_deg)
        sx, sy = cx + r * math.cos(ang), cy + r * math.sin(ang)
        dim = view.dimensions.add(
            CatDimType.catDimRadius,
            (circ,),
            (sx, sy),
            CatDimLineRep.catDimAuto,
        )
        dim.move_value(float(pos[0]), float(pos[1]), 0, 0)
        if black:
            self.set_dimensions_color((dim,), (0, 0, 0))
        return dim

    def add_angle_dimension(
        self,
        view: DrawingView,
        vertex: tuple[float, float],
        angle1_deg: float,
        angle2_deg: float,
        pos: tuple[float, float],
        *,
        leg_length: float = 10.0,
        black: bool = True,
    ) -> DrawingDimension:
        """Create a genuine native CATIA angle ``DrawingDimension`` inside ``view``."""
        view.activate()
        f2d = view.factory_2d
        vx, vy = float(vertex[0]), float(vertex[1])
        a1, a2 = math.radians(angle1_deg), math.radians(angle2_deg)
        x1, y1 = vx + leg_length * math.cos(a1), vy + leg_length * math.sin(a1)
        x2, y2 = vx + leg_length * math.cos(a2), vy + leg_length * math.sin(a2)
        l1 = f2d.create_line(vx, vy, x1, y1)
        l2 = f2d.create_line(vx, vy, x2, y2)
        self._hide_elements((l1, l2))

        dim = view.dimensions.add(
            CatDimType.catDimAngle,
            (l1, l2),
            (x1, y1, x2, y2),
            CatDimLineRep.catDimAuto,
        )
        dim.move_value(float(pos[0]), float(pos[1]), 0, 0)
        if black:
            self.set_dimensions_color((dim,), (0, 0, 0))
        return dim

    def add_linear_dimension(
        self,
        view: DrawingView,
        p1: tuple[float, float],
        p2: tuple[float, float],
        *,
        line_pos: float,
        label: str,
        vertical: bool = False,
        text_offset: tuple[float, float] = (0.0, 0.0),
        font_size: float = 2.6,
    ) -> None:
        """Add a clean ISO linear dimension anchored in the generative view's local 2D frame."""
        view.activate()
        f2d = view.factory_2d
        texts = view.texts
        thin: list = []
        x1, y1 = p1
        x2, y2 = p2

        if vertical:
            tx = float(line_pos)
            sgn1 = 1.0 if tx >= x1 else -1.0
            sgn2 = 1.0 if tx >= x2 else -1.0
            thin.append(f2d.create_line(float(x1 + sgn1 * 0.8), float(y1), float(tx + sgn1 * 1.5), float(y1)))
            thin.append(f2d.create_line(float(x2 + sgn2 * 0.8), float(y2), float(tx + sgn2 * 1.5), float(y2)))
            ya, yb = min(y1, y2), max(y1, y2)
            if yb - ya >= 5.0:
                thin.append(f2d.create_line(tx, float(ya), tx, float(yb)))
                for ye, dy in [(ya, 1.0), (yb, -1.0)]:
                    thin.append(f2d.create_line(tx, float(ye), tx - 0.5, float(ye + dy * 1.7)))
                    thin.append(f2d.create_line(tx, float(ye), tx + 0.5, float(ye + dy * 1.7)))
            else:
                thin.append(f2d.create_line(tx, float(ya - 3.5), tx, float(yb + 3.5)))
                for ye, dy in [(ya, -1.0), (yb, 1.0)]:
                    thin.append(f2d.create_line(tx, float(ye), tx - 0.5, float(ye + dy * 1.7)))
                    thin.append(f2d.create_line(tx, float(ye), tx + 0.5, float(ye + dy * 1.7)))
            _add_text(
                texts,
                label,
                tx + text_offset[0],
                (ya + yb) / 2.0 + text_offset[1],
                size=font_size,
                angle=math.pi / 2.0,
            )
        else:
            ty = float(line_pos)
            sgn1 = 1.0 if ty >= y1 else -1.0
            sgn2 = 1.0 if ty >= y2 else -1.0
            thin.append(f2d.create_line(float(x1), float(y1 + sgn1 * 0.8), float(x1), float(ty + sgn1 * 1.5)))
            thin.append(f2d.create_line(float(x2), float(y2 + sgn2 * 0.8), float(x2), float(ty + sgn2 * 1.5)))
            xa, xb = min(x1, x2), max(x1, x2)
            if xb - xa >= 5.0:
                thin.append(f2d.create_line(float(xa), ty, float(xb), ty))
                for xe, dx in [(xa, 1.0), (xb, -1.0)]:
                    thin.append(f2d.create_line(float(xe), ty, float(xe + dx * 1.7), ty - 0.5))
                    thin.append(f2d.create_line(float(xe), ty, float(xe + dx * 1.7), ty + 0.5))
            else:
                thin.append(f2d.create_line(float(xa - 3.5), ty, float(xb + 3.5), ty))
                for xe, dx in [(xa, -1.0), (xb, 1.0)]:
                    thin.append(f2d.create_line(float(xe), ty, float(xe + dx * 1.7), ty - 0.5))
                    thin.append(f2d.create_line(float(xe), ty, float(xe + dx * 1.7), ty + 0.5))
            _add_text(
                texts,
                label,
                (xa + xb) / 2.0 + text_offset[0],
                ty + text_offset[1],
                size=font_size,
            )

        _set_vis_style(self._sel, thin, width=1, line_type=1)

    def add_leader(
        self,
        view: DrawingView,
        point: tuple[float, float],
        knee: tuple[float, float],
        end: tuple[float, float],
        label: str,
        *,
        font_size: float = 2.6,
        text_dy: float = 1.8,
    ) -> None:
        """Add an ISO leader arrow and text annotation anchored inside ``view``."""
        view.activate()
        f2d = view.factory_2d
        texts = view.texts
        px, py = point
        kx, ky = knee
        ex, ey = end
        dx, dy = kx - px, ky - py
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        nx, ny = -uy, ux
        thin = [
            f2d.create_line(float(px), float(py), float(kx), float(ky)),
            f2d.create_line(float(kx), float(ky), float(ex), float(ey)),
            f2d.create_line(float(px), float(py), float(px + ux * 1.7 + nx * 0.5), float(py + uy * 1.7 + ny * 0.5)),
            f2d.create_line(float(px), float(py), float(px + ux * 1.7 - nx * 0.5), float(py + uy * 1.7 - ny * 0.5)),
        ]
        _add_text(texts, label, (kx + ex) / 2.0, ey + text_dy, size=font_size)
        _set_vis_style(self._sel, thin, width=1, line_type=1)

    def add_section_hatching(
        self,
        view: DrawingView,
        points: Sequence[tuple[float, float]],
        *,
        step: float = 1.6,
    ) -> list:
        """
        Draw clean ISO 45-degree thin hatching lines inside ``points`` (in
        ``view`` local 2D coordinates) when CATIA's default section hatch pitch
        is too wide for thin-walled parts.
        """
        view.activate()
        f2d = view.factory_2d
        n = len(points)
        c_min = min(x - y for x, y in points) + step * 0.5
        c_max = max(x - y for x, y in points) - step * 0.5
        lines: list = []
        c = c_min
        while c <= c_max:
            ts: list[tuple[float, float, float]] = []
            for i in range(n):
                x1, y1 = points[i]
                x2, y2 = points[(i + 1) % n]
                d1 = x1 - y1 - c
                d2 = x2 - y2 - c
                if (d1 <= 0.0 < d2) or (d2 <= 0.0 < d1):
                    u = -d1 / (d2 - d1)
                    xi = x1 + u * (x2 - x1)
                    yi = y1 + u * (y2 - y1)
                    ts.append((xi + yi, xi, yi))
            ts.sort(key=lambda item: item[0])
            for k in range(0, len(ts) - 1, 2):
                _, xi1, yi1 = ts[k]
                _, xi2, yi2 = ts[k + 1]
                if math.hypot(xi2 - xi1, yi2 - yi1) > 0.25:
                    lines.append(f2d.create_line(float(xi1), float(yi1), float(xi2), float(yi2)))
            c += step
        _set_vis_style(self._sel, lines, width=1, line_type=1)
        return lines

    def add_area_fill(
        self,
        view: DrawingView,
        points: Sequence[tuple[float, float]],
        *,
        pattern: str = "alu 30",
    ):
        """
        Add a native CATIA ``DrawingAreaFill`` hatching region inside ``view``
        using a standard hatching pattern (e.g. ``"alu 30"``).
        """
        view.activate()
        flat: list[float] = []
        for x, y in points:
            flat.extend([float(x), float(y)])
        af = view.area_fills.add((len(points),), tuple(flat))
        if pattern:
            try:
                af.set_pattern(pattern)
            except Exception:
                pass
        return af

    # ------------------------------------------------------------------
    # Direct PDF Export
    # ------------------------------------------------------------------
    def export_pdf(
        self,
        output_path: str | os.PathLike,
        *,
        printer_name: str = "Microsoft Print to PDF",
    ) -> Path:
        """Export the active CATIA Drawing Sheet directly to a PDF file."""
        self.sheet.update()
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()

        pdf_printer = self.app.printers.item(printer_name)
        self.app.active_printer = pdf_printer

        ps = self.sheet.page_setup
        ps.choose_best_orientation = False
        ps.orientation = self.sheet.orientation
        ps.fit_to_sheet_format = True

        self.sheet.print_to_file(str(out))
        return out


class DraftingAutomation:
    """
    Entry point exposed as ``dx.drafting`` on :class:`~pycatia3dx.hub.ThreeDExperience`.
    """

    def __init__(self, application=None, client=None):
        self._app = application
        self._client = client

    @property
    def app(self):
        if self._app is None:
            from pycatia3dx import catia3dx

            self._app = catia3dx()
        return self._app

    @property
    def client(self):
        if self._client is None:
            from pycatia3dx.ecosystem.universal_client import UniversalClientController

            self._client = UniversalClientController(application=self.app)
        return self._client

    @staticmethod
    def _has_3d_shape(vpm_ref, depth: int = 0) -> bool:
        if depth > 4:
            return False
        try:
            if vpm_ref.rep_instances.count > 0:
                return True
        except Exception:
            pass
        try:
            insts = vpm_ref.instances
            for idx in range(1, insts.count + 1):
                child_ref = insts.item(idx).reference_instance_of
                if DraftingAutomation._has_3d_shape(child_ref, depth + 1):
                    return True
        except Exception:
            pass
        return False

    def find_active_product(self, name_hint: str | None = None):
        """
        Locate an open Physical Product (``VPMRootOccurrence``) that contains
        at least one 3D representation (directly or in a nested R2027x child
        instance) and passes CATIA's generative view link integrity check.
        """
        dgs = DrawingGenService(self.app.get_session_service("CATDrawingGenService").com_object)
        candidates = []

        for i in range(1, self.app.windows.count + 1):
            win = self.app.windows.item(i)
            if name_hint and name_hint.lower() not in win.name.lower():
                continue
            try:
                win.activate()
                ed = self.app.active_editor
                ps = ed.get_service("PLMProductService")
                root_occ = ps.root_occurrence
                vpm_ref = root_occ.reference_root_occurrence_of
                if self._has_3d_shape(vpm_ref) and dgs.check_view_link_integrity((root_occ,)):
                    candidates.append((win.name, root_occ))
            except Exception:
                continue

        if not candidates:
            raise RuntimeError(
                "No open Physical Product (VPMReference) with a 3DShape was found in 3DEXPERIENCE. "
                "Open or create a Physical Product containing your 3DShape first."
            )
        return candidates[-1][1]

    def create_technical_drawing(
        self,
        *,
        drawing_name: str = "Technical_Drawing",
        product_name_hint: str | None = None,
        root_occurrence=None,
        standard: str = "ISO",
        paper_size: str = "A4",
        orientation: str = "landscape",
        first_angle: bool = True,
        scale: float = 1.0,
    ) -> TechnicalDrawingBuilder:
        """
        Create a new CATIA 3DEXPERIENCE ``Drawing`` linked to the open Physical
        Product and return a :class:`TechnicalDrawingBuilder`.
        """
        if root_occurrence is None:
            root_occurrence = self.find_active_product(name_hint=product_name_hint)

        size_enum, w_mm, h_mm = _PAPER_SIZES[paper_size.upper()]
        is_landscape = orientation.lower().startswith("land")
        if not is_landscape:
            w_mm, h_mm = h_mm, w_mm

        ed_draw = self.client.create_plm_entity("Drawing", name=drawing_name)
        draw_root = DrawingRoot(ed_draw.active_object.com_object)
        draw_root.standard = standard

        sheet = draw_root.active_sheet
        sheet.paper_size = size_enum
        sheet.orientation = (
            CatPaperOrientation.catPaperLandscape if is_landscape else CatPaperOrientation.catPaperPortrait
        )
        sheet.projection_method = (
            CatSheetProjectionMethod.catFirstAngle if first_angle else CatSheetProjectionMethod.catThirdAngle
        )
        sheet.scale = float(scale)
        sheet.activate()

        return TechnicalDrawingBuilder(
            self.app,
            ed_draw,
            draw_root,
            root_occurrence,
            width=w_mm,
            height=h_mm,
        )
