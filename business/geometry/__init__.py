"""Governed physical geometry derivation.

Dev Order: SMART-GUITAR-CAVITY-GEOMETRY-1

Cavity dimensions are computed from a component register rather than asserted,
so a cavity can never drift from the parts it has to hold.
"""

from business.geometry.cavity_derivation import (
    derive_cavity,
    derive_cavity_geometry,
    derive_required_body_thickness,
)
from business.geometry.models import (
    ComponentRegisterV1,
    SmartGuitarCavityGeometryV1,
)

__all__ = [
    "ComponentRegisterV1",
    "SmartGuitarCavityGeometryV1",
    "derive_cavity",
    "derive_cavity_geometry",
    "derive_required_body_thickness",
]
