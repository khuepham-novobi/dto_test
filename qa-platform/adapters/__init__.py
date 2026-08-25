from backend.config import EnvironmentConfig

from .base import OdooAdapter, OdooRPC, OdooRPCError, QA_MARKER
from .odoo17 import Odoo17Adapter
from .odoo19 import Odoo19Adapter

# DataOne migrates Odoo 17 -> Odoo 19. "17" is the baseline the workbook
# captures expectations from; "19" is the target under test.
_BY_VERSION = {"17": Odoo17Adapter, "19": Odoo19Adapter}


def get_adapter(env: EnvironmentConfig) -> OdooAdapter:
    try:
        return _BY_VERSION[str(env.version)](env)
    except KeyError:
        raise ValueError(
            f"No adapter for Odoo version '{env.version}'. "
            f"Known versions: {sorted(_BY_VERSION)}")


__all__ = ["get_adapter", "OdooAdapter", "OdooRPC", "OdooRPCError",
           "QA_MARKER", "Odoo17Adapter", "Odoo19Adapter"]
