# -*- coding: utf-8 -*-
"""Legacy command-level helpers kept for namespace compatibility."""


def almost_equal(a, b, tolerance=1e-8):
    return abs(a - b) <= tolerance
