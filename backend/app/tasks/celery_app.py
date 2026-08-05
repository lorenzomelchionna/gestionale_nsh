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
    # Accodare un task non deve poter bloccare una richiesta HTTP.
    #
    # Ogni `.delay()` dell'app è fire-and-forget dentro un `try/except`: se il
    # broker non c'è, la prenotazione o la vendita restano registrate e la
    # notifica salta. Ma con i default di Celery `.delay()` **ritenta** con
    # backoff prima di sollevare, quindi con Redis irraggiungibile la
    # richiesta resta appesa per decine di secondi — visto in locale
    # emettendo un buono regalo con Redis spento. L'eccezione arrivava, solo
    # troppo tardi per essere utile: alla cassa c'è qualcuno che aspetta.
    #
    # `task_publish_retry=False` fa fallire subito la pubblicazione, e i due
    # timeout limitano la connessione TCP. Insieme trasformano un'attesa
    # indefinita in un paio di secondi.
    task_publish_retry=False,
    broker_transport_options={
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
    },
    # Vale per il worker all'avvio, non per chi pubblica: il worker deve
    # aspettare Redis, altrimenti un riavvio simultaneo dei due servizi lo
    # farebbe morire prima che il broker sia pronto. Impostarlo esplicitamente
    # toglie anche la deprecation che Celery 6 stampa a ogni boot.
    broker_connection_retry_on_startup=True,
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
