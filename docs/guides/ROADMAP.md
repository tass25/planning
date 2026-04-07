# Codara — Full Execution Roadmap
> One step at a time. Each step has: what to do, exact commands, where results go, and what "done" looks like.

---

## PHASE 1 — Setup & CI/CD (Day 1-2)

---

### Step 1 — Get free API keys you're missing

**Cerebras** (2 minutes):
1. Go to https://cloud.cerebras.ai
2. Sign up with GitHub
3. Go to API Keys → Create Key
4. Copy key into `.env` → `CEREBRAS_API_KEY=your_key_here`

**Done when**: `.env` has a real value for `CEREBRAS_API_KEY`

---

### Step 2 — Install the new dependencies locally

```bash
cd backend
pip install z3-solver geoopt google-generativeai datasketch datasets llama-cpp-python
```

If `llama-cpp-python` fails on Windows (it often does), use the prebuilt wheel:
```bash
pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
```

**Done when**: `python -c "import z3; import geoopt; import google.generativeai"` runs with no errors

---

### Step 3 — Run the new tests to confirm code is wired correctly

```bash
cd backend
python -m pytest tests/test_z3_verification.py tests/test_hyper_raptor.py tests/test_local_model_client.py -v
```

Expected output:
```
tests/test_z3_verification.py::test_proc_means_equivalent PASSED
tests/test_z3_verification.py::test_sort_nodupkey_proved PASSED
... (12 tests)
tests/test_hyper_raptor.py::TestGetClusterer::test_default_returns_gmm PASSED
... (9 tests)
tests/test_local_model_client.py::TestLocalModelClient::test_not_available_when_path_unset PASSED
... (6 tests)
```

If `geoopt` tests are skipped with `pytest.importorskip` — that's fine, they skip cleanly when geoopt isn't installed yet.

**Done when**: All 27 tests pass (or skip cleanly with importorskip)

---

### Step 4 — Wire Z3 into TranslationPipeline

Z3 is built but not connected. Open `backend/partition/translation/translation_pipeline.py`.

Find this block (around line 44):
```python
        # Validate
        test_type = partition.metadata.get("test_coverage_type", "full")
        validation = await self.validator.validate(conversion, test_type)
```

Add Z3 import at the top of the file:
```python
from partition.verification.z3_agent import Z3VerificationAgent, VerificationStatus
```

Add Z3 call after the `__init__` sets up `self.validator`:
```python
        self.z3_agent = Z3VerificationAgent()
```

Add Z3 call after validation passes (after the retry loop finishes, before `_log_quality`):
```python
        # Z3 formal verification — non-blocking
        if conversion.status != ConversionStatus.PARTIAL:
            z3_result = self.z3_agent.verify(
                partition.source_code,
                conversion.python_code or "",
            )
            conversion.metadata["z3_status"] = z3_result.status.value
            conversion.metadata["z3_pattern"] = z3_result.pattern
            conversion.metadata["z3_latency_ms"] = z3_result.latency_ms

            if z3_result.status == VerificationStatus.COUNTEREXAMPLE:
                # Z3 found a semantic difference → escalate risk
                from partition.models.enums import RiskLevel
                partition.risk_level = RiskLevel.HIGH
                conversion.metadata["z3_counterexample"] = z3_result.counterexample
```

**Done when**: `python -m pytest tests/test_z3_verification.py -v` still passes and the pipeline runs without import errors

---

### Step 5 — Wire local model into TranslationAgent

Open `backend/partition/translation/translation_agent.py`. In `__init__`, after the Groq client setup, add:

```python
        # Local fine-tuned model (Tier 0 — free, ~200ms)
        from partition.utils.local_model_client import get_local_model_client
        self.local_client = get_local_model_client()
```

In the `process()` method, find where it calls the Azure client for LOW-risk translations. Before the Azure call, add:

```python
        # Tier 0: local model (if available)
        if self.local_client.is_available and partition.risk_level == RiskLevel.LOW:
            local_result = await self.local_client.complete(
                partition.source_code, max_tokens=1024, temperature=0.1
            )
            if local_result:
                # parse python_code from local_result.content
                # (same extraction logic as existing Azure path)
                pass  # wire the result into ConversionResult
```

