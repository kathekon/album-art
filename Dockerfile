# Album Art Display Server
FROM python:3.11-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/
COPY config.toml .
COPY src/album_art/static/ src/album_art/static/

# Install dependencies
RUN uv pip install --system -e .

# Expose the server port
EXPOSE 5174

# Run the server (bind to 0.0.0.0 for container access)
CMD ["python", "-m", "uvicorn", "album_art.main:app", "--host", "0.0.0.0", "--port", "5174"]
