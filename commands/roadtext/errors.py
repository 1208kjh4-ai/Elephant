# -*- coding: utf-8 -*-


class RoadTextError(Exception):
    """An error whose message can be shown directly to the Rhino user."""

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message_text = message

