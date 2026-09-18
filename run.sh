#!/usr/bin/env bash
# Startet x52tool aus dem Projektverzeichnis, ohne Installation.
cd "$(dirname "$0")" && exec python3 -m x52tool "$@"
