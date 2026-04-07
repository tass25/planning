"""
Qwen2.5-Coder-7B QLoRA Fine-tuning for SAS→Python Migration
============================================================
Run this in Google Colab (free T4 GPU) or Lightning AI (free A10G).

IMPORTANT: This is a .py file meant to be copied into a Colab notebook
cell by cell. Each section marked with # == CELL == is one Colab cell.

Colab setup:
  Runtime → Change runtime type → T4 GPU
  Then run cells top to bottom.

Expected training time: ~3-4 hours on T4 for 1000 pairs, 3 epochs.
Expected memory: ~12 GB VRAM with 4-bit QLoRA (T4 has 16 GB).
"""

# == CELL 1: Install ==
# %%
# Install unsloth (fast QLoRA) — must be first
# !pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
# !pip install --no-deps trl peft accelerate bitsandbytes
# !pip install datasets google-generativeai

# == CELL 2: Setup & Config ==
# %%
import os
import json
from pathlib import Path

# Config — adjust these
MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"
MAX_SEQ_LENGTH = 2048   # Qwen2.5 supports up to 131072
LORA_RANK = 16
LORA_ALPHA = 32
BATCH_SIZE = 2
GRAD_ACCUM = 4          # effective batch = 8
EPOCHS = 3
LR = 2e-4
OUTPUT_DIR = "codara-qwen2.5-coder-sas"
HF_USERNAME = "your_huggingface_username"   # ← change this

print(f"Training: {MODEL_NAME}")
print(f"Output:   {OUTPUT_DIR}")

# == CELL 3: Mount Google Drive (optional — for checkpoint persistence) ==
# %%
# from google.colab import drive
# drive.mount('/content/drive')
# CHECKPOINT_DIR = "/content/drive/MyDrive/codara_checkpoints"
# os.makedirs(CHECKPOINT_DIR, exist_ok=True)

# == CELL 4: Load model with unsloth (4-bit QLoRA) ==
# %%
from unsloth import FastLanguageModel
import torch

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,          # auto-detect: bfloat16 on A10G, float16 on T4
    load_in_4bit=True,   # QLoRA
)

# Add LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r=LORA_RANK,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_alpha=LORA_ALPHA,
    lora_dropout=0,      # optimized for unsloth
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
    use_rslora=False,
)

print(f"Model parameters: {model.num_parameters():,}")
print(f"Trainable params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")

# == CELL 5: Load dataset ==
# %%
# Option A: upload your sft_train.jsonl from Colab Files panel
# Option B: load from HuggingFace Hub (after you upload it)

from datasets import load_dataset

# Load from local upload (Files panel on left → upload sft_train.jsonl)
def load_local_jsonl(path: str):
    data = []
    with open(path) as f:
        for line in f:
            data.append(json.loads(line))
    return data

try:
    train_data = load_local_jsonl("/content/sft_train.jsonl")
    val_data = load_local_jsonl("/content/sft_val.jsonl")
    print(f"Loaded local: {len(train_data)} train, {len(val_data)} val")
except FileNotFoundError:
    # Fallback: generate minimal synthetic dataset for testing
    train_data = [
        {
            "instruction": "You are a SAS-to-Python migration expert.",
            "input": "Convert this SAS code to Python:\n\n```sas\ndata output;\n  set input;\n  new_var = old_var * 2;\nrun;\n```",
            "output": "```python\nimport pandas as pd\n\noutput = input.copy()\noutput['new_var'] = output['old_var'] * 2\n```",
            "category": "data_step",
        }
    ] * 10
    val_data = train_data[:2]
    print("WARNING: Using synthetic test data. Upload your sft_train.jsonl for real training.")

# == CELL 6: Format into chat template ==
# %%
def format_example(example: dict) -> str:
    """Format training example into Qwen chat template."""
    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": example["instruction"]},
            {"role": "user",   "content": example["input"]},
            {"role": "assistant", "content": example["output"]},
        ],
        tokenize=False,
        add_generation_prompt=False,
    )

# Verify format
print("Example formatted input:")
print(format_example(train_data[0])[:500])
print("...")

from datasets import Dataset

train_dataset = Dataset.from_list([
    {"text": format_example(ex)} for ex in train_data
])
val_dataset = Dataset.from_list([
    {"text": format_example(ex)} for ex in val_data
])

