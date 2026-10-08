import os
import json
import pickle
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score

start = int(os.environ.get("CHUNK_START", 0))
end   = int(os.environ.get("CHUNK_END", 1000))
chunk = int(os.environ.get("CHUNK_INDEX", 0))
total = int(os.environ.get("CHUNK_TOTAL", 1))

print(f"[chunk {chunk}/{total}] Training on rows {start}:{end} ...")

np.random.seed(42 + chunk)
n_samples = end - start
X, y = make_classification(
    n_samples=n_samples,
    n_features=20,
    n_informative=10,
    random_state=42 + chunk
)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
metrics = {
    "chunk_index": chunk,
    "accuracy":  float(accuracy_score(y_test, y_pred)),
    "precision": float(precision_score(y_test, y_pred, zero_division=0)),
    "recall":    float(recall_score(y_test, y_pred, zero_division=0)),
    "n_samples": n_samples,
    "n_features": X.shape[1],
}

os.makedirs("/job/output", exist_ok=True)

with open("/job/output/metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

with open("/job/output/model.pkl", "wb") as f:
    pickle.dump(model, f)

print(f"[chunk {chunk}] Accuracy: {metrics['accuracy']:.4f}")
print(json.dumps(metrics, indent=2))
