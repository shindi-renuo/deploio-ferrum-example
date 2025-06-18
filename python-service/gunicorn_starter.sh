#!/bin/bash
set -e

echo "Starting Gunicorn with Flask app..."
exec gunicorn --bind 0.0.0.0:5000 main:app
