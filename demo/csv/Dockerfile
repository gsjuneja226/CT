FROM python:3.11-slim
WORKDIR /job
RUN pip install --no-cache-dir pandas --quiet
COPY process.py .
CMD ["python", "process.py"]