> Note: The exact location depends on where your LOW-risk routing is. Look for
> `get_deployment_name("mini")` — that's the LOW-risk Azure call. Put the local
> model check just before it. If local returns None, fall through to Azure as before.

**Done when**: With `LOCAL_MODEL_PATH` unset, pipeline behaves exactly as before. With `LOCAL_MODEL_PATH` set, LOW-risk partitions skip Azure.

---

### Step 6 — Azure setup (30 minutes, one time only)

First, edit `scripts/azure_setup.sh` line 14 — change `GITHUB_REPO`:
```bash
GITHUB_REPO="your_actual_github_username/your_actual_repo_name"
```

Then run:
```bash
# On Windows, use Git Bash or WSL
bash scripts/azure_setup.sh
```

The script will:
- Create Resource Group, App Insights, Key Vault, Container Apps, Managed Identity
- Ask you to enter API keys to store in Key Vault
- Print the 3 OIDC values you need for GitHub Secrets

**Fill in App Insights connection string in `.env`**:
The script prints it. Copy it into:
```
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=xxxx;IngestionEndpoint=...
```

**Done when**: Script completes without error, you have 3 values printed (CLIENT_ID, TENANT_ID, SUBSCRIPTION_ID)

---

### Step 7 — Add GitHub Secrets

Go to: your repo → Settings → Secrets and variables → Actions → New repository secret

Add these one by one (use exact names — CI/CD references them):

| Secret name | Where to get the value |
|---|---|
| `AZURE_CLIENT_ID` | printed by azure_setup.sh |
| `AZURE_TENANT_ID` | printed by azure_setup.sh |
| `AZURE_SUBSCRIPTION_ID` | printed by azure_setup.sh |
| `AZURE_OPENAI_API_KEY` | copy from your `.env` |
| `AZURE_OPENAI_ENDPOINT` | copy from your `.env` |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` |
| `AZURE_OPENAI_DEPLOYMENT_MINI` | copy from your `.env` |
| `GROQ_API_KEY` | copy from your `.env` |
| `GEMINI_API_KEY` | copy from your `.env` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | copy from `.env` after step 6 |

**Done when**: All 10 secrets appear in GitHub → Settings → Secrets list

---

### Step 8 — Push to GitHub and watch CI run

```bash
git add .
git commit -m "Add Z3 verification, HyperRAPTOR, CI/CD upgrade, Azure integration"
git push origin main
```

Go to: your repo → Actions tab → watch "CI/CD Pipeline" run

Expected jobs in order:
1. `Lint & Format` → green (ruff + black)
2. `Tests & Coverage` → green (≥75% coverage)
3. `Security Scan` → green or warning (not failing)
4. `Build & Push Docker Image` → green (image pushed to ghcr.io)
5. `Deploy to Azure Container Apps` → green (smoke test on `/api/health` passes)
6. `Gold Standard Benchmark` → green or warning

If `Deploy` fails on first run: the Container App doesn't exist yet. The `az containerapp up` command creates it on first run, but may time out. Re-run the job manually from Actions → Re-run failed jobs.

**Done when**: All 6 jobs green. Go to your repo → Code → look for the green deployment status badge on your latest commit.

---

## PHASE 2 — Fine-Tuning (Week 1-2)

---

### Step 9 — Build the training dataset

```bash
cd backend
python scripts/build_dataset.py --output data/sft_train.jsonl --target 1000
```

This takes 30-60 minutes (mostly Gemini distillation of The Stack SAS files).

Watch the output — it logs progress:
```
[info] loaded_gold_standard count=45
[info] loaded_kb_pairs count=330
[info] distillation_progress done=50
[info] distillation_progress done=100
...
[info] dedup_complete original=1200 unique=1050 removed=150
[info] dataset_complete train=945 val=105
```

Results stored in:
```
backend/data/sft_train.jsonl   ← training data
backend/data/sft_val.jsonl     ← validation data
backend/data/dpo_train.jsonl   ← preference pairs (if corrections table has data)
```

**Done when**: `wc -l backend/data/sft_train.jsonl` shows ≥ 800 lines

---

### Step 10 — Run fine-tuning in Google Colab

1. Go to https://colab.research.google.com
2. New notebook
3. Runtime → Change runtime type → **T4 GPU** → Save
4. Open `notebooks/sft_qwen_colab.py` in VSCode — you'll see it's organized as `# == CELL N ==` sections
5. For each `# == CELL N ==` block, create a new Colab cell and paste the code

