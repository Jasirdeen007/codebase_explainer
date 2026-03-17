pip install -r requirements.txt
pip install -r requirements-ai.txt
python manage.py collectstatic --noinput
python manage.py migrate