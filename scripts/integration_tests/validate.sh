#!/bin/bash

echo "Validating app..."

for i in {1..15}
do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000)

  if [ "$STATUS" -eq 200 ] || [ "$STATUS" -eq 404 ]; then
    echo "App is running (status: $STATUS)"
    exit 0
  fi

  echo "Waiting for app... attempt $i"
  sleep 2
done

echo "App failed to start"
exit 1
