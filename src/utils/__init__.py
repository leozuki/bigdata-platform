# src/utils/__init__.py
# Re-export everything from the original utils.py so that:
#   from src.utils import setup_logger, format_number, clean_phone_number, ...
# still works even though src/utils/ is now a package.

import importlib.util as _ilu, os as _os, sys as _sys

_utils_file = _os.path.join(_os.path.dirname(__file__), "..", "utils.py")
_utils_file = _os.path.normpath(_utils_file)

_spec = _ilu.spec_from_file_location("src._utils_module", _utils_file)
_mod  = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Expose everything from utils.py in this package namespace
from sys import modules as _modules
for _name in dir(_mod):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_mod, _name)
