#!/bin/bash

cd ~/app/paribus/

source .venv/bin/activate

pkill -f "daphne.*paribus.wsgi:application"
daphne -b 0.0.0.0 -p 8015 paribus.asgi:application