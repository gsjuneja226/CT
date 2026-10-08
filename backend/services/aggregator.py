"""
Result Aggregator Service
=========================
Orchestrates the assembly of distributed computational results.
When all shards of a parallel job complete, this service merges 
their individual outputs into a single, cohesive final artifact.

Features:
- Standardized Merging: Intelligently combines JSON metrics, CSV logs, and Pickle models.
- Namespace Preservation: Renames non-standard files with chunk prefixes to avoid collisions.
- Artifact Finalization: Packages the merged results into a production-ready ZIP archive.
"""

import os
import json
import zipfile
import statistics
from database import execute, fetchall, fetchone
from services.ws_manager import ws_manager


def aggregate(parent_job_id: str):
    """
    Main entry point for assembling a split job.
    
    1. Identifies all child chunks for a parent job.
    2. Extracts their individual result ZIPs into temporary directories.
    3. Merges data based on file extensions.
    4. Creates a final consolidated ZIP archive.
    5. Updates the parent job status to 'done'.
    6. Broadcasts completion via WebSockets.
    """
    children = fetchall("""
        SELECT id, chunk_index, result_path
        FROM jobs
        WHERE parent_id = %s
        ORDER BY chunk_index ASC
    """, (parent_job_id,))

    if not children:
        return

    # Hierarchy: ./results/[parent_id]/final
    output_dir = f"./results/{parent_job_id}/final"
    os.makedirs(output_dir, exist_ok=True)

    chunk_dirs = []
    for child in children:
        # Skip shards that failed to produce an artifact
        if not child["result_path"] or not os.path.exists(child["result_path"]):
            continue
            
        d = f"./results/{parent_job_id}/chunk_{child['chunk_index']}"
        os.makedirs(d, exist_ok=True)
        
        try:
            with zipfile.ZipFile(child["result_path"]) as z:
                z.extractall(d)
            chunk_dirs.append(d)
        except Exception as e:
            print(f"[aggregator] Error extracting chunk {child['chunk_index']}: {e}")

    # If NO chunks produced valid data, the parent job is a terminal failure
    if not chunk_dirs:
        execute("""
            UPDATE jobs SET status='failed', updated_at=NOW() WHERE id=%s
        """, (parent_job_id,))
        return

    # Use the first chunk as a structural sample to detect shared file types
    sample = os.listdir(chunk_dirs[0]) if chunk_dirs else []

    # Format-specific Merge Dispatch
    if any(f.endswith(".json") for f in sample):
        _merge_json(chunk_dirs, output_dir)

    if any(f.endswith(".csv") for f in sample):
        _merge_csv(chunk_dirs, output_dir)

    if any(f.endswith(".pkl") for f in sample):
        _merge_pkl(chunk_dirs, output_dir)

    # Catch-all: Copy un-mergable files (images, logs, txt) with index prefixes
    _merge_other(chunk_dirs, output_dir, [".json", ".csv", ".pkl"])

    # Finalization: ZIP compression for user retrieval
    final_zip = f"./results/{parent_job_id}/final.zip"
    with zipfile.ZipFile(final_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for fname in os.listdir(output_dir):
            fpath = os.path.join(output_dir, fname)
            z.write(fpath, fname)

    # Database Synchronization
    execute("""
        UPDATE jobs
        SET status='done', result_path=%s, updated_at=NOW()
        WHERE id=%s
    """, (final_zip, parent_job_id))

    execute("""
        INSERT INTO results (job_id, file_path, exit_code)
        VALUES (%s, %s, 0)
        ON CONFLICT (job_id) DO UPDATE SET file_path=EXCLUDED.file_path
    """, (parent_job_id, final_zip))

    # Real-time UI notification
    ws_manager.broadcast_sync(parent_job_id, {
        "type": "job_complete",
        "download_url": f"/jobs/{parent_job_id}/results"
    })

    # Cleanup: Purge temporary chunk zips to save disk space
    for child in children:
        if child["result_path"] and os.path.exists(child["result_path"]):
            try:
                os.remove(child["result_path"])
            except Exception:
                pass


def _merge_json(chunk_dirs, out):
    """
    Averages numeric metrics across all shards. 
    Ideal for accuracy, loss, or performance timing JSONs.
    """
    all_data = []
    for d in chunk_dirs:
        p = os.path.join(d, "metrics.json")
        if os.path.exists(p):
            try:
                all_data.append(json.load(open(p)))
            except Exception:
                pass
    if not all_data:
        return
    keys = all_data[0].keys()
    merged = {}
    for k in keys:
        vals = [d[k] for d in all_data if isinstance(d.get(k), (int, float))]
        merged[k] = statistics.mean(vals) if vals else all_data[0].get(k)
    merged["chunks_merged"] = len(all_data)
    with open(os.path.join(out, "metrics.json"), "w") as f:
        json.dump(merged, f, indent=2)


def _merge_csv(chunk_dirs, out):
    """
    Concatenates CSV files vertically, maintaining schema alignment 
    using the Pandas library if available.
    """
    try:
        import pandas as pd
        frames = []
        for d in chunk_dirs:
            p = os.path.join(d, "output.csv")
            if os.path.exists(p):
                frames.append(pd.read_csv(p))
        if frames:
            pd.concat(frames, ignore_index=True).to_csv(
                os.path.join(out, "output.csv"), index=False)
    except ImportError:
        pass


def _merge_pkl(chunk_dirs, out):
    """
    Combines serialized Python objects (models) into a dictionary-based ensemble.
    """
    try:
        import pickle
        models = []
        for d in chunk_dirs:
            p = os.path.join(d, "model.pkl")
            if os.path.exists(p):
                with open(p, "rb") as f:
                    models.append(pickle.load(f))
        if models:
            with open(os.path.join(out, "ensemble.pkl"), "wb") as f:
                pickle.dump({"models": models, "type": "ensemble"}, f)
    except Exception:
        pass


def _merge_other(chunk_dirs, out, skip_exts):
    """
    Handles unstructured data by prefixing filenames with the shard index.
    e.g., 'chunk_0/plot.png' -> 'final/0_plot.png'
    """
    import shutil
    for d in chunk_dirs:
        for fname in os.listdir(d):
            # Only copy files that weren't handled by the specific format mergers
            if not any(fname.endswith(ext) for ext in skip_exts):
                src = os.path.join(d, fname)
                idx = os.path.basename(d).split("_")[-1]
                dst = os.path.join(out, f"{idx}_{fname}")
                shutil.copy2(src, dst)
