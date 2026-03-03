# Week 3–4 Visualization: Boundary Detection Benchmark

> Artifacts produced: Console benchmark metrics (no persistent DB)

**What this week delivered:**
- `BoundaryDetectorAgent` + `PartitionBuilderAgent` (L2-C chunking)
- Benchmark script: `sas_converter/benchmark/boundary_benchmark.py`
- Accuracy: 61.3% → 72.3% (79 blocks gained)

**Why no persistent visualization artifacts:**
The benchmark script compares detected blocks against the 50 gold `.gold.json` files and prints results to console. It does not write a database.

**To see the benchmark results:**

1. Switch to `main`:
   ```powershell
   git checkout main
   ```

2. Run the benchmark:
   ```powershell
   python -m pytest sas_converter/benchmark/boundary_benchmark.py -v
   ```
   or if you have a standalone benchmark script:
   ```powershell
   python sas_converter/benchmark/boundary_benchmark.py
   ```

3. Console output shows:
   - Overall accuracy (e.g., `72.3% (521/721)`)
   - Per-type accuracy breakdown
   - Matched/missed counts per `PartitionType`

**Gold corpus location (for reference):**
- `sas_converter/knowledge_base/gold_standard/*.sas` + `*.gold.json`
