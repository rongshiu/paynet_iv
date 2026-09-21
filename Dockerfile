# ---------------------------------------------------------------------------
# PySpark + JupyterLab image for the credit-card transaction assessment.
#
# Why a container: PySpark needs a JVM. Pinning Python 3.11 + OpenJDK 17 +
# Spark 3.5 here means the notebook runs identically on any machine (and on
# both arm64 and amd64) with no host Java install.
# ---------------------------------------------------------------------------
FROM python:3.11-slim-bookworm

# default-jre-headless on bookworm is OpenJDK 17 and creates the
# arch-independent /usr/lib/jvm/default-java symlink, so JAVA_HOME is the same
# string on Apple Silicon and on x86.
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
    # Spark's local-mode driver otherwise probes for a routable NIC and can
    # hang or bind to a container IP that dies with the network.
    SPARK_LOCAL_IP=127.0.0.1 \
    # Keep Ivy/Spark scratch inside the image, not the bind mount.
    SPARK_LOCAL_DIRS=/tmp/spark-local \
    HOME=/home/analyst

WORKDIR /workspace

# Dependencies and the local package both come from pyproject.toml. The install
# is editable and rooted at /workspace, which is also the bind-mount point --
# so `src/paynet_iv` stays live-editable from the host without a rebuild, and
# the notebook can `from paynet_iv import viz_theme` with no sys.path games.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install -e ".[notebook]"

# Run as a non-root user whose UID matches the common Linux default, so files
# the notebook writes into the bind mount stay editable from the host.
RUN useradd --create-home --uid 1000 --shell /bin/bash analyst \
 && mkdir -p /tmp/spark-local \
 && chown -R analyst:analyst /workspace /tmp/spark-local

USER analyst
EXPOSE 8888 4040

# 8888 = JupyterLab, 4040 = the Spark UI for the notebook's driver.
CMD ["jupyter", "lab", \
     "--ip=0.0.0.0", \
     "--port=8888", \
     "--no-browser", \
     "--ServerApp.root_dir=/workspace", \
     "--IdentityProvider.token=paynet"]
