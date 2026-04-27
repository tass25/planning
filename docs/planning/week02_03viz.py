"""Week 2-3 Visualization: Streaming Core (no DB artifacts)

This week implemented StreamAgent + StateAgent (the streaming core).
These are code-level modules with no persistent database or graph output.

To visualize Week 2-3 work, you can:
1. Run the streaming pipeline on a sample .sas file.
2. Show the RawBlockEvent objects detected.
3. Display the FSM state transitions as a diagram.

Run from repo root on main:
    python planning/week02_03viz.py [path/to/sample.sas]
"""

import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
except ImportError:
    print("ERROR: Install matplotlib:")
    print("  pip install matplotlib")
    sys.exit(1)

#  Config 
SAMPLE_SAS = "sas_converter/knowledge_base/gold_standard/gs_01_basic_data_step.sas"

if len(sys.argv) > 1:
    SAMPLE_SAS = sys.argv[1]

if not Path(SAMPLE_SAS).exists():
    print(f"ERROR: {SAMPLE_SAS} not found.")
    print("Run from main branch with a valid .sas file path.")
    sys.exit(1)

#  Try to import the streaming agents 
sys.path.insert(0, str(Path.cwd()))

try:
    from sas_converter.partition.streaming.stream_agent import StreamAgent
    from sas_converter.partition.streaming.state_agent import StateAgent
except ImportError as e:
    print(f"ERROR: Cannot import streaming agents: {e}")
    print("Make sure you're on the main branch and sas_converter/ exists.")
    sys.exit(1)

#  Run the streaming pipeline 
print("=" * 70)
print("WEEK 2-3: Streaming Core (StreamAgent + StateAgent)")
print("=" * 70)
print(f"\n Processing: {SAMPLE_SAS}")

import asyncio

async def run_streaming():
    stream_agent = StreamAgent(SAMPLE_SAS)
    state_agent = StateAgent()
    
    events = []
    async for line_num, raw_line in stream_agent.read_lines():
        event = await state_agent.process_line(line_num, raw_line)
        if event:
            events.append(event)
    
    # Flush any pending block
    final_event = state_agent.finalize()
    if final_event:
        events.append(final_event)
    
    return events

try:
    events = asyncio.run(run_streaming())
except Exception as e:
    print(f"ERROR running streaming pipeline: {e}")
    sys.exit(1)

print(f"\n Detected {len(events)} blocks\n")

#  Display event summary 
type_counts = {}
for ev in events:
    btype = ev.block_type
    type_counts[btype] = type_counts.get(btype, 0) + 1

print(" Block type distribution:")
for btype, count in sorted(type_counts.items()):
    print(f"   {btype}: {count}")

#  Visualize block timeline 
fig, ax = plt.subplots(figsize=(14, 8))

colors = {
    'DATA_STEP': 'lightblue',
    'PROC_BLOCK': 'lightgreen',
    'SQL_BLOCK': 'lightyellow',
    'MACRO_DEFINITION': 'lightcoral',
    'MACRO_INVOCATION': 'orange',
    'CONDITIONAL_BLOCK': 'plum',
    'LOOP_BLOCK': 'cyan',
    'GLOBAL_STATEMENT': 'lightgray',
    'INCLUDE_STATEMENT': 'wheat'
}

y_pos = 0
for ev in events:
    start = ev.line_start
    end = ev.line_end
    duration = end - start + 1
    color = colors.get(ev.block_type, 'white')
    
    rect = mpatches.FancyBboxPatch(
        (start, y_pos), duration, 0.8,
        boxstyle="round,pad=0.05",
        edgecolor='black',
        facecolor=color,
        linewidth=0.5
    )
    ax.add_patch(rect)
    
    # Add label
    label_text = f"{ev.block_type}\n[{start}{end}]"
    ax.text(start + duration/2, y_pos + 0.4, label_text,
            ha='center', va='center', fontsize=7, fontweight='bold')
    
    y_pos += 1

ax.set_xlim(0, max(ev.line_end for ev in events) + 5)
ax.set_ylim(0, len(events))
ax.set_xlabel('Line Number', fontsize=12)
ax.set_ylabel('Block Index', fontsize=12)
ax.set_title(f'Week 2-3: Streaming Block Detection Timeline\n{Path(SAMPLE_SAS).name}',
             fontsize=14, fontweight='bold')
ax.grid(True, alpha=0.3)

# Legend
legend_patches = [mpatches.Patch(color=colors[k], label=k) 
                  for k in sorted(set(ev.block_type for ev in events))]
ax.legend(handles=legend_patches, loc='upper right', fontsize=8)

plt.tight_layout()
plt.show()

print("\n Week 2-3 visualization complete.")
print("   (No persistent DB/graph  this week built the streaming core only)")
