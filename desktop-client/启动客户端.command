#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 crawler/meta_material_client.py
