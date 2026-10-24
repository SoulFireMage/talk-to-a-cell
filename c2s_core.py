"""
Cell2Sentence (C2S-Scale) inference: the only part of the app that touches a GPU.

On a Hugging Face ZeroGPU Space, each call to a @spaces.GPU function borrows a GPU
for its duration and charges that time to the *visitor's* daily quota. Elsewhere
(local, Docker, CPU) the decorator does nothing and the model runs on whatever
device is available.

Prompts are the official C2S templates, copied verbatim from
vandijklab/cell2sentence src/cell2sentence/prompts/ (the first template of each task).
"""

import os
import re
from typing import List

import spaces
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = os.getenv("C2S_MODEL_ID", "vandijklab/C2S-Scale-Gemma-2-2B")
MAX_GENES = 1000

PREDICT_TEMPLATE = (
    "The following is a list of {num_genes} gene names ordered by descending expression "
    "level in a {organism} cell. Your task is to give the cell type which this cell "
    "belongs to based on its gene expression.\n"
    "Cell sentence: {cell_sentence}.\n"
    "The cell type corresponding to these genes is:"
)

GENERATE_TEMPLATE = (
    "Generate a list of {num_genes} genes in order of descending expression which "
    "represent a {organism} cell of cell type {cell_type}.\n"
    "Cell sentence:"
)

ORGANISMS = ("Homo sapiens", "Mus musculus")

# ZeroGPU wants the model placed on "cuda" at import time (it emulates CUDA outside
# @spaces.GPU functions), so treat a ZeroGPU Space as a CUDA machine.
ON_ZERO_GPU = bool(os.getenv("SPACES_ZERO_GPU"))
DEVICE = "cuda" if (ON_ZERO_GPU or torch.cuda.is_available()) else "cpu"
DTYPE = torch.bfloat16 if DEVICE == "cuda" else torch.float32

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=DTYPE).to(DEVICE).eval()

# Gemma emits control markers such as "<ctrl100>" after the answer; they survive
# skip_special_tokens, so cut them off explicitly.
_CTRL = re.compile(r"<(?:ctrl\d+|eos|end_of_turn|start_of_turn)>.*", re.DOTALL)

_GENE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")


def parse_genes(text_or_list) -> List[str]:
    """Split on commas/whitespace, drop junk, de-duplicate keeping order, cap length."""
    items = text_or_list if isinstance(text_or_list, list) else re.split(r"[\s,;]+", text_or_list or "")
    seen, genes = set(), []
    for g in items:
        g = str(g).strip().strip(".")
        if g and _GENE_TOKEN.match(g) and g.upper() not in seen:
            seen.add(g.upper())
            genes.append(g)
    return genes[:MAX_GENES]


def _organism(value: str) -> str:
    return value if value in ORGANISMS else "Homo sapiens"


def _generate(prompt: str, max_new_tokens: int) -> str:
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
        )
    text = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return _CTRL.sub("", text)


@spaces.GPU(duration=30)
def predict_cell_type(genes, organism: str = "Homo sapiens") -> dict:
    genes = parse_genes(genes)
    if not genes:
        raise ValueError("No usable gene symbols were given.")
    prompt = PREDICT_TEMPLATE.format(
        num_genes=len(genes), organism=_organism(organism), cell_sentence=" ".join(genes)
    )
    raw = _generate(prompt, max_new_tokens=24)
    answer = raw.strip().split("\n")[0].strip().rstrip(".").strip()
    return {"task": "cell_type_prediction", "prompt": prompt, "raw": raw.strip(),
            "answer": answer, "num_genes": len(genes)}


@spaces.GPU(duration=60)
def generate_cell_sentence(cell_type: str, num_genes: int = 100,
                           organism: str = "Homo sapiens") -> dict:
    cell_type = (cell_type or "").strip().rstrip(".")
    if not cell_type:
        raise ValueError("No cell type was given.")
    num_genes = max(10, min(int(num_genes), 300))
    prompt = GENERATE_TEMPLATE.format(
        num_genes=num_genes, organism=_organism(organism), cell_type=cell_type
    )
    # Gene symbols average roughly 3 tokens each, plus the separating space.
    raw = _generate(prompt, max_new_tokens=num_genes * 4 + 16)
    genes = parse_genes(raw.strip().split("\n")[0])[:num_genes]
    return {"task": "cell_sentence_generation", "prompt": prompt, "raw": raw.strip(),
            "genes": genes, "cell_type": cell_type}
