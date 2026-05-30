import subprocess
import sys
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # parent/
SRC_DIR = BASE_DIR / "src"

VENV_DIR = BASE_DIR / "venv"
ENV_FILE = SRC_DIR / ".env"
REQ_FILE = SRC_DIR / "requirements.txt"

PYTHON = VENV_DIR / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(cmd):
    subprocess.check_call(cmd)


def create_venv():
    if VENV_DIR.exists():
        print("⚠️ Virtual environment already exists – skipped.")
        return
    print("🐍 Creating virtual environment...")
    run([sys.executable, "-m", "venv", str(VENV_DIR)])


def install_requirements():
    if not REQ_FILE.exists():
        print("⚠️ requirements.txt not found – skipped.")
        return

    print("📦 Installing requirements inside venv...")
    run([str(PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(PYTHON), "-m", "pip", "install", "-r", str(REQ_FILE)])


def create_env_file():
    if ENV_FILE.exists():
        print("⚠️ .env already exists – skipped.")
        return

    secret_key = secrets.token_urlsafe(50)

    content = f"""# Django core
DEBUG=True
SECRET_KEY={secret_key}
ALLOWED_HOSTS=127.0.0.1,localhost

# PostgreSQL (optional – used in production)
POSTGRES_DB=app_db
POSTGRES_USER=app_user
POSTGRES_PASSWORD=strong_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
"""

    ENV_FILE.write_text(content, encoding="utf-8")
    print("✅ .env file created.")


def django(cmd: list[str]):
    run([str(PYTHON), "manage.py"] + cmd)


def main():
    print("🚀 Bootstrapping Django project...")

    create_venv()
    install_requirements()
    create_env_file()

    # Safe to run Django now
    django(["makemigrations"])
    django(["migrate"])
    django(["seed_all"])

    print("\n🎉 Project is ready!")
    print("Activate venv:")
    print("  source venv/bin/activate")
    print("Then run:")
    print("  python manage.py runserver")


if __name__ == "__main__":
    main()
