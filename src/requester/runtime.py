"""Facts about the box the process runs in (used to size worker pools)."""

import math
import os
from pathlib import Path


def _cgroup_cpu_quota() -> float | None:
    """CPU limit from the container's cgroup (``docker --cpus``), None if unlimited."""
    try:  # cgroup v2: "<quota> <period>" or "max <period>"
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()[:2]
        return None if quota == "max" else int(quota) / int(period)
    except (OSError, ValueError):
        pass
    try:  # cgroup v1
        quota_us = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        period_us = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
        return None if quota_us <= 0 else quota_us / period_us
    except (OSError, ValueError):
        return None


def container_cpu_count() -> int:
    """CPUs this process can really use.

    ``os.cpu_count()`` reports the host's CPUs even inside a container capped with
    ``--cpus``, so pools sized from it (gunicorn workers, Celery prefork children)
    start far too many processes and run out of memory. A fractional quota rounds up.
    """
    affinity = getattr(os, "sched_getaffinity", None)  # Linux only
    available = len(affinity(0)) if affinity else (os.cpu_count() or 1)
    quota = _cgroup_cpu_quota()
    if quota is None:
        return available
    return max(1, min(available, math.ceil(quota)))
