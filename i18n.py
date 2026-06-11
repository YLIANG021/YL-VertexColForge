# -*- coding: utf-8 -*-
import importlib

import bpy

from .core.logging import debug
from .paths import locales_dir

_TRANSLATION_DOMAIN = __package__ or __name__
_TRANSLATIONS = {}
_LOCALE_ALIASES = {
    "es": ("es_ES",),
    "es_ES": ("es",),
    "pt": ("pt_BR",),
    "pt_BR": ("pt", "pt_PT"),
    "pt_PT": ("pt_BR",),
    "zh_CN": ("zh_HANS",),
    "zh_TW": ("zh_HANT",),
    "zh_HANS": ("zh_CN",),
    "zh_HANT": ("zh_TW",),
}


def load_all_locales():
    global _TRANSLATIONS
    _TRANSLATIONS = {}

    directory = locales_dir()
    if not directory.exists():
        return _TRANSLATIONS

    for file_path in sorted(directory.glob("*.py")):
        if file_path.stem == "__init__":
            continue

        lang_code = file_path.stem
        module_name = f"{__package__}.locales.{lang_code}" if __package__ else f"locales.{lang_code}"

        try:
            module = importlib.import_module(module_name)
            module = importlib.reload(module)
        except Exception as exc:
            debug(f"YLVC i18n: failed to load locale '{lang_code}': {exc}")
            continue

        data = getattr(module, "data", None)
        if isinstance(data, dict):
            _TRANSLATIONS[lang_code] = data
            for alias in _LOCALE_ALIASES.get(lang_code, ()):
                _TRANSLATIONS.setdefault(alias, data)
        else:
            debug(f"YLVC i18n: locale '{lang_code}' has no valid data dict")

    return _TRANSLATIONS


def register():
    load_all_locales()
    try:
        bpy.app.translations.unregister(_TRANSLATION_DOMAIN)
    except Exception:
        pass

    try:
        bpy.app.translations.register(_TRANSLATION_DOMAIN, _TRANSLATIONS)
    except Exception as exc:
        debug(f"YLVC i18n: register failed: {exc}")


def unregister():
    try:
        bpy.app.translations.unregister(_TRANSLATION_DOMAIN)
    except Exception:
        pass


def tr(msgid):
    try:
        return bpy.app.translations.pgettext_iface(msgid)
    except Exception:
        return msgid


def tr_format(msgid, **kwargs):
    translated = tr(msgid)
    try:
        return translated.format(**kwargs)
    except Exception:
        try:
            return msgid.format(**kwargs) if kwargs else msgid
        except Exception:
            return translated
