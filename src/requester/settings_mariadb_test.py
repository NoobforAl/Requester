"""pytest settings that run the suite on a real MariaDB (see `make test-mariadb`)."""

import os

from .settings_test import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "requester"),
        "USER": os.environ.get("DB_ROOT_USER", "root"),
        "PASSWORD": os.environ.get("DB_ROOT_PASSWORD", "requester-dev-root"),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {"charset": "utf8mb4"},
        "TEST": {"NAME": "test_requester"},
    }
}
