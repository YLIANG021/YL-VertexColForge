# -*- coding: utf-8 -*-
"""Bundled translation data."""

from importlib import import_module
from pathlib import Path


_LOCALE_ALIASES = {
    "de_DE": ("de",),
    "es_ES": ("es",),
    "fr_FR": ("fr",),
    "it_IT": ("it",),
    "ja_JP": ("ja",),
    "ko_KR": ("ko",),
    "pl_PL": ("pl",),
    "pt_BR": ("pt",),
    "ru_RU": ("ru",),
    "vi_VN": ("vi",),
    "zh_CN": ("zh_HANS",),
    "zh_HANS": ("zh_CN",),
    "zh_TW": ("zh_HANT",),
    "zh_HANT": ("zh_TW",),
}


def _discover_locale_modules():
    modules = {}
    package_name = __name__
    locales_dir = Path(__file__).resolve().parent

    for path in locales_dir.glob("*.py"):
        stem = path.stem
        if stem.startswith("_") or stem == "__init__":
            continue
        modules[stem] = import_module(f"{package_name}.{stem}")

    return modules


_LOCALE_MODULES = _discover_locale_modules()


def _build_translations():
    translations = {}
    for lang_code, module in _LOCALE_MODULES.items():
        data = getattr(module, "data", None)
        if not isinstance(data, dict):
            continue
        translations[lang_code] = data
        for alias in _LOCALE_ALIASES.get(lang_code, ()):
            translations.setdefault(alias, data)
    return translations


TRANSLATIONS = _build_translations()
