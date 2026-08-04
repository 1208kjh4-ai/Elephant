# -*- coding: utf-8 -*-


PICTOGRAM_DEFINITIONS = [
    ("PI_YIELD", u"양보"),
    ("PI_CROSSWALK", u"횡단보도"),
    ("PI_BICYCLE", u"자전거도로"),
    ("PI_BICYCLEONLY", u"자전거우선도로"),
    ("PI_HANDICAPPED_LARGE", u"장애인표지(대형)"),
    ("PI_HANDICAPPED_SMALL", u"장애인표지(소형)"),
]

PICTOGRAM_LAYER_NAMES = set([
    layer_name for layer_name, label in PICTOGRAM_DEFINITIONS
])
PICTOGRAM_LABELS = [
    label for layer_name, label in PICTOGRAM_DEFINITIONS
]
PICTOGRAM_LAYER_BY_LABEL = dict([
    (label, layer_name)
    for layer_name, label in PICTOGRAM_DEFINITIONS
])


def get_layer_name(label):
    return PICTOGRAM_LAYER_BY_LABEL.get(label)

