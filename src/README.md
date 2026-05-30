# Django Starter Core
-khalid salman
A production-ready Django starter with:
- Custom User
- RBAC System
- Separated settings (dev/prod)
- Ready static structure

نواة جاهزة لبناء مشاريع Django، تحتوي على:
- مستخدم مخصص (Custom User)
- نظام أدوار وصلاحيات (RBAC)
- فصل الإعدادات (تطوير / إنتاج)
- بنية جاهزة للملفات الثابتة

## Quick start

```bash
python scripts/bootstrap.py
source ../.venv/bin/activate
..\.venv\Scripts\activate
python manage.py seed_all
python manage.py runserver
python manage.py runserver 0.0.0.0:8000
py manage.py runserver 127.0.0.1:8002  

python manage.py makemigrations
python manage.py migrate
python manage.py seed_all


## Quick start

## Language 
python manage.py compilemessages


toast Use:
messages.success(request, "تم", extra_tags="toast")



tailwind
npx @tailwindcss/cli -i ./assets/css/input.css -o ./static/css/output.css --minify
python3 manage.py collectstatic --noinput
python3 manage.py runserver

python manage.py import_ayah_positions --csv apps/quran/data/hafs.csv --mushaf hafs
python manage.py import_ayah_positions --csv apps/quran/data/sousi.csv --mushaf sousi
python manage.py import_ayah_positions --csv apps/quran/data/shuba.csv --mushaf shuba
python manage.py import_ayah_positions --csv apps/quran/data/qaloun.csv --mushaf qaloun
python manage.py import_ayah_positions --csv apps/quran/data/warsh.csv --mushaf warsh
python manage.py import_ayah_positions --csv apps/quran/data/douri.csv --mushaf douri



python manage.py shell -c "from django.db import connection; cursor=connection.cursor(); cursor.execute('TRUNCATE TABLE quran_ayahposition RESTART IDENTITY CASCADE;')"


mv env .env
```
## Create new app (تذكير)

```bash
python scripts/create_app.py app_name
```


## Env.  (تذكير)

```bash
pip freeze > requirements.txt
pip install -r requirements.txt
```



## Clean temp  windows on cmd bat(تذكير)

```bash
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
```


## Clean temp  Mac(تذكير)

```bash
find . -name "__pycache__" -type d -exec rm -rf {} +
find . -name "*.pyc" -delete
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete



```



## Database Sqllite for base (تذكير)
```bash
rm db.sqlite3
```

## Database Sqllite for base (تذكير)
```bash

```



## Delte Data from table renew
```bash
python manage.py dbshell

DELETE FROM quran_ayahposition;
DELETE FROM sqlite_sequence WHERE name='quran_ayahposition';

```

 

# Django Environment Commands (Dev & Prod)

## 🟢 Development – SQLite (dev)

```bash

#ٍSqlite
# Run development server
python manage.py runserver --settings=core.settings.dev

# Apply migrations
python manage.py migrate --settings=core.settings.dev

# Create superuser
python manage.py createsuperuser --settings=core.settings.dev

# Seed initial data
python manage.py seed_all --settings=core.settings.dev

###############################################

#PostgreSQL
python manage.py runserver --settings=core.settings.prod

# Apply migrations on PostgreSQL
python manage.py migrate --settings=core.settings.prod

# Create superuser
python manage.py createsuperuser --settings=core.settings.prod

# Seed initial data
python manage.py seed_all --settings=core.settings.prod

# Collect static files
python manage.py collectstatic --settings=core.settings.prod

```

```bash
from axes.models import AccessAttempt

AccessAttempt.objects.all().delete()
exit()
```




from notifications.sms import send_sms

mobiles = [
    "966551539188",
    "966553194521",
]

for mobile in mobiles:
    ok, reason = send_sms(mobile, "Test SMS")
    print(mobile, "=>", ok, reason)
