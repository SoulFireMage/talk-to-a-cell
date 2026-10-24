"""
Build data/example_cells.json: real, expert-labelled human blood cells for the demo.

Source: the 10x Genomics PBMC 3k dataset as processed in the scanpy tutorial
(scanpy.datasets.pbmc3k_processed). Its cluster labels are the classic annotations.
Each cell becomes a "cell sentence": gene names ordered by descending expression,
which is the input format C2S was trained on.

Run: venv/bin/python tools/make_examples.py
"""

import json
import random
from pathlib import Path

import numpy as np
import scanpy as sc

CELLS_PER_TYPE = 3
TOP_GENES = 200
SEED = 42

# Plain-English names for the scanpy cluster labels.
FRIENDLY = {
    "CD4 T cells": "CD4 helper T cell",
    "CD8 T cells": "CD8 killer T cell",
    "B cells": "B cell",
    "NK cells": "natural killer (NK) cell",
    "CD14+ Monocytes": "CD14+ classical monocyte",
    "FCGR3A+ Monocytes": "FCGR3A+ non-classical monocyte",
    "Dendritic cells": "dendritic cell",
    "Megakaryocytes": "megakaryocyte / platelet",
}


def main():
    adata = sc.datasets.pbmc3k_processed()
    raw = adata.raw.to_adata()          # all genes, log-normalised; ranking is unaffected
    genes = np.array(raw.var_names)
    X = raw.X.toarray() if hasattr(raw.X, "toarray") else np.asarray(raw.X)

    rng = random.Random(SEED)
    out = []
    for label in FRIENDLY:
        idx = [i for i, l in enumerate(adata.obs["louvain"]) if l == label]
        for n, i in enumerate(rng.sample(idx, min(CELLS_PER_TYPE, len(idx)))):
            row = X[i]
            order = np.argsort(-row, kind="stable")
            order = order[row[order] > 0][:TOP_GENES]
            out.append({
                "id": f"{label.split()[0].lower()}-{n + 1}",
                "label": label,
                "friendly": FRIENDLY[label],
                "barcode": str(adata.obs_names[i]),
                "genes": [str(g) for g in genes[order]],
            })

    dest = Path(__file__).resolve().parent.parent / "data" / "example_cells.json"
    dest.write_text(json.dumps({
        "source": "10x Genomics PBMC 3k (scanpy.datasets.pbmc3k_processed), scanpy tutorial cluster labels",
        "organism": "Homo sapiens",
        "top_genes": TOP_GENES,
        "cells": out,
    }, indent=1))
    print(f"wrote {len(out)} cells to {dest}")


if __name__ == "__main__":
    main()
