"""Run slow work (AI calls) after the current transaction commits, off the request thread.

A daemon thread is enough at our volume. Swap this one function for a task queue later
without touching callers.
"""
import logging
import threading

from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)


def run_after_commit(func, *args):
    transaction.on_commit(lambda: threading.Thread(target=_run, args=(func, *args), daemon=True).start())


def _run(func, *args):
    close_old_connections()
    try:
        func(*args)
    except Exception:
        logger.exception("Background task %s failed", getattr(func, "__name__", func))
    finally:
        close_old_connections()
