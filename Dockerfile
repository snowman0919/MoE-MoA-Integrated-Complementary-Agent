FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY gateway gateway
RUN pip install --no-cache-dir .
USER 65532:65532
ENTRYPOINT ["dgx-moa"]

