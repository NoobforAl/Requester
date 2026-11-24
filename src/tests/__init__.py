"""Cross-app tests: a whole site built from fake data, query counts, benchmarks.

Per-app tests live next to the code (``<app>/tests.py``, ``test_*.py``). This package
holds what spans every app, so it may import all of them.

    conftest.py   fixtures that build a ``seed_fake_data`` site once per module
                  (marker ``fakedata``; deselect with ``-m 'not fakedata'``).
    factories.py  Faker builders (``make_employer``, ``make_posting``, ...), seeded
                  with ``factories.seed(n)``; they reuse ``applications.fake_data``.
    test_fake_data_invariants.py, test_pages_fake_data.py, test_seed_fake_data.py
                  the generated data is consistent and every page renders on it.
    perf/         query-count tests at two data sizes.
    benchmarks/   pytest-benchmark timings (also smoke tests in the normal run).

Depends on: employers, candidates, applications (models, fake_data, commands) and
the shared fixtures in src/conftest.py. Nothing outside this package imports it.
"""
