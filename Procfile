web: gunicorn app.main:app --workers ${WEB_CONCURRENCY:-2} --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --timeout 120 --access-logfile - --error-logfile -
worker: celery -A app.workers.celery_app.celery_app worker --loglevel=info --concurrency=${WORKER_CONCURRENCY:-2}
