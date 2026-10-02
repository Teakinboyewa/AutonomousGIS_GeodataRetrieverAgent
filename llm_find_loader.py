# -*- coding: utf-8 -*-
"""Load modules from this plugin's LLM_Find folder reliably.

LLM_Find is not a package: its modules are imported by plain name
(``import handbook``). A plain import returns whatever module of that name is
already loaded, which can be a stale copy (an older version of this plugin
loaded earlier in the same QGIS session) or another plugin's module with the
same generic name. ``load`` makes sure this folder's version is the one used.
"""
import importlib
import os
import sys

LLM_FIND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'LLM_Find')


def _is_own(module):
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return False
    return os.path.normcase(os.path.dirname(os.path.abspath(module_file))) == os.path.normcase(LLM_FIND_DIR)


def load(name):
    """Return LLM_Find's ``name`` module, (re)importing it from this plugin if needed."""
    if LLM_FIND_DIR in sys.path:
        sys.path.remove(LLM_FIND_DIR)
    sys.path.insert(0, LLM_FIND_DIR)
    module = sys.modules.get(name)
    if module is None or not _is_own(module):
        sys.modules.pop(name, None)
        module = importlib.import_module(name)
    return module
