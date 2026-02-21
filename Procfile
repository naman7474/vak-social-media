web: uvicorn vak_bot.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: celery -A vak_bot.workers.celery_app.celery_app worker -Q pipeline,maintenance --loglevel=info
beat: celery -A vak_bot.workers.celery_app.celery_app beat --loglevel=info
