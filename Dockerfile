FROM node:26-slim AS node
FROM python:3.12-slim
COPY --from=node /usr/local/ /usr/local/
RUN apt-get update && apt-get install -y --no-install-recommends git ripgrep procps ca-certificates libatomic1 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/mypi
COPY requirements.txt package.json package-lock.json ./
RUN python -m venv agent-workflow-v2/.venv && agent-workflow-v2/.venv/bin/python -m pip install --no-cache-dir -r requirements.txt && npm ci --ignore-scripts
COPY . .
RUN chmod +x mypi pi-local install.sh agent-workflow-v2/qwen-agent
ENTRYPOINT ["/opt/mypi/mypi"]
