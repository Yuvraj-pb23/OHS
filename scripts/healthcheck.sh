#!/bin/bash
set -e
echo "Verifying service health status..."
curl -f http://localhost/health || exit 1
