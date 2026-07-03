#!/bin/bash
set -e
echo "Cleaning up dangling images, unused containers, and caches..."
docker system prune -f
docker volume prune -f
