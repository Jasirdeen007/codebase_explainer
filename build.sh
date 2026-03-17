pip install -r requirements.txt
pip install -r requirements-ai.txt
cd codeexplainer
python manage.py collectstatic --noinput
python manage.py migrate