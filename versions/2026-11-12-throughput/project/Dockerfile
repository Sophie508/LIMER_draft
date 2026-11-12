FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake python3 git pkg-config ca-certificates \
    libboost-dev libgsl-dev libsqlite3-dev libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
COPY . /opt/limer
WORKDIR /work
ENTRYPOINT ["python3", "/opt/limer/limer.py"]
CMD ["--help"]
