#!/bin/sh
# Single process running both the Celery worker and the beat scheduler (-B).
# Fine for a single-worker deployment (1 salon). For multiple workers, run
# beat as a separate service instead to avoid duplicate scheduled tasks.
exec celery -A app.tasks.celery_app worker --beat --loglevel=info
