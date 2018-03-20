kill -INT `cat uwsgi.pid`
sleep 1
nohup bin/uwsgi -start config.ini 2>&1 >uwsgi.log &
