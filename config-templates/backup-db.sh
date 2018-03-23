pushd cachelabweb
sqlite3 db.sqlite3 '.dump' >../backup.`date +%Y%m%dT%H%M%S`.sql
