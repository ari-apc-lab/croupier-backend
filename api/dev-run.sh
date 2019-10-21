sudo bash -c "export $(cat .env | sed 's/#.*//g' | xargs) && python manage.py runserver 0.0.0.0:80"
