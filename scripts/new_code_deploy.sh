#!/bin/bash

cd ~/app/paribus/

git pull origin main₹

# for django
source ~/app/paribus/.venv/bin/activate

cd ~/app/paribus/
uv pip install -r requirements.txt
python manage.py migrate

# Kill any existing gunicorn/uvicorn processes
pkill -f "daphne.*paribus.wsgi:application"

# Restart using supervisor (supervisor will manage the process)
sudo supervisorctl stop paribus
sudo supervisorctl start paribus
sudo supervisorctl status paribus

sudo systemctl restart nginx
#sudo supervisorctl restart basanti-shopee-celery-worker