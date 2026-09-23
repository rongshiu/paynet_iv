# Python and Java are both pinned here so the Spark setup is reproducible.
FROM python:3.11-slim-bookworm

# Bookworm's default JRE is OpenJDK 17 on both arm64 and amd64.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      default-jre-headless \
      procps \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYSPARK_PYTHON=python3 \
    PYSPARK_DRIVER_PYTHON=python3 \
    # Stop local Spark from binding itself to the container's temporary IP.
    SPARK_LOCAL_IP=127.0.0.1 \
    # Keep Spark's scratch files off the bind mount.
    SPARK_LOCAL_DIRS=/tmp/spark-local \
    HOME=/home/analyst

WORKDIR /workspace

# Editable install: changes under src/ show up after a kernel restart.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e ".[notebook]"

# Avoid leaving root-owned notebook outputs on the host.
RUN useradd --create-home --uid 1000 --shell /bin/bash analyst \
 && mkdir -p /tmp/spark-local \
 && chown -R analyst:analyst /workspace /tmp/spark-local

USER analyst
EXPOSE 8888 4040

# JupyterLab listens on 8888; Spark's UI uses 4040.
CMD ["jupyter", "lab", \
     "--ip=0.0.0.0", \
     "--port=8888", \
     "--no-browser", \
     "--ServerApp.root_dir=/workspace", \
     "--IdentityProvider.token=paynet"]