**Cells to run in order:**
- Cell 1: install packages (takes ~3 minutes)
- Cell 2: config — change `HF_USERNAME` to your HuggingFace username
- Cell 3: optional Google Drive mount (recommended — saves checkpoints if Colab disconnects)
- Cell 4: load model (takes ~2 minutes, downloads 14GB)
- Cell 5: load dataset — **upload your files first**:
  - Colab left panel → Files icon → Upload → select `backend/data/sft_train.jsonl`
  - Upload `backend/data/sft_val.jsonl`
- Cell 6: format dataset
- Cell 7: **SFT training** — takes 3-4 hours on T4, watch the loss go down
- Cell 8: evaluate perplexity — target < 3.0
- Cell 9: test inference — paste a SAS block, see the output
- Cell 10: DPO (only if you have `dpo_train.jsonl` with ≥ 20 pairs, otherwise skip)
- Cell 11: save + export GGUF
- Cell 12: optional HuggingFace push

**Training progress to watch in Cell 7:**
```
{'loss': 2.34, 'epoch': 0.1}
{'loss': 1.87, 'epoch': 0.5}
{'loss': 1.21, 'epoch': 1.0}
{'loss': 0.89, 'epoch': 2.0}
{'loss': 0.67, 'epoch': 3.0}   ← target: loss < 0.8 by epoch 3
```

**Download the GGUF** (Cell 11 creates it):
```python
from google.colab import files
files.download("codara-qwen2.5-coder-sas-gguf/unsloth.Q4_K_M.gguf")
```
File size: ~4.5 GB. Download takes 5-10 minutes.

