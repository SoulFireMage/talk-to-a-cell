---
title: Talk to a Cell
emoji: 🧬
colorFrom: green
colorTo: indigo
sdk: gradio
sdk_version: 5.49.1
python_version: "3.12"
app_file: app.py
pinned: false
license: mit
short_description: Chat in plain English with Cell2Sentence, a cell-reading LLM
models:
  - vandijklab/C2S-Scale-Gemma-2-2B
preload_from_hub:
  - vandijklab/C2S-Scale-Gemma-2-2B
tags:
  - biology
  - single-cell
  - cell2sentence
  - scRNA-seq
---

# 🧬 Talk to a Cell

Chat in plain English with **Cell2Sentence (C2S-Scale)**, a language model from the van Dijk
Lab (Yale), Google Research and Google DeepMind that learned to read cells from over 57 million
real ones. C2S's native language is the "cell sentence": a cell's gene names, ordered from
most to least expressed. It can name a cell from its genes, or write the genes of a typical cell.

This app puts a general AI model either side of it, so you can just ask:

- **"Show me it working"** sends C2S a *real* human blood cell from a public dataset, labelled
  by experts, without telling C2S the answer, then says whether it got it right.
- **"Which genes define a neuron?"** has C2S write a typical neuron's cell sentence.
- **"Feed that back in"** is the round trip: does C2S recognise its own cell?

Every answer has a **"What C2S actually said"** box with the raw output and the exact prompt,
so you can always tell the specialist model's answer from the translator's commentary.

## Who pays for what

- **The translator (plain-English layer)** runs on [OpenRouter](https://openrouter.ai) with
  **your own key**. The key stays in your browser tab and is sent only to OpenRouter, never to
  this Space's server. Use a key with a spending cap. With the default model, a question
  costs a fraction of a cent.
- **C2S itself** runs on Hugging Face **ZeroGPU**. Its GPU time comes from *your* Hugging Face
  daily allowance; signing in to huggingface.co gives you more.
- **Expert mode** needs no key: paste a gene list (or load a real cell) and talk to C2S
  directly.

## How it works

```
browser ── your key ──> OpenRouter  "understand": what does the user want?
   │
   └──> this Space (ZeroGPU) ──> C2S-Scale-Gemma-2-2B  (official C2S prompt templates)
   │
browser ── your key ──> OpenRouter  "explain": plain English, raw output kept visible
```

- `c2s_core.py`: model loading and the two C2S tasks, using the official prompt templates
  from [vandijklab/cell2sentence](https://github.com/vandijklab/cell2sentence).
- `orchestrator_prompts.py`: instructions for the translator model.
- `app.py`: the Gradio page. The OpenRouter calls run in browser-side JS hooks, which blank
  the key before anything reaches the server, and the server refuses any request that
  carries one.
- `data/example_cells.json`: 24 real cells (3 each of 8 blood cell types) from 10x Genomics
  PBMC 3k, top 200 genes. Made by `tools/make_examples.py`.

## Run it yourself

```bash
docker build -t talk-to-a-cell .
docker run -p 7860:7860 -v c2s-models:/models talk-to-a-cell   # http://localhost:7860
```

Or with Python 3.12: `pip install -r requirements.txt gradio==5.49.1 && python app.py`.
It runs on CPU (around 15 s per cell on a laptop) or a GPU, automatically. Set
`C2S_MODEL_ID=vandijklab/C2S-Scale-Gemma-2-27B` for the big model if you have the GPU for it.

## Credits

- Model: [C2S-Scale-Gemma-2-2B](https://huggingface.co/vandijklab/C2S-Scale-Gemma-2-2B), CC-BY-4.0.
  Paper: [Scaling Large Language Models for Next-Generation Single-Cell Analysis](https://www.biorxiv.org/content/10.1101/2025.04.14.648850v1).
- Example cells: 10x Genomics PBMC 3k, with the cluster labels from the scanpy tutorial.
- App by [SoulFireMage](https://huggingface.co/SoulFireMage), MIT licence.

A demo for curiosity and learning, not for medical or diagnostic use.
