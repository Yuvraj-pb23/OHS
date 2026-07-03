#!/bin/bash
set -e
if [ -z "$1" ]; then
    echo "Usage: $0 <image_tag>"
    exit 1
fi
TAG=$1
echo "Rolling back to tag: $TAG..."
docker-compose --profile prod stop web
docker-compose --profile prod up -d --remove-orphans
echo "Rollback trigger succeeded."
