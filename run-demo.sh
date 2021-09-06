#!/bin/bash
export DJANGO_SETTINGS_MODULE=cachelab.settings_demo
if [ $# -eq 0 ]; then
    python3 manage.py runserver 127.0.0.1:8888
else
    python3 manage.py "${@}"
fi
