FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY setup_nuclei_templates.sh update_nuclei_templates.py generate_nuclei_tree.py ./
RUN chmod +x setup_nuclei_templates.sh update_nuclei_templates.py generate_nuclei_tree.py
RUN ./setup_nuclei_templates.sh

COPY ./app/ ./

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 