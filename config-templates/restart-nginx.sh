kill -QUIT `cat nginx-build/logs/nginx.pid`
nohup ./nginx-build/sbin/nginx -c `pwd`/nginx-conf/nginx.conf 2>nginx.log &
