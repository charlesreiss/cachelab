cd /var/www/vibe.d/cachelab

if /bin/kill -0 `cat uwsgi.pid`; then
    true;
else
    bash restart-uwsgi.sh
fi

if /bin/kill -0 `cat nginx-build/logs/nginx.pid`; then
    true;
else
    bash restart-nginx.sh
fi