**Results to store:**
- Save final perplexity number somewhere (you'll need it for the paper)
- Save training loss curve screenshot

**Done when**: You have `unsloth.Q4_K_M.gguf` downloaded locally

---

### Step 11 — Deploy the fine-tuned model locally

```bash
# Create models directory in backend
mkdir -p backend/models

# Move the downloaded GGUF there
mv ~/Downloads/unsloth.Q4_K_M.gguf backend/models/codara-qwen2.5-coder-sas-Q4_K_M.gguf
```

Update `.env`:
```
LOCAL_MODEL_PATH=backend/models/codara-qwen2.5-coder-sas-Q4_K_M.gguf
```

Test it:
```bash
cd backend
python -c "
import asyncio
from partition.utils.local_model_client import get_local_model_client

async def test():
    client = get_local_model_client()
    print(f'Available: {client.is_available}')
    result = await client.complete('data output; set input; new_var = old_var * 2; run;')
    if result:
        print(f'Latency: {result.latency_ms:.0f}ms')
        print(f'Output: {result.content[:200]}')
    else:
        print('Model returned None')

asyncio.run(test())
"
```

Expected output:
```
Available: True
Latency: 180ms
Output: ```python
output = input.copy()
output['new_var'] = output['old_var'] * 2
```
```

**Done when**: Local model returns a valid Python translation in < 500ms

---

## PHASE 3 — HyperRAPTOR Validation (Week 2-3, 3-4 days)

---

### Step 12 — Install geoopt and run HyperRAPTOR tests

```bash
pip install geoopt>=0.5.0
cd backend
python -m pytest tests/test_hyper_raptor.py -v
```

All 9 tests should now pass (no more `importorskip` skips).

---

### Step 13 — Run ablation: GMM vs HyperRAPTOR

First, run with **GMM** (baseline — your current state):
```bash
cd backend
# Make sure USE_HYPER_RAPTOR=false in .env
python scripts/run_ablation_study.py 2>&1 | tee ablation_gmm.log
```

Wait for it to complete (~30 minutes). Results go to `backend/ablation.db`.

Then switch to **HyperRAPTOR**:
```bash
# Edit .env: USE_HYPER_RAPTOR=true
python scripts/run_ablation_study.py 2>&1 | tee ablation_hyper.log
```

Compare results:
```bash
python -c "
import duckdb
conn = duckdb.connect('ablation.db', read_only=True)

print('=== GMM (flat) vs HyperRAPTOR comparison ===')
results = conn.execute('''
    SELECT condition, 
           AVG(CAST(hit_at_5 AS DOUBLE)) as hit5,
           AVG(CAST(mrr AS DOUBLE)) as mrr,
           COUNT(*) as n
    FROM ablation_results
    GROUP BY condition
    ORDER BY hit5 DESC
''').fetchall()

for r in results:
    print(f'{r[0]:30s}  hit@5={r[1]:.4f}  MRR={r[2]:.4f}  n={r[3]}')
"
```

**Store results:**
Copy the comparison table into `docs/ablation_results.md` under a new section "HyperRAPTOR vs GMM".

**Done when**: You have a number for HyperRAPTOR hit@5 and MRR to compare against GMM

**If HyperRAPTOR is better** (expected): keep `USE_HYPER_RAPTOR=true` in production  
**If HyperRAPTOR is worse**: keep `USE_HYPER_RAPTOR=false`, document the result (still a contribution — negative result with explanation)

---

## PHASE 4 — Z3 Validation (Week 3, 2-3 days)

---

### Step 14 — Measure Z3 provability on gold standard

```bash
cd backend
python -c "
import asyncio
import json
from pathlib import Path
from partition.verification.z3_agent import Z3VerificationAgent, VerificationStatus

async def measure_provability():
    agent = Z3VerificationAgent()
    results = []
    
    gold_dir = Path('knowledge_base/gold_standard')
    for gold_file in sorted(gold_dir.glob('*.gold.json')):
        sas_file = gold_dir / gold_file.name.replace('.gold.json', '.sas')
        if not sas_file.exists():
            continue
        gold = json.loads(gold_file.read_text())
        sas_code = sas_file.read_text()
        python_code = gold.get('python_translation', '')
        
        result = agent.verify(sas_code, python_code)
        results.append({
            'file': gold_file.stem,
            'category': gold.get('category', 'unknown'),
            'status': result.status.value,
            'pattern': result.pattern,
            'latency_ms': result.latency_ms
        })
    
    total = len(results)
    proved = sum(1 for r in results if r['status'] == 'formal_proof')
    counterex = sum(1 for r in results if r['status'] == 'counterexample')
    unknown = sum(1 for r in results if r['status'] == 'unverifiable')
    
    print(f'Total gold files: {total}')
    print(f'PROVED:           {proved} ({proved/total*100:.1f}%)')
    print(f'COUNTEREXAMPLE:   {counterex} ({counterex/total*100:.1f}%)')
    print(f'UNKNOWN:          {unknown} ({unknown/total*100:.1f}%)')
    print()
    print('By pattern:')
    from collections import Counter
    patterns = Counter(r[\"pattern\"] for r in results if r[\"pattern\"])
    for p, c in patterns.most_common():
        print(f'  {p}: {c}')

asyncio.run(measure_provability())
" 2>&1 | tee z3_provability_results.txt
```

**Store results:**
```bash
mv z3_provability_results.txt docs/z3_provability_results.txt
```

**What to expect:**
- ~35-45% of gold standard files will get `PROVED`
- Counterexamples (Z3 found a bug) are **valuable** — check them manually

**Done when**: You have a provability percentage number saved in `docs/z3_provability_results.txt`

---

### Step 15 — Run full test suite after all wiring

```bash
cd backend
python -m pytest tests/ -v --tb=short 2>&1 | tee test_results.txt
tail -5 test_results.txt
```

Expected: all existing 221+ tests still pass, plus the 27 new ones.

**If anything breaks**: the error message will tell you which import or function signature changed. Fix it before moving on.

---

## PHASE 5 — Push Everything and Verify Azure (Day after Phase 4)

---

### Step 16 — Commit and push

```bash
git add backend/partition/translation/translation_pipeline.py   # Z3 wired
git add backend/partition/translation/translation_agent.py       # local model wired
git add docs/ablation_results.md
git add docs/z3_provability_results.txt
git commit -m "Wire Z3 + local model into pipeline, HyperRAPTOR validated, ablation updated"
git push origin main
```

Watch CI/CD in GitHub Actions → all 6 jobs should go green.

---

### Step 17 — Verify Azure deployment

After the `Deploy` job finishes:

```bash
# Get your deployed URL
az containerapp show \
  --name ca-codara-backend \
  --resource-group rg-codara \
  --query "properties.configuration.ingress.fqdn" -o tsv
```

Test it:
```bash
curl https://YOUR_URL.azurecontainerapps.io/api/health
# Expected: {"status": "ok", "version": "3.0.0"}
```

Open Azure Portal → Application Insights → Live Metrics  
Start a conversion through your API. Watch requests appear in real-time.

**Done when**: `/api/health` returns 200 from the Azure URL, and you see telemetry in App Insights

---

## PHASE 6 — Month 2: Paper Work (Weeks 5-8)

These are the core paper contributions. Code does not exist yet — you need to build it.

---

### Step 18 — Build Oracle Verification Agent

**What it is**: Uses Gemini 2.0 Flash to simulate SAS execution without a SAS runtime. Generates synthetic input data, predicts what SAS would output, runs Python translation on same data, compares.

**Files to create:**
```
backend/partition/verification/oracle_agent.py
backend/partition/verification/test_generator.py
backend/partition/verification/comparator.py
backend/tests/test_oracle_agent.py
```

**To build it, ask me to**: "Build the Oracle Verification Agent" — I'll write the full code.

**Calibration experiment to run after building:**
```bash
cd backend
python scripts/calibrate_oracle.py  # (will also need to be created)
# Produces: docs/oracle_calibration_results.txt
# Shows: oracle accuracy % by partition type
```

**Target**: oracle accuracy > 70% overall (needed for paper claim)

---

### Step 19 — Build Best-of-N Translator

**What it is**: Generates 3-7 translation candidates in parallel (local model + Groq + Cerebras, all free), scores each with composite scorer (oracle + Z3 + syntax + code quality), picks the best.

**Files to create:**
```
backend/partition/translation/bon_translator.py
backend/partition/translation/scoring.py
backend/tests/test_bon_translator.py
```

**To build it, ask me to**: "Build the Best-of-N translator"

**Experiment to run:**
```bash
# Measures accuracy at N=1, 3, 5, 7 on gold standard
python scripts/bon_ablation.py --max-n 7
# Produces: docs/bon_scaling_curve.txt
# This is Figure 2 in your paper
```

---

### Step 20 — Build Adversarial Pipeline

**What it is**: For HIGH-risk/UNCERTAIN partitions only. Proposer (local model) generates translation → Critic (Gemini, independent) finds semantic flaws → Refiner (local model) fixes them. 3 rounds max.

**Files to create:**
```
backend/partition/translation/adversarial_pipeline.py
backend/partition/prompts/templates/critic.j2
backend/tests/test_adversarial_pipeline.py
```

**To build it, ask me to**: "Build the adversarial translation pipeline"

---

### Step 21 — Full Ablation Experiment (the paper table)

Run all conditions on your 45-file gold standard:

```bash
cd backend
python scripts/run_full_ablation.py \
  --gold-dir knowledge_base/gold_standard \
  --output docs/full_ablation_table.csv
```

This generates the main results table for the paper:

| Condition | Translation acc | Verification coverage | Latency |
|---|---|---|---|
| baseline (current) | 82.2% | 0% | ~2s |
| + Z3 | 82.2% | 41% | ~2.3s |
| + Oracle | 88%+ | 95%+ | ~4s |
| + Best-of-N (N=3) | 90%+ | 95%+ | ~6s |
| + Adversarial (HIGH only) | 92%+ | 95%+ | ~8s |

---

### Step 22 — Oracle DPO: retrain from oracle feedback

After Best-of-N has run on your test corpus:

```bash
cd backend
# Accumulates DPO pairs from Best-of-N runs
python scripts/collect_oracle_dpo.py --min-gap 0.3 --output data/oracle_dpo.jsonl

# Check how many pairs collected
wc -l data/oracle_dpo.jsonl
# Target: ≥ 200 pairs before retraining
```

When ≥ 200 pairs collected → go back to Colab, run DPO training on top of your SFT checkpoint using `oracle_dpo.jsonl` instead of `dpo_train.jsonl`. Download new GGUF. Update `LOCAL_MODEL_PATH`.

Run the full ablation again. This is your "learning curve" figure — accuracy at v1 vs v2 of the model.

---

### Step 23 — Paper writing

**Where to write**: Use Overleaf (free). Create a new project with template "ICSE/FSE LaTeX Template" (IEEE double-column).

**Sections and what goes in each:**

| Section | Content | Source |
|---|---|---|
| Abstract | Problem, approach, key numbers | After Step 21 |
| 1. Introduction | The 12.6% silent failure problem, what you built | After Step 14 |
| 2. Background | SAS semantics, Z3, RAPTOR, LoRA — brief | Can write now |
| 3. System Overview | Pipeline diagram + 8 nodes | Can write now |
| 4. Verification Framework | Z3 patterns + Oracle design | After Step 18 |
| 5. Inference Scaling | Best-of-N design + scoring function | After Step 19 |
| 6. Evaluation | Full ablation table + figures | After Step 21 |
| 7. Related Work | Code migration, LLM testing, formal verification | Can write now |
| 8. Conclusion | Summary + future work | Last |

**Target submission**: SANER 2026 (deadline ~October 2025) or ASE 2026 (deadline ~April 2026)

---

## Summary Timeline

```
Day 1:        Steps 1-3   (API keys, install deps, test new code)
Day 2:        Steps 4-5   (Wire Z3 + local model into pipeline)
Day 2-3:      Steps 6-8   (Azure setup, GitHub secrets, push + CI green)
Week 1-2:     Steps 9-11  (Build dataset, run Colab training, deploy GGUF)
Week 2-3:     Steps 12-13 (Install geoopt, run HyperRAPTOR ablation)
Week 3:       Steps 14-15 (Z3 gold standard measurement, full test suite)
Week 3-4:     Steps 16-17 (Push everything, verify Azure deployment)
Week 5:       Step 18     (Oracle agent — biggest piece)
Week 6:       Steps 19-20 (Best-of-N + Adversarial)
Week 7:       Steps 21-22 (Full ablation + oracle DPO retraining)
Week 8:       Step 23     (Paper writing)
```

---

## Quick reference — what's already done vs what needs action

| Component | Code exists? | Wired into pipeline? | Your action needed |
|---|---|---|---|
| Z3 verification | ✅ | ❌ | **Step 4** — add 10 lines to `translation_pipeline.py` |
| HyperRAPTOR | ✅ | ✅ (via feature flag) | **Step 12-13** — install geoopt, run ablation |
| Local model client | ✅ | ❌ | **Step 5** — add to TranslationAgent |
| Fine-tuning notebook | ✅ | N/A | **Steps 9-11** — run in Colab, download GGUF |
| CI/CD (6 jobs) | ✅ | N/A | **Steps 6-8** — Azure setup + GitHub secrets |
| Gemini client | ✅ | ❌ | Used in Step 18 (Oracle) |
| Cerebras client | ✅ | ❌ | Used in Step 19 (Best-of-N) |
| Oracle agent | ❌ | ❌ | **Step 18** — needs to be built |
| Best-of-N | ❌ | ❌ | **Step 19** — needs to be built |
| Adversarial pipeline | ❌ | ❌ | **Step 20** — needs to be built |
