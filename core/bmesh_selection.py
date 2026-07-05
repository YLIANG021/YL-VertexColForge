# -*- coding: utf-8 -*-
"""Small bmesh selection helpers."""


def bm_use_face_selection(bm):
    return any(f.select for f in bm.faces)


def bm_face_in_auto_scope(face, use_selection):
    return face.select if use_selection else True
