"""The configuration for the backend application.

Task 2 changes this module to a ``pydantic-settings`` class. It then adds
``RECALL_API_KEY``, ``OPENAI_API_KEY`` and the database path, and it reads
``CORS_ORIGINS`` from the environment.
"""

# The browser origins that can call this API. 
#
# Task 2 makes this value an environment variable. The list below stays as the
# default.
CORS_ORIGINS = [
    "https://recall.samneet.com",  # The deployed Cloudflare Worker.
    "http://localhost:8787",  # wrangler dev, the default port.
    "http://127.0.0.1:8787",  # The same server, the other loopback name.
]

CORS_METHODS = ["GET", "POST", "OPTIONS"]
CORS_HEADERS = ["Authorization", "Content-Type"]
