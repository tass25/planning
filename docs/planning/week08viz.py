"""Week 08 Visualization -- Orchestration Pipeline Flow + Metrics.

Generates 4 interactive plots:
  1. LangGraph pipeline flow diagram (node DAG)
  2. Pipeline stage timing waterfall (simulated)
  3. Redis checkpoint timeline
  4. LLM audit call distribution per agent

Run:
    cd C:\\Users\\labou\\Desktop\\Stage
    venv\\Scripts\\python planning\\week08viz.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ======================================================================
# Data (hardcoded / simulated -- no runtime databases required)
# ======================================================================

PIPELINE_STAGES = [
    ("INIT",              0.0,  0.1,  "#95a5a6"),
    ("FILE_SCAN",         0.1,  1.8,  "#3498db"),
    ("CROSS_FILE_RESOLVE",1.9,  3.0,  "#2980b9"),
    ("STREAMING",         3.1,  8.5,  "#27ae60"),
    ("BOUNDARY_DETECTION",8.6, 15.2,  "#16a085"),
    ("RAPTOR_CLUSTERING", 15.3, 22.0, "#e67e22"),
    ("COMPLEXITY_ANALYSIS",22.1,25.5, "#e74c3c"),
    ("STRATEGY_ASSIGNMENT",25.6,26.8, "#c0392b"),
    ("PERSISTENCE",       26.9, 30.0, "#8e44ad"),
    ("INDEXING",          30.1, 33.5, "#9b59b6"),
    ("COMPLETE",          33.5, 33.6, "#2ecc71"),
]

CHECKPOINT_EVENTS = [
    (0,   "file_1.sas", True),
    (50,  "file_1.sas", True),
    (100, "file_1.sas", True),
    (150, "file_2.sas", True),
    (200, "file_2.sas", True),
    (250, "file_3.sas", True),
    (300, "file_3.sas", True),
    (350, "file_4.sas", True),
    (400, "file_5.sas", True),
    (450, "file_5.sas", True),
    (500, "pipeline_end", True),
]

LLM_AUDIT_DATA = {
    "BoundaryDetectorAgent": {"calls": 42, "mean_ms": 320, "success": 40, "fail": 2},
    "ClusterSummarizer":     {"calls": 18, "mean_ms": 580, "success": 18, "fail": 0},
    "LLMBoundaryResolver":   {"calls": 15, "mean_ms": 410, "success": 14, "fail": 1},
    "ComplexityAgent":       {"calls": 10, "mean_ms": 250, "success": 10, "fail": 0},
}

PIPELINE_NODES = [
    "file_scan",
    "cross_file_resolve",
    "streaming",
    "boundary_detection",
    "raptor_clustering",
    "complexity_analysis",
    "strategy_assignment",
    "persistence",
    "indexing",
]

LAYER_LABELS = {
    "file_scan": "L2-A",
    "cross_file_resolve": "L2-A",
    "streaming": "L2-B",
    "boundary_detection": "L2-C",
    "raptor_clustering": "L2-C",
    "complexity_analysis": "L2-D",
    "strategy_assignment": "L2-D",
    "persistence": "L2-E",
    "indexing": "L2-E",
}

LAYER_COLORS = {
    "L2-A": "#3498db",
    "L2-B": "#27ae60",
    "L2-C": "#e67e22",
    "L2-D": "#e74c3c",
    "L2-E": "#9b59b6",
}


def plot_pipeline_dag(ax):
    """Plot 1: LangGraph node flow as vertical DAG."""
    n = len(PIPELINE_NODES)
    y_positions = list(range(n - 1, -1, -1))  # top to bottom

    for i, node in enumerate(PIPELINE_NODES):
        layer = LAYER_LABELS[node]
        color = LAYER_COLORS[layer]
        y = y_positions[i]

        # Draw node
        rect = mpatches.FancyBboxPatch(
            (0.2, y - 0.3), 3.6, 0.6,
            boxstyle="round,pad=0.15",
            facecolor=color, edgecolor="white", alpha=0.85,
            linewidth=2,
        )
        ax.add_patch(rect)
        ax.text(2.0, y, f"{layer}: {node}", ha="center", va="center",
                fontsize=9, fontweight="bold", color="white")

        # Draw edge to next node
        if i < n - 1:
            ax.annotate(
                "", xy=(2.0, y_positions[i + 1] + 0.3),
                xytext=(2.0, y - 0.3),
                arrowprops=dict(arrowstyle="->", color="#7f8c8d", lw=1.5),
            )

    # END node
    ax.text(2.0, -1.2, "END", ha="center", va="center",
            fontsize=11, fontweight="bold", color="#2ecc71",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#ecf0f1", edgecolor="#2ecc71", lw=2))
    ax.annotate(
        "", xy=(2.0, -0.9), xytext=(2.0, y_positions[-1] - 0.3),
        arrowprops=dict(arrowstyle="->", color="#7f8c8d", lw=1.5),
    )

    # Legend
    handles = [mpatches.Patch(color=c, label=l) for l, c in LAYER_COLORS.items()]
    ax.legend(handles=handles, loc="upper right", fontsize=8)

    ax.set_xlim(-0.5, 4.5)
    ax.set_ylim(-2, n)
    ax.set_title("LangGraph Pipeline DAG", fontweight="bold", fontsize=12)
    ax.axis("off")


def plot_stage_waterfall(ax):
    """Plot 2: Pipeline stage timing waterfall."""
    stages = PIPELINE_STAGES
    labels = [s[0] for s in stages]
    starts = [s[1] for s in stages]
    durations = [s[2] - s[1] for s in stages]
    colors = [s[3] for s in stages]

    y_pos = np.arange(len(labels))
    ax.barh(y_pos, durations, left=starts, color=colors, height=0.6, edgecolor="white")

    for i, (label, start, dur) in enumerate(zip(labels, starts, durations)):
        ax.text(start + dur / 2, i, f"{dur:.1f}s", ha="center", va="center",
                fontsize=7, fontweight="bold", color="white")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Time (seconds)", fontsize=9)
    ax.set_title("Pipeline Stage Waterfall (10-file run)", fontweight="bold", fontsize=12)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)


def plot_checkpoint_timeline(ax):
    """Plot 3: Redis checkpoint events timeline."""
    blocks = [e[0] for e in CHECKPOINT_EVENTS]
    files = [e[1] for e in CHECKPOINT_EVENTS]
    success = [e[2] for e in CHECKPOINT_EVENTS]

    unique_files = list(dict.fromkeys(files))
    file_colors = plt.cm.Set2(np.linspace(0, 1, len(unique_files)))
    file_color_map = dict(zip(unique_files, file_colors))

    for i, (block, file, ok) in enumerate(CHECKPOINT_EVENTS):
        color = file_color_map[file]
        marker = "o" if ok else "x"
        ax.scatter(block, 0.5, c=[color], marker=marker, s=120, zorder=5, edgecolors="black", linewidths=0.5)
        ax.annotate(file.replace(".sas", ""), (block, 0.55), fontsize=6,
                    rotation=45, ha="left", va="bottom")

    ax.axhline(0.5, color="#bdc3c7", linestyle="--", linewidth=0.8)
    ax.set_xlim(-20, 540)
    ax.set_ylim(0, 1.2)
    ax.set_xlabel("Block Number", fontsize=9)
    ax.set_title("Redis Checkpoint Timeline (interval=50)", fontweight="bold", fontsize=12)
    ax.set_yticks([])

    # Legend
    handles = [mpatches.Patch(color=file_color_map[f], label=f) for f in unique_files]
    ax.legend(handles=handles, loc="lower right", fontsize=7, ncol=2)


def plot_llm_audit(ax):
    """Plot 4: LLM audit call distribution."""
    agents = list(LLM_AUDIT_DATA.keys())
    calls = [d["calls"] for d in LLM_AUDIT_DATA.values()]
    mean_ms = [d["mean_ms"] for d in LLM_AUDIT_DATA.values()]
    successes = [d["success"] for d in LLM_AUDIT_DATA.values()]
    failures = [d["fail"] for d in LLM_AUDIT_DATA.values()]

    x = np.arange(len(agents))
    width = 0.35

    bars1 = ax.bar(x - width / 2, successes, width, label="Success", color="#2ecc71", edgecolor="white")
    bars2 = ax.bar(x + width / 2, failures, width, label="Failure", color="#e74c3c", edgecolor="white")

    # Add latency annotation
    ax2 = ax.twinx()
    ax2.plot(x, mean_ms, "D-", color="#f39c12", markersize=8, linewidth=2, label="Mean latency (ms)")
    ax2.set_ylabel("Mean Latency (ms)", fontsize=9, color="#f39c12")
    ax2.tick_params(axis="y", labelcolor="#f39c12")

    ax.set_xticks(x)
    ax.set_xticklabels(agents, fontsize=8, rotation=15, ha="right")
    ax.set_ylabel("Call Count", fontsize=9)
    ax.set_title("DuckDB LLM Audit Log Summary", fontweight="bold", fontsize=12)

    # Combined legend
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)


def main():
    print("=" * 60)
    print("Week 08 Visualization -- Orchestration Pipeline")
    print("=" * 60)

    print("\n[1] LangGraph Pipeline DAG")
    print(f"    Nodes: {len(PIPELINE_NODES)}")
    print(f"    Layers: {sorted(set(LAYER_LABELS.values()))}")

    print("\n[2] Stage Waterfall")
    total_time = PIPELINE_STAGES[-1][2]
    print(f"    Total pipeline time: {total_time:.1f}s")
    longest = max(PIPELINE_STAGES, key=lambda s: s[2] - s[1])
    print(f"    Slowest stage: {longest[0]} ({longest[2] - longest[1]:.1f}s)")

    print("\n[3] Checkpoint Timeline")
    print(f"    Total checkpoints: {len(CHECKPOINT_EVENTS)}")
    print(f"    Interval: every 50 blocks")
    print(f"    TTL: 24 hours")

    print("\n[4] LLM Audit Summary")
    total_calls = sum(d["calls"] for d in LLM_AUDIT_DATA.values())
    total_fail = sum(d["fail"] for d in LLM_AUDIT_DATA.values())
    print(f"    Total LLM calls: {total_calls}")
    print(f"    Success rate: {(total_calls - total_fail) / total_calls * 100:.1f}%")
    avg_lat = np.mean([d["mean_ms"] for d in LLM_AUDIT_DATA.values()])
    print(f"    Avg latency: {avg_lat:.0f} ms")

    # ---- Draw ----
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Week 08: PartitionOrchestrator -- LangGraph + Redis + DuckDB Audit",
                 fontsize=14, fontweight="bold", y=0.98)

    plot_pipeline_dag(axes[0, 0])
    plot_stage_waterfall(axes[0, 1])
    plot_checkpoint_timeline(axes[1, 0])
    plot_llm_audit(axes[1, 1])

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()

    print("\n>> Visualization complete.")


if __name__ == "__main__":
    main()
