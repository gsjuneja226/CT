FROM python:3.11-slim
WORKDIR /job
RUN pip install --no-cache-dir scikit-learn numpy pandas --quiet
COPY train_sklearn.py .
CMD ["python", "train_sklearn.py"]
