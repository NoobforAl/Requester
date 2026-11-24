"""Benchmarks of hot paths: job matching, the busiest pages, logging overhead.

In the normal suite (``--benchmark-disable``) each runs once, untimed, as a smoke
test. Time them with ``make bench``; ``make bench-check`` fails when a median is 20%
slower than the last saved run (``.benchmarks/``).

Depends on: candidates.matching, the employers/candidates/applications models, the
Django test client, ``tests.factories`` and ``observability.logging_config``.
"""
