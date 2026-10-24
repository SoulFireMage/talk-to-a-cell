"""Quick CPU check of the official prompts on a few real example cells."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
t = time.time(); import c2s_core; print(f"model loaded on {c2s_core.DEVICE} in {time.time()-t:.0f}s", flush=True)
cells = json.loads((Path(__file__).resolve().parent.parent / "data/example_cells.json").read_text())["cells"]
for c in cells[::3]:
    t = time.time(); r = c2s_core.predict_cell_type(c["genes"])
    print(f"{c['label']:18s} -> {r['answer']!r:45s} {time.time()-t:.1f}s", flush=True)
t = time.time(); r = c2s_core.generate_cell_sentence("B cell", 50)
print(f"generate B cell ({time.time()-t:.1f}s): {' '.join(r['genes'][:30])}")
r2 = c2s_core.predict_cell_type(r["genes"]); print("round trip ->", r2["answer"])
