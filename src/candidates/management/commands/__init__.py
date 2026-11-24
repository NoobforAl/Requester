"""Management commands of the candidates app.

    top_searches   what candidates search for: most searched words, cities, skills.
                   Reads ``JobSearch`` rows through ``candidates.search_log``.
                   ``cd src && python manage.py top_searches``

Depends on: candidates.search_log and candidates.models only.
"""
