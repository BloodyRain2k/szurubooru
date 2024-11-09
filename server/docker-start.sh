#!/usr/bin/dumb-init /bin/sh
set -e
cd /opt/app

if [ "$DOWNGRADE" ]; then
  alembic downgrade $DOWNGRADE
else
  if [ "$NO_UPGRADE" = "1" ]; then
    echo "skipping migrations"
  else
    alembic upgrade head
  fi
fi

if [ "$HUPPER" = "1" ]; then
  echo "Debugging szurubooru API on port ${PORT} - Running on ${THREADS} threads"
  exec hupper -m waitress --port ${PORT} --threads ${THREADS} szurubooru.facade:app
else
  echo "Starting szurubooru API on port ${PORT} - Running on ${THREADS} threads"
  exec waitress-serve-3 --port ${PORT} --threads ${THREADS} szurubooru.facade:app
fi
