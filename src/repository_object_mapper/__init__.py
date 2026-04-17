"""repository-object-mapper: empirical pipeline for measuring article embeddedness
in open access repositories.

This package implements the v0.2 paper-submittable minimum described in the
project specification. Public re-exports here are deliberately narrow; import
from submodules for everything else.
"""

from __future__ import annotations

__version__ = "0.2.0"
SCHEMA_VERSION = "0.2"

__all__ = ["SCHEMA_VERSION", "__version__"]
