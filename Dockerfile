FROM python:3.12-slim

WORKDIR /app

# Copy project definition and source tree
COPY pyproject.toml README.md ./
COPY src ./src

# Install package locally
RUN pip install --no-cache-dir .

ENTRYPOINT ["leakguard"]
CMD ["scan", ".", "--format", "text"]
