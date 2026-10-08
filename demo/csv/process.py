import os
import json
import pandas as pd

start_raw = os.environ.get("CHUNK_START", "0")
end_raw   = os.environ.get("CHUNK_END", "1000")
chunk_raw = os.environ.get("CHUNK_INDEX", "0")
total_raw = os.environ.get("CHUNK_TOTAL", "1")

start = int(start_raw) if start_raw and start_raw != "None" else 0
end   = int(end_raw)   if end_raw   and end_raw   != "None" else 1000
chunk = int(chunk_raw) if chunk_raw and chunk_raw != "None" else 0
total = int(total_raw) if total_raw and total_raw != "None" else 1

print(f"Processing rows {start} to {end} (chunk {chunk}/{total})")

n_samples = max(end - start, 1)
data = {"value": [i * 1.5 for i in range(n_samples)]}
df = pd.DataFrame(data)

summary = {
    "chunk_index": chunk,
    "rows_processed": len(df),
    "mean": float(df["value"].mean()),
    "std":  float(df["value"].std()) if len(df) > 1 else 0.0,
    "min":  float(df["value"].min()),
    "max":  float(df["value"].max()),
}

os.makedirs("/job/output", exist_ok=True)
with open("/job/output/metrics.json", "w") as f:
    json.dump(summary, f, indent=2)

df.describe().to_csv("/job/output/output.csv")
print(f"Done. Mean={summary['mean']:.2f}, Rows={summary['rows_processed']}")
print(json.dumps(summary, indent=2))