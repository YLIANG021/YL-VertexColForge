# -*- coding: utf-8 -*-
"""Small runtime logging helpers.

Normal add-on usage should not write to the console. Keep diagnostics opt-in so
official builds remain quiet unless a developer explicitly enables logging.
"""

import os

DEBUG_ENV_VAR = "YLVC_DEBUG"


def is_debug_enabled():
    return os.environ.get(DEBUG_ENV_VAR, "").lower() in {"1", "true", "yes", "on"}


def debug(message):
    if is_debug_enabled():
        print(message)
