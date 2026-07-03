#!/bin/bash
set -e
echo "Building consolidated Docker Image..."
docker build --target production -t ohs-web:latest .
