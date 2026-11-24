"""Query-count tests: how many SQL queries a page runs at two data sizes.

``scenario.py`` builds a data set that can grow (N=2 versus N=10, or the large
preset) with every field that changes the queries held fixed. A page that runs more
queries at N=10 than at N=2 has an N+1 problem, and the tests fail on that rather
than on timing.

Depends on: the employers, candidates and applications models and ``tests.factories``.
"""
