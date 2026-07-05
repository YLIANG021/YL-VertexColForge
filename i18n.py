# -*- coding: utf-8 -*-
"""Translation registration helpers."""

import bpy

from .locales import TRANSLATIONS


_TRANSLATION_DOMAIN = __package__ or __name__


def register():
    try:
        bpy.app.translations.unregister(_TRANSLATION_DOMAIN)
    except Exception:
        pass

    try:
        bpy.app.translations.register(_TRANSLATION_DOMAIN, TRANSLATIONS)
    except Exception:
        pass


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
