"""
Unified ``ThreeDExperience`` Hub — Mechanical CAD Entry Point (3DXPYAM).

Provides clean Python automation for:
- **CATIA Part Design, Sketcher, GSD & Knowledgeware** (``dx.catia``, ``dx.client``)
- **Product Structure & R2025x–R2027x Physical Product / 3D Part Creation**
  (``dx.open_part_in_physical_product()``, ``dx.ensure_part()``, ``dx.ensure_product()``)
- **3D-Linked Generative Drafting & PDF Export** (``dx.drafting``)
- **Installation & CATEnv Auto-Discovery** (``dx.discover()``, ``dx.installations()``)
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pycatia3dx.ecosystem.core_helpers import open_part_in_physical_product
from pycatia3dx.ecosystem.discovery import discover_3dx_installations, discover_ecosystem_summary
from pycatia3dx.ecosystem.drafting_helper import DraftingAutomation
from pycatia3dx.ecosystem.universal_client import UniversalClientController, Workbenches

if TYPE_CHECKING:
    from pycatia3dx.interfaces.application import Application


class ThreeDExperience:
    """
    Lightweight Python facade for automating CATIA 3DEXPERIENCE Mechanical CAD.

    Example::

        from pycatia3dx import ThreeDExperience, add_formula, measure_body

        dx = ThreeDExperience()
        editor, part = dx.open_part_in_physical_product()
        body = part.main_body
    """

    workbenches = Workbenches

    def __init__(self, application: Application | None = None):
        self._app = application
        self._client: UniversalClientController | None = None
        self._drafting: DraftingAutomation | None = None

    @property
    def catia(self) -> Application:
        """Connect to the running 3DEXPERIENCE rich client and return :class:`Application`."""
        if self._app is None:
            from pycatia3dx import catia3dx

            self._app = catia3dx()
        return self._app

    def launch(self, *, wait_timeout: float = 120.0) -> Application:
        """
        Connect to ``3DEXPERIENCE.exe`` if already running, or automatically launch
        it from the discovered installation using its ``CATEnv`` and wait until ready.
        """
        if self._app is None:
            from pycatia3dx import catia3dx

            self._app = catia3dx(auto_launch=True, launch_timeout=wait_timeout)
        return self._app

    def open_part_in_physical_product(
        self,
        *,
        reuse_empty: bool = True,
        name: str | None = None,
    ):
        """
        Create (or reuse an empty) ``3D Shape`` inside a ``Physical Product``.

        Supports R2025x–R2027x (``release >= 429``) and **all 3DEXPERIENCE UI
        languages** (resolving localized commands dynamically via NLS catalogs).
        """
        return open_part_in_physical_product(self, self.catia, reuse_empty=reuse_empty, name=name)

    def ensure_part(self, name: str | None = None, *, create_if_missing: bool = True):
        """Return an active ``Part`` automatically (reusing open part, opening by name, or creating one)."""
        return self.client.ensure_part(name=name, create_if_missing=create_if_missing)

    def ensure_drawing(self, name: str | None = None, *, create_if_missing: bool = True):
        """Return an active ``DrawingRoot`` automatically."""
        return self.client.ensure_drawing(name=name, create_if_missing=create_if_missing)

    def ensure_product(self, name: str | None = None, *, create_if_missing: bool = True):
        """Return an active ``VPMRootOccurrence`` automatically."""
        return self.client.ensure_product(name=name, create_if_missing=create_if_missing)

    @property
    def client(self) -> UniversalClientController:
        """Return the rich-client controller (workbenches, macros, PLM, dynamic COM)."""
        if self._client is None:
            self._client = UniversalClientController(application=self._app)
        elif self._app is not None and self._client._app is None:
            self._client._app = self._app
        return self._client

    @property
    def drafting(self) -> DraftingAutomation:
        """Return the high-level 3D-linked Generative Drafting & PDF export controller."""
        if self._drafting is None:
            self._drafting = DraftingAutomation(application=self._app, client=self._client)
        elif self._app is not None and self._drafting._app is None:
            self._drafting._app = self._app
        return self._drafting

    @staticmethod
    def discover() -> dict[str, Any]:
        """Discover local 3DEXPERIENCE installations and ``CATEnv`` configurations."""
        return discover_ecosystem_summary()

    @staticmethod
    def installations():
        """Return structured :class:`ThreeDXInstallation` records found on this machine."""
        return discover_3dx_installations()
