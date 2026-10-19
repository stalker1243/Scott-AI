# CPU validation environment; it is not a Linux distribution package.
FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ cmake ninja-build libgomp1 && rm -rf /var/lib/apt/lists/*
