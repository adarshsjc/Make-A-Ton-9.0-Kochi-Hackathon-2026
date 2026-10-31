#!/usr/bin/env python
"""Django's command-line utility."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django is not installed. Activate .venv and run: "
            "python -m pip install -r requirements.txt"
        ) from exc
    execute_from_command_line(sys.argv)
