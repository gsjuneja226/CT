"""
CampuShare Demo: PyTorch Model Training
=======================================
A reference implementation for a machine learning workload (Deep Learning).
Demonstrates how to utilize hardware acceleration (CUDA) and report 
training metrics (loss, accuracy) back to the dashboard.

Capabilities:
- Dynamic Hardware Detection: Automatically uses NVIDIA GPUs if present.
- Real-time Progress: Prints epoch-level stats for log streaming.
- Persistent Artifacts: Saves both JSON metrics and binary model weights (.pt).
"""

import os
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np

# Retrieve sharding metadata for deterministic seeding or partitioned training
chunk = int(os.environ.get("CHUNK_INDEX", 0))
total = int(os.environ.get("CHUNK_TOTAL", 1))

# Hardware Abstraction Layer
# CampuShare Project Hardware Detection
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[demo] Node Shard {chunk}/{total} | Device: {device}")
if torch.cuda.is_available():
    print(f"  GPU Hardware: {torch.cuda.get_device_name(0)}")

# Simple Linear Bottleneck Architecture
# Input: 784 (Flattened 28x28 Image)
# Output: 10 (Softmax Class Probabilities)
class SimpleCNN(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(784, 256),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Linear(64, 10)
        )
    def forward(self, x):
        return self.net(x)

# Data Generation: Synthetic MNIST-like tensors
# Using a unique seed per chunk to ensure diverse data across nodes
np.random.seed(42 + chunk)
n = 2000
X = torch.FloatTensor(np.random.randn(n, 784))
y = torch.LongTensor(np.random.randint(0, 10, n))

dataset = TensorDataset(X, y)
loader  = DataLoader(dataset, batch_size=64, shuffle=True)

# Optimization Setup
model = SimpleCNN().to(device)
optimizer = optim.Adam(model.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss()

# Training Loop
history = []
print("[demo] Initializing training loop (5 epochs)...")
for epoch in range(5):
    model.train()
    total_loss = 0
    correct = 0
    for xb, yb in loader:
        xb, yb = xb.to(device), yb.to(device)
        optimizer.zero_grad()
        out = model(xb)
        loss = criterion(out, yb)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        correct += (out.argmax(1) == yb).sum().item()

    acc = correct / n
    avg_loss = total_loss / len(loader)
    history.append({"epoch": epoch + 1, "loss": avg_loss, "accuracy": acc})
    print(f"  Epoch {epoch+1}/5 | Mean Loss: {avg_loss:.4f} | Accuracy: {acc:.4f}")

# Metric Aggregation
metrics = {
    "chunk_index": chunk,
    "device": str(device),
    "accuracy": history[-1]["accuracy"],
    "final_loss": history[-1]["loss"],
    "epochs": 5,
    "history": history,
}

# Artifact Serialization
# Note: /job/output is the standard mount point for result collection.
os.makedirs("/job/output", exist_ok=True)

# 1. Dashboard-consumable metrics
with open("/job/output/metrics.json", "w") as f:
    json.dump(metrics, f, indent=2)

# 2. Binary Model Weights for model serving/fine-tuning
torch.save(model.state_dict(), "/job/output/model.pt")

print(f"\n[demo] Final training accuracy: {metrics['accuracy']:.4f}")
print(json.dumps({k: v for k, v in metrics.items() if k != "history"}, indent=2))
