import multiprocessing

# Gunicorn configuration for SafeLensAI
# Usage: gunicorn -c gunicorn_config.py safelensai.wsgi

bind = "0.0.0.0:8000"
workers = 3
worker_class = "sync"
accesslog = "/var/log/gunicorn/access.log"
errorlog = "/var/log/gunicorn/error.log"
loglevel = "info"
timeout = 120
keepalive = 2
capture_output = True
enable_stdio_inheritance = True

