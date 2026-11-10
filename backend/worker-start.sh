#!/bin/sh
# Single process running both the Celery worker and the beat scheduler (-B).
# Fine for a single-worker deployment (1 salon). For multiple workers, run
# beat as a separate service instead to avoid duplicate scheduled tasks.
#
# --pool=solo: tasks run inside the main worker process, no child process.
# Celery's default prefork pool starts one child per CPU core (~48 on
# Railway hosts), each loading the full app → ~2.2 GB RAM always-on; until
# 2026-11-10 this was capped with --concurrency=1, which still kept one
# child alive. Measured locally in the deployment image on 2026-11-10: the
# child's own share was ~32 MB (PSS), the container 121–147 MB with it and
# 124–128 MB without. The salon sends a handful of notifications a day and
# each task takes under a second, so running them one at a time in the main
# process loses nothing.
#
# What solo gives up, checked before switching: no task time limits (none
# are set here; outbound HTTP to Twilio and Brevo has its own 10–15 s
# timeouts) and no recycling of the child after N tasks
# (--max-tasks-per-child, which solo ignores). Memory is watched on Railway
# after the change; if it grows over the days, back to prefork.
exec celery -A app.tasks.celery_app worker --beat \
    --pool=solo \
    --loglevel=info
