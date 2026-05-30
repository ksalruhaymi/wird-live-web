import os

app_env = os.getenv("APP_ENV")

if not app_env:
    app_env = "dev"

app_env = app_env.lower()

if app_env == "prod":
    from .prod import *
elif app_env == "dev":
    from .dev import *
else:
    raise RuntimeError(f"Unknown APP_ENV: {app_env}")