#!/usr/bin/env bash
set -e

cd /root/paso-bot

git pull origin main

source .venv/bin/activate
pip install -r requirements.txt || true

systemctl restart paso-api
systemctl status paso-api --no-pager

