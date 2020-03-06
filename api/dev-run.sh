#!/bin/sh
#sudo bash -c "export $(cat .env | sed 's/#.*//g' | xargs) && source venv/bin/activate && source sample.env && python3 manage.py runserver 0.0.0.0:80"
sudo bash -c "export $(cat .env | sed 's/#.*//g' | xargs) && source venv/bin/activate && source sample.env && uwsgi --ini api_uwsgi.ini"
