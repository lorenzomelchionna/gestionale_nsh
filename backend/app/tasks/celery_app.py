from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "new_style_hair",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.reminders"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Rome",
    enable_utc=True,
    beat_schedule={
        # Every 15 min: check upcoming appointments and send reminders
        "send-reminders": {
            "task": "app.tasks.reminders.send_appointment_reminders",
            "schedule": crontab(minute="*/15"),
        },
        # Every day at 09:00 Europe/Rome: send birthday greetings
        "send-birthday-greetings": {
            "task": "app.tasks.reminders.send_birthday_greetings",
            "schedule": crontab(hour=9, minute=0),
        },
    },
)
