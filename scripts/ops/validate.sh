#!/bin/bash
 
echo "Validating app..."
 
for i in {1..30}
do
    STATUS=$(curl -L -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/admin/)
 
    if [ "$STATUS" = "200" ] || [ "$STATUS" = "302" ]; then
        echo "Application is healthy (HTTP $STATUS)"
        exit 0
    fi
 
    echo "Waiting for app... attempt $i (HTTP $STATUS)"
    sleep 2
done
 
echo "Application validation failed"
exit 1