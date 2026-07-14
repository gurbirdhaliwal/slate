FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY slate_worker ./slate_worker
RUN pip install --no-cache-dir .

# Non-root
RUN useradd -m slate
USER slate

CMD ["slate-worker"]
