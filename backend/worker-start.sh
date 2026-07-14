#!/bin/sh
# Single process running both the Celery worker and the beat scheduler (-B).
# Fine for a single-worker deployment (1 salon). For multiple workers, run
# beat as a separate service instead to avoid duplicate scheduled tasks.
#
# --concurrency=2: only 2 child processes. Celery defaults to one process per
# CPU core (~48 on Railway hosts), each loading the full app → ~2.2 GB RAM
# always-on. A single salon sends a handful of notifications, so 2 is plenty
# and cuts memory (and cost) dramatically.
# --max-tasks-per-child=100: recycle a child after 100 tasks to cap memory leaks.
exec celery -A app.tasks.celery_app worker --beat \
    --concurrency=2 \
    --max-tasks-per-child=100 \
    --loglevel=info
