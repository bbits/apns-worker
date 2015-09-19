"""
Datetime utilities to facilitate testing.
"""
from __future__ import unicode_literals, absolute_import


def now():
    """ Public API: import this. """
    return _now()


def _now():
    """ Private API: patch this. """
    import datetime

    return datetime.datetime.now()


def Now(dt):
    """ A context processor that sets the current datetime. """
    from datetime import date, time, datetime
    from mock import patch

    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, time(0))

    return patch('{}._now'.format(__name__), lambda: dt)