print(f"\nDataset sizes: {len(train_dataset)} train, {len(val_dataset)} val")

# == CELL 7: SFT Training ==
# %%
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import is_bfloat16_supported

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_dataset,
    eval_dataset=val_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,
    dataset_num_proc=2,
    packing=True,           # pack short sequences → faster training
    args=TrainingArguments(
        per_device_train_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_steps=50,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        fp16=not is_bfloat16_supported(),
        bf16=is_bfloat16_supported(),
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=200,
        output_dir=OUTPUT_DIR,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=42,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
    ),
)

print("Starting SFT training...")
trainer_stats = trainer.train()
print(f"\nTraining complete!")
print(f"  Runtime:     {trainer_stats.metrics['train_runtime']:.0f}s")
print(f"  Train loss:  {trainer_stats.metrics['train_loss']:.4f}")

# == CELL 8: Evaluate perplexity ==
# %%
import math

eval_results = trainer.evaluate()
perplexity = math.exp(eval_results["eval_loss"])
print(f"Validation perplexity: {perplexity:.2f}")
print(f"Target: < 3.0 — {'✓ PASS' if perplexity < 3.0 else '✗ FAIL — train more epochs'}")

# == CELL 9: Test inference before saving ==
# %%
FastLanguageModel.for_inference(model)  # enable fast inference mode

TEST_SAS = """
data patients_clean;
    set patients;
    by patient_id;
    retain running_total 0;
    if first.patient_id then running_total = 0;
    running_total + amount;
    if last.patient_id then output;
run;
"""

inputs = tokenizer.apply_chat_template(
    [
        {"role": "system", "content": "You are a SAS-to-Python migration expert."},
        {"role": "user",   "content": f"Convert this SAS code to Python:\n\n```sas\n{TEST_SAS}\n```"},
    ],
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt",
).to("cuda")

outputs = model.generate(
    input_ids=inputs,
    max_new_tokens=512,
    temperature=0.1,
    do_sample=True,
)
print("Generated translation:")
print(tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True))

# == CELL 10: DPO fine-tuning (optional, run after SFT) ==
# %%
# Only run this if you have dpo_train.jsonl from human corrections

try:
    dpo_data = load_local_jsonl("/content/dpo_train.jsonl")
    print(f"DPO pairs: {len(dpo_data)}")

    from trl import DPOTrainer, DPOConfig

    dpo_dataset = Dataset.from_list(dpo_data)

    dpo_trainer = DPOTrainer(
        model=model,
        ref_model=None,     # implicit ref from LoRA (memory efficient)
        tokenizer=tokenizer,
        train_dataset=dpo_dataset,
        args=DPOConfig(
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            num_train_epochs=1,
            learning_rate=5e-5,
            beta=0.1,
            output_dir=f"{OUTPUT_DIR}-dpo",
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
        ),
    )
    dpo_trainer.train()
    print("DPO complete")
except FileNotFoundError:
    print("No dpo_train.jsonl found — skipping DPO step")

# == CELL 11: Save & Export ==
# %%
# Save LoRA adapters (small, ~100MB)
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"LoRA adapters saved to {OUTPUT_DIR}/")

# Export merged GGUF for local inference (Q4_K_M quantization)
# This is what you load via llama-cpp-python on your local machine
print("Exporting GGUF (Q4_K_M)... this takes ~5 minutes")
model.save_pretrained_gguf(
    f"{OUTPUT_DIR}-gguf",
    tokenizer,
    quantization_method="q4_k_m",
)
print(f"GGUF saved to {OUTPUT_DIR}-gguf/")

# Download to local:
# from google.colab import files
# files.download(f"{OUTPUT_DIR}-gguf/unsloth.Q4_K_M.gguf")

# == CELL 12: Push to HuggingFace Hub (optional) ==
# %%
# from huggingface_hub import login
# login(token="your_hf_token")
# model.push_to_hub(f"{HF_USERNAME}/codara-qwen2.5-coder-sas")
# tokenizer.push_to_hub(f"{HF_USERNAME}/codara-qwen2.5-coder-sas")
# model.push_to_hub_gguf(
#     f"{HF_USERNAME}/codara-qwen2.5-coder-sas-gguf",
#     tokenizer,
#     quantization_method="q4_k_m",
# )
print("Done. Download the GGUF file and set LOCAL_MODEL_PATH in your .env")
