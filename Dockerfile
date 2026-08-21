FROM ghcr.io/astral-sh/uv:0.11.19@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 AS uv
FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY gateway gateway
COPY --from=uv /uv /uvx /bin/
RUN uv sync --frozen --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH"
USER 65532:65532
ENTRYPOINT ["dgx-moa"]
