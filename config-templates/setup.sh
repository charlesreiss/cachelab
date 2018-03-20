CACHELABWEB_GIT=/home/cr4bd/repos/cachelabweb
CACHELABWEB_BRANCH=for-deploy
SECRET_SETTINGS=XXX

set -e
set -x
python3 -m venv .
git clone -b $CACHELABWEB_BRANCH $CACHELABWEB_GIT cachelabweb
cp $SECRET_SETTINGS cachelabweb/cachelabweb/secret_settings.py
source bin/activate
pip install django uwsgi
pushd cachelabweb
python3 manage.py migrate
popd
cp cachelabweb/config-templates/nginx.conf .
cp cachelabweb/config-templates/restart-uwsgi.sh .
sed -e "s/@@@BASE@@@/`pwd`/" < cachelabweb/config-templates/config.ini >config.ini
