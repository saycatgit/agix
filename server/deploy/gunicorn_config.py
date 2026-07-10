import os

bind = "127.0.0.1:8000"
workers = 4
worker_class = "sync"
timeout = 30
accesslog = "/var/log/agix-auth/access.log"
errorlog = "/var/log/agix-auth/error.log"
loglevel = "info"
