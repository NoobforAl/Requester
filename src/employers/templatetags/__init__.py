"""Template tags package (Django loads ``filters.py`` as ``{% load filters %}``).

    localdate     date as ``YYYY-MM-DD`` in the visitor's calendar (Jalali for
                  Persian, Gregorian otherwise), via ``requester.localdates``.
    salary_label  ``30,000 - 50,000 EUR`` for a posting; empty without a salary.

Depends on: requester.localdates. Used by: the templates.
"""
