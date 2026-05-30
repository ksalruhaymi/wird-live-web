import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / ""


def create_app(app_name: str):
    app_dir = SRC_DIR / app_name
    templates_dir = app_dir / "templates" / app_name

    if app_dir.exists():
        print(f"❌ App '{app_name}' already exists.")
        return

    # إنشاء المجلدات
    templates_dir.mkdir(parents=True)

    # ملفات أساسية
    files = {
        "__init__.py": "",
        "apps.py": f"""from django.apps import AppConfig


class {app_name.capitalize()}Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "{app_name}"
""",
        "models.py": "from django.db import models\n",
        "views.py": "from django.shortcuts import render\n",
        "urls.py": "from django.urls import path\n\nurlpatterns = []\n",
        "admin.py": "from django.contrib import admin\n",
        "tests.py": "from django.test import TestCase\n",
    }

    for file, content in files.items():
        (app_dir / file).write_text(content, encoding="utf-8")

    # قالب أساسي
    (templates_dir / "base.html").write_text(
        """{% extends "web/base.html" %}

{% block content %}
<h1>""" + app_name + """</h1>
{% endblock %}
""",
        encoding="utf-8",
    )

    print(f"✅ App '{app_name}' created.")
    print(f"➕ Add to INSTALLED_APPS:")
    print(f'   "{app_name}",')


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/create_app.py app_name")
        sys.exit(1)

    create_app(sys.argv[1])
