"""
Universal 3DEXPERIENCE Rich-Client Controller.

Provides:
- :class:`Workbenches`: App / Workbench IDs across CATIA, SIMULIA, DELMIA,
  ENOVIA, BIOVIA, GEOVIA, and 3DEXCITE.
- :class:`UniversalClientController`: High-level Python driver to switch apps,
  launch commands, evaluate inline VBScript/CATScript/CATVBA macros, query/open/create/save
  PLM entities, automatically ensure an active ``Part``, ``DrawingRoot``, or
  ``VPMRootOccurrence`` without manual GUI clicks, and access *any* session
  service, editor service, or active feature dynamically via
  :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMObject`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping, Sequence

from pycatia3dx import CATScriptLanguage, CatScriptLibraryType
from pycatia3dx.ecosystem.dynamic_com import DynamicCOMObject, unwrap_com_arg, wrap_com_result

if TYPE_CHECKING:
    from pycatia3dx.drafting.drawing_root import DrawingRoot
    from pycatia3dx.interfaces.application import Application
    from pycatia3dx.interfaces.editor import Editor
    from pycatia3dx.interfaces.service import Service
    from pycatia3dx.mmr_automation_interfaces.part import Part
    from pycatia3dx.product_structure_client.vpm_root_occurrence import VPMRootOccurrence


class Workbenches:
    """Common 3DEXPERIENCE App / Workbench identifiers across Dassault Systèmes brands."""

    # CATIA Design & Engineering
    PART_DESIGN = "PrtCfg"
    GENERATIVE_SHAPE_DESIGN = "PKT"
    WIREFRAME_AND_SURFACE = "WksCfg"
    SKETCHER = "CS0Wks"
    ASSEMBLY_DESIGN = "Assembly"
    DRAFTING = "Drw"
    SHEETMETAL_DESIGN = "SmdNewDesignWorkbench"
    COMPOSITES_DESIGN = "CpdConfiguration"
    STRUCTURE_DESIGN = "StrStructureDesignWorkbench"
    ELECTRICAL_3D_DESIGN = "Elec3DConductor"
    PCB_DESIGN = "PCBWorkbench"
    KNOWLEDGE_ADVISOR = "KweWorkbench"
    MECHANICAL_SYSTEMS_DESIGN = "KinematicsWorkbench"
    NATURAL_SKETCH = "CATNaturalSketchWkb"
    IMA_SUBDIVISION = "CATImaWorkbench"

    # SIMULIA In-Client Apps
    SIM_MECHANICAL_SCENARIO = "SimMechanicalScenarioCreation"
    SIM_STRUCTURAL_SCENARIO = "SimStructuralScenarioCreation"
    SIM_STRUCTURAL_SCENARIO_ESSENTIAL = "SMAExsEssentialMechanicsApp"
    SIM_LINEAR_STRUCTURAL_SCENARIO = "SimLinearStructuralScenarioCreation"
    SIM_LINEAR_STRUCTURAL_VALIDATION = "SimLinearStructuralValidation"
    SIM_FEM_MODEL = "FmtModelAssembly"
    SIM_PHYSICS_RESULTS = "SimResultsWorkbench"
    SIM_RESULTS_EXPLORER = "SMAHvcStructureResultsWorkbench"

    # DELMIA Manufacturing, Robotics, & Ergonomics
    DELMIA_ROBOTICS_OLP = "DNBIgpOlpUseWkbench"
    DELMIA_ROBOT_TASK = "DELRobotSimulationWkb"
    DELMIA_ARC_WELDING = "DNBIgpArcWeldingUseWkbench"
    DELMIA_SPOT_WELDING = "DELSpotWeldingWkb"
    DELMIA_FITTING = "DNBFittingWorkbench"
    DELMIA_PRISMATIC_MACHINING = "PmgWorkbench"
    DELMIA_SURFACE_MACHINING = "SmgWorkbench"
    DELMIA_ERGONOMICS = "HumanBuilder"

    # ENOVIA / Digital Mockup / Review
    DMU_SECTIONING = "OpnsSectionWkb"
    DMU_INTERFERENCE = "InterferenceCheckWkb"
    PLM_VALIDATION = "VALValidationWkb"


def _walk_part_from_reference(vpm_ref: Any, max_depth: int = 4) -> Part | None:
    """Recursively locate the first ``Part`` inside a ``VPMReference`` hierarchy."""
    if max_depth < 0 or vpm_ref is None:
        return None
    from pycatia3dx.mmr_automation_interfaces.part import Part
    from pycatia3dx.product_structure_client.vpm_instance import VPMInstance

    try:
        reps = vpm_ref.rep_instances
        for idx in range(1, reps.count + 1):
            try:
                part_obj = reps.item(idx).reference_instance_of.get_item("Part")
                if part_obj is not None and hasattr(part_obj, "com_object"):
                    return Part(part_obj.com_object)
            except Exception:
                continue
    except Exception:
        pass

    try:
        insts = vpm_ref.instances
        for idx in range(1, insts.count + 1):
            try:
                inst = VPMInstance(insts.item(idx).com_object)
                found = _walk_part_from_reference(inst.reference_instance_of, max_depth - 1)
                if found is not None:
                    return found
            except Exception:
                continue
    except Exception:
        pass

    return None


def extract_part_from_editor(editor: Editor | None) -> Part | None:
    """
    Extract a :class:`~pycatia3dx.mmr_automation_interfaces.part.Part` from
    ``editor`` if it is a ``3DShape`` editor or a ``3DPart`` / ``VPMReference``
    product editor containing a shape representation (including nested
    ``Physical Product -> 3D Part -> 3D Shape`` hierarchies). Returns ``None``
    when the editor is the Welcome Page (``Page d'accueil``) or a non-part document.
    """
    if editor is None:
        return None
    from pycatia3dx.mmr_automation_interfaces.part import Part
    from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService

    try:
        active_com = editor.active_com_object
        if active_com is not None and hasattr(active_com, "MainBody"):
            return Part(active_com)
    except Exception:
        pass

    try:
        plm_prod_svc = editor.get_service("PLMProductService")
        if not isinstance(plm_prod_svc, PLMProductService):
            plm_prod_svc = PLMProductService(plm_prod_svc.com_object)
        root_occ = plm_prod_svc.root_occurrence
        vpm_ref = root_occ.reference_root_occurrence_of
        return _walk_part_from_reference(vpm_ref, max_depth=4)
    except Exception:
        pass

    return None


class UniversalClientController:
    """
    Universal controller for the 3DEXPERIENCE rich client, enabling Python automation
    across CATIA, SIMULIA, DELMIA, ENOVIA, BIOVIA, GEOVIA, and 3DEXCITE apps.
    """

    def __init__(self, application: Application | None = None):
        self._app = application

    @property
    def application(self) -> Application:
        if self._app is None:
            from pycatia3dx import catia3dx

            self._app = catia3dx()
        return self._app

    @property
    def active_editor(self) -> Editor:
        return self.application.active_editor

    def active_object(self) -> DynamicCOMObject:
        """Return the active PLM/CAD/Simulation/Manufacturing object as a ``DynamicCOMObject``."""
        return DynamicCOMObject(self.application.active_editor.active_com_object)

    def current_workbench(self) -> str:
        """Return the active 3DEXPERIENCE app / workbench identifier."""
        return self.application.get_workbench_id()

    def switch_workbench(self, workbench_id: str) -> None:
        """Activate any 3DEXPERIENCE app/workbench by ID (see :class:`Workbenches`)."""
        self.application.start_workbench(workbench_id)

    def run_command(self, command_id: str) -> None:
        """Trigger a one-shot 3DEXPERIENCE command header by ID or localized title."""
        self.application.start_command(command_id)

    def session_service(self, service_id: str) -> Service:
        """
        Retrieve *any* session-level service (typed wrapper if known, or
        :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMService` automatically).
        """
        return self.application.get_session_service(service_id)

    def editor_service(self, service_id: str, *, editor: Editor | None = None) -> Service:
        """
        Retrieve *any* editor-level service (typed wrapper if known, or
        :class:`~pycatia3dx.ecosystem.dynamic_com.DynamicCOMService` automatically).
        """
        target_editor = editor or self.application.active_editor
        return target_editor.get_service(service_id)

    # ------------------------------------------------------------------
    # Inline VBScript / CATScript / Macro Execution
    # ------------------------------------------------------------------
    def evaluate_vbscript(
        self,
        function_code: str,
        function_name: str,
        params: Sequence[Any] = (),
    ) -> Any:
        """Evaluate a VBScript ``Function`` inside the 3DEXPERIENCE scripting engine."""
        unwrapped = [unwrap_com_arg(p) for p in params]
        res = self.application.system_service.evaluate(
            function_code,
            CATScriptLanguage.CATVBScriptLanguage,
            function_name,
            unwrapped,
        )
        return wrap_com_result(res)

    def evaluate_catscript(
        self,
        function_code: str,
        function_name: str,
        params: Sequence[Any] = (),
    ) -> Any:
        """Evaluate a CATScript procedure/function inside 3DEXPERIENCE."""
        unwrapped = [unwrap_com_arg(p) for p in params]
        res = self.application.system_service.evaluate(
            function_code,
            CATScriptLanguage.CATBasicScriptLanguage,
            function_name,
            unwrapped,
        )
        return wrap_com_result(res)

    def run_inline_vbscript(self, statements: str, *args: Any) -> Any:
        """
        Execute arbitrary VBScript statements inside 3DEXPERIENCE without boilerplate.

        Inside ``statements``:
        - ``CATIA`` is available globally.
        - Arguments passed via ``*args`` are bound as ``arg0``, ``arg1``, ...
        - Assign ``RESULT = ...`` (or ``Set RESULT = ...``) to return a value to Python.
        """
        arg_names = [f"arg{i}" for i in range(len(args))]
        sig = ", ".join(arg_names)
        indented = "\n".join(f"    {ln}" for ln in statements.splitlines())
        vb_code = (
            f"Function pycatiaInline({sig})\n"
            f"    Dim RESULT\n"
            f"    RESULT = Empty\n"
            f"{indented}\n"
            f"    If IsObject(RESULT) Then\n"
            f"        Set pycatiaInline = RESULT\n"
            f"    Else\n"
            f"        pycatiaInline = RESULT\n"
            f"    End If\n"
            f"End Function"
        )
        return self.evaluate_vbscript(vb_code, "pycatiaInline", args)

    def run_macro_file(
        self,
        library_name: str,
        program_name: str,
        function_name: str = "CATMain",
        params: Sequence[Any] = (),
        *,
        library_type: int = CatScriptLibraryType.catScriptLibraryTypeDirectory,
    ) -> Any:
        """Execute an external ``.catvbs``, ``.CATScript``, or ``.catvba`` macro."""
        unwrapped = [unwrap_com_arg(p) for p in params]
        res = self.application.system_service.execute_script(
            library_name,
            library_type,
            program_name,
            function_name,
            unwrapped,
        )
        return wrap_com_result(res)

    # ------------------------------------------------------------------
    # High-level PLM Session Helpers (Search / Open / Create / Save / Refresh)
    # ------------------------------------------------------------------
    def search_plm(
        self,
        *,
        base_type: str | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> list[DynamicCOMObject]:
        """Search PLM database inside the rich client via ``Search`` session service."""
        from pycatia3dx.plm_access.search_service import SearchService

        svc = self.session_service("Search")
        search_svc = svc if isinstance(svc, SearchService) else SearchService(svc.com_object)
        db_search = search_svc.database_search
        if base_type:
            db_search.base_type = base_type
        db_search.all_minor_versions = True
        if attributes:
            for attr_id, attr_val in attributes.items():
                db_search.add_easy_criteria(attr_id, attr_val)
        search_svc.search()
        entities = db_search.results
        return [DynamicCOMObject(entities.item(i).com_object) for i in range(1, entities.count + 1)]

    def open_plm_object(self, plm_entity: Any) -> Editor:
        """Open a searched ``PLMEntity`` into an authoring ``Editor`` via ``PLMOpenService``."""
        open_svc = self.session_service("PLMOpenService")
        raw_entity = unwrap_com_arg(plm_entity)
        try:
            open_svc.com_object.PLMOpen(raw_entity)
            return self.application.active_editor
        except Exception:
            vb_code = (
                "Function pycatia_plm_open(openSvc, entity)\n"
                "    Dim edt\n"
                "    openSvc.PLMOpen entity, edt\n"
                "    Set pycatia_plm_open = edt\n"
                "End Function"
            )
            edt = self.evaluate_vbscript(vb_code, "pycatia_plm_open", [open_svc, raw_entity])
            if edt is None:
                return self.application.active_editor
            from pycatia3dx.interfaces.editor import Editor

            return Editor(unwrap_com_arg(edt))

    def create_plm_entity(
        self,
        plm_type: str = "3DShape",
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Editor:
        """
        Create a new PLM authoring object (e.g. ``'3DShape'``, ``'3DPart'``,
        ``'VPMReference'``, ``'Drawing'``) and return its ``Editor``.
        """
        from pycatia3dx.interfaces.editor import Editor
        from pycatia3dx.plm_session_builder.plm_new_service import PLMNewService

        svc = self.session_service("PLMNewService")
        new_svc = svc if isinstance(svc, PLMNewService) else PLMNewService(svc.com_object)
        if name:
            try:
                new_svc.set_attribute_value("V_Name", name)
            except Exception:
                pass
        if description:
            try:
                new_svc.set_attribute_value("V_description", description)
            except Exception:
                pass

        try:
            return new_svc.plm_create(plm_type)
        except Exception:
            vb_code = (
                "Function pycatiaPlmNew(newSvc, plmType)\n"
                "    Dim edt\n"
                "    newSvc.PLMCreate plmType, edt\n"
                "    Set pycatiaPlmNew = edt\n"
                "End Function"
            )
            edt = self.evaluate_vbscript(vb_code, "pycatiaPlmNew", [new_svc, plm_type])
            if edt is None:
                return self.application.active_editor
            return Editor(unwrap_com_arg(edt))

    def ensure_part(
        self,
        name: str | None = None,
        *,
        create_if_missing: bool = True,
    ) -> Part:
        """
        Return a ready-to-use :class:`~pycatia3dx.mmr_automation_interfaces.part.Part`
        without requiring the user to manually open or create a document first:

        1. Checks the currently active editor (skipping the Welcome Page / ``Page d'accueil``).
        2. Scans all other open windows and activates a matching ``3DShape`` / ``3DPart``.
        3. If ``name`` is specified, searches the PLM database and opens it.
        4. If none is open and ``create_if_missing=True``, automatically creates a
           new ``3DShape`` (or ``3DPart``) in the session and returns its ``Part``.
        """
        app = self.application

        def _win_matches(win_name: str) -> bool:
            if not name:
                return True
            return win_name == name or win_name.startswith(name + " ")

        # 1. Check active editor first
        try:
            active_win = app.active_window
            if active_win and _win_matches(active_win.name):
                part = extract_part_from_editor(app.active_editor)
                if part is not None:
                    return part
        except Exception:
            pass

        # 2. Scan all open windows
        try:
            windows = list(app.windows)
        except Exception:
            windows = []

        for win in windows:
            try:
                if not _win_matches(win.name):
                    continue
                win.activate()
                part = extract_part_from_editor(app.active_editor)
                if part is not None:
                    return part
            except Exception:
                continue

        # 3. Search in PLM database if name was given
        if name:
            for base_type in ("3DShape", "VPMReference"):
                try:
                    found = self.search_plm(base_type=base_type, attributes={"V_Name": name})
                    if found:
                        edt = self.open_plm_object(found[0])
                        part = extract_part_from_editor(edt)
                        if part is not None:
                            return part
                except Exception:
                    continue

        if not create_if_missing:
            raise RuntimeError(
                f"No open 3DPart/3DShape found{f' matching {name!r}' if name else ''} "
                f"and create_if_missing=False."
            )

        # 4. Automatically create a new 3DShape (falling back to 3DPart)
        for create_type in ("3DShape", "3DPart"):
            try:
                edt = self.create_plm_entity(create_type, name=name)
                part = extract_part_from_editor(edt)
                if part is not None:
                    return part
            except Exception:
                continue

        raise RuntimeError("Could not obtain or create a Part in the active 3DEXPERIENCE session.")

    def ensure_drawing(
        self,
        name: str | None = None,
        *,
        create_if_missing: bool = True,
    ) -> DrawingRoot:
        """
        Return a ready-to-use :class:`~pycatia3dx.drafting.drawing_root.DrawingRoot`
        (reusing an open drawing, opening ``name`` from PLM, or creating a new
        ``Drawing`` with a default sheet and view if none is open).
        """
        from pycatia3dx.drafting.drawing_root import DrawingRoot

        app = self.application

        def _extract_drawing(editor: Editor | None) -> DrawingRoot | None:
            if editor is None:
                return None
            try:
                com_obj = editor.active_com_object
                if com_obj is not None and hasattr(com_obj, "Sheets"):
                    return DrawingRoot(com_obj)
            except Exception:
                pass
            return None

        # 1. Check active editor
        try:
            drw = _extract_drawing(app.active_editor)
            if drw is not None and (not name or app.active_window.name.startswith(name)):
                return drw
        except Exception:
            pass

        # 2. Check open windows
        try:
            for win in app.windows:
                if name and not win.name.startswith(name):
                    continue
                win.activate()
                drw = _extract_drawing(app.active_editor)
                if drw is not None:
                    return drw
        except Exception:
            pass

        # 3. Search PLM if name provided
        if name:
            try:
                found = self.search_plm(base_type="Drawing", attributes={"V_Name": name})
                if found:
                    edt = self.open_plm_object(found[0])
                    drw = _extract_drawing(edt)
                    if drw is not None:
                        return drw
            except Exception:
                pass

        if not create_if_missing:
            raise RuntimeError("No open Drawing found and create_if_missing=False.")

        edt = self.create_plm_entity("Drawing", name=name)
        drw = _extract_drawing(edt)
        if drw is None:
            drw = DrawingRoot(edt.active_com_object)
        try:
            if drw.sheets.count == 0:
                sheet = drw.sheets.add("Sheet.1")
                if sheet.views.count == 0:
                    sheet.views.add("Main View")
        except Exception:
            pass
        return drw

    def ensure_product(
        self,
        name: str | None = None,
        *,
        create_if_missing: bool = True,
    ) -> VPMRootOccurrence:
        """
        Return a ready-to-use :class:`~pycatia3dx.product_structure_client.vpm_root_occurrence.VPMRootOccurrence`
        (reusing an open product editor, searching/opening ``name``, or creating a new
        ``VPMReference`` / ``3DPart`` automatically).
        """
        from pycatia3dx.vpm_editor_context.plm_product_service import PLMProductService

        app = self.application

        def _extract_root_occ(editor: Editor | None) -> VPMRootOccurrence | None:
            if editor is None:
                return None
            try:
                svc = editor.get_service("PLMProductService")
                prod_svc = svc if isinstance(svc, PLMProductService) else PLMProductService(svc.com_object)
                return prod_svc.root_occurrence
            except Exception:
                return None

        try:
            occ = _extract_root_occ(app.active_editor)
            if occ is not None and (not name or app.active_window.name.startswith(name)):
                return occ
        except Exception:
            pass

        if name:
            try:
                found = self.search_plm(base_type="VPMReference", attributes={"V_Name": name})
                if found:
                    edt = self.open_plm_object(found[0])
                    occ = _extract_root_occ(edt)
                    if occ is not None:
                        return occ
            except Exception:
                pass

        if not create_if_missing:
            raise RuntimeError("No open Product found and create_if_missing=False.")

        for create_type in ("VPMReference", "3DPart"):
            try:
                edt = self.create_plm_entity(create_type, name=name)
                occ = _extract_root_occ(edt)
                if occ is not None:
                    return occ
            except Exception:
                continue

        raise RuntimeError("Could not obtain or create a VPMRootOccurrence in 3DEXPERIENCE.")

    def save_session(self) -> None:
        """Propagate / save modified PLM objects in the session to 3DSpace."""
        prop_svc = self.session_service("PLMPropagateService")
        try:
            prop_svc.com_object.PLMPropagate()
        except Exception:
            prop_svc.com_object.Save()

    def refresh_session(self) -> None:
        """Refresh open PLM objects from 3DSpace."""
        ref_svc = self.session_service("PLMRefreshService")
        DynamicCOMObject(ref_svc.com_object).perform_refresh()
