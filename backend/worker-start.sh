#!/bin/sh
# Single process running both the Celery worker and the beat scheduler (-B).
# Fine for a single-worker deployment (1 salon). For multiple workers, run
# beat as a separate service instead to avoid duplicate scheduled tasks.
#
# --concurrency=1: one child process. Celery defaults to one process per CPU
# core (~48 on Railway hosts), each loading the full app → ~2.2 GB RAM
# always-on. This salon sends a handful of notifications a day and each task
# finishes in under a second, so a single child is enough; tasks that arrive
# together just queue behind each other for a moment.
# --max-tasks-per-child=100: recycle the child after 100 tasks to cap leaks.
exec celery -A app.tasks.celery_app worker --beat \
    --concurrency=1 \
    --max-tasks-per-child=100 \
    --loglevel=info
