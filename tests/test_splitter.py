import pytest
import json


def test_row_range_produces_correct_ranges():
    from backend.services.splitter import compute_chunks
    chunks = compute_chunks({"strategy": "row_range", "num_chunks": 4, "total_rows": 100000})
    assert len(chunks) == 4
    assert chunks[0]["CHUNK_START"] == "0"
    assert chunks[0]["CHUNK_END"]   == "25000"
    assert chunks[1]["CHUNK_START"] == "25000"
    assert chunks[1]["CHUNK_END"]   == "50000"


def test_row_range_last_chunk_covers_remainder():
    from backend.services.splitter import compute_chunks
    chunks = compute_chunks({"strategy": "row_range", "num_chunks": 3, "total_rows": 100})
    assert chunks[-1]["CHUNK_END"] == "100"


def test_row_range_chunk_indices():
    from backend.services.splitter import compute_chunks
    chunks = compute_chunks({"strategy": "row_range", "num_chunks": 4, "total_rows": 1000})
    for i, c in enumerate(chunks):
        assert c["CHUNK_INDEX"] == str(i)
        assert c["CHUNK_TOTAL"] == "4"


def test_param_grid_distributes_all_combinations():
    from backend.services.splitter import compute_chunks
    params = [{"lr": 0.01}, {"lr": 0.001}, {"lr": 0.0001}]
    chunks = compute_chunks({"strategy": "param_grid", "num_chunks": 3, "params": params})
    assert len(chunks) == 3
    for i, c in enumerate(chunks):
        p = json.loads(c["PARAMS"])
        assert p == params[i]


def test_file_list_distributes_files_evenly():
    from backend.services.splitter import compute_chunks
    files = ["a.csv", "b.csv", "c.csv", "d.csv"]
    chunks = compute_chunks({"strategy": "file_list", "num_chunks": 2, "files": files})
    assert len(chunks) == 2
    all_files = []
    for c in chunks:
        all_files.extend(json.loads(c["CHUNK_FILES"]))
    assert set(all_files) == set(files)


def test_unknown_strategy_raises():
    from backend.services.splitter import compute_chunks
    with pytest.raises(ValueError):
        compute_chunks({"strategy": "unknown", "num_chunks": 2})
