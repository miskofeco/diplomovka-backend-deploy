import os

bind = f"0.0.0.0:{os.getenv('PORT', '5001')}"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "180"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
worker_tmp_dir = "/tmp"
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

