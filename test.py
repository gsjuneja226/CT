# my_workload.py
import os
import pandas as pd

# 1. Read cluster shard indices
chunk_idx = os.environ.get("CHUNK_INDEX", "0")
chunk_total = os.environ.get("CHUNK_TOTAL", "1")
print(f"Node executing shard {chunk_idx} of {chunk_total}...")

# 2. If you attached a CSV dataset, each node receives its slice:
input_file = os.environ.get("INPUT_FILE_NAME")
if input_file and os.path.exists(input_file):
    print(f"Loading partitioned dataset: {input_file}")
    df = pd.read_csv(input_file)
    summary = df.describe()
else:
    # Or perform synthetic computation
    summary = pd.DataFrame({"sample": [i ** 2 for i in range(1000)]})

# 3. Save all outputs to /job/output/ (CampuShare will collect & zip them)
os.makedirs("/job/output", exist_ok=True)
summary.to_csv(f"/job/output/summary_shard_{chunk_idx}.csv")
print("Finished computation!")
