if kill -0 `cat uwsgi.pid`; then
else
    bash restart-uwsgi.sh
fi

if kill -0 `cat nginx-build/logs/nginx.pid`; then
else
    bash restart-uwsgi.sh
fi

