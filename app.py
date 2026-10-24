"""
Talk to a Cell: plain-English chat with Cell2Sentence (C2S-Scale).

How a chat turn flows:
  1. Browser JS -> OpenRouter ("understand"), with the visitor's own key.
  2. Gradio event -> run_plan() on the server -> C2S on ZeroGPU (visitor's GPU quota).
  3. Browser JS -> OpenRouter ("explain"), with the visitor's own key.

The OpenRouter key is only ever an input to JS-only events, so it never reaches the
server. Expert mode needs no key at all: it calls C2S directly.
"""

import json
from pathlib import Path

import gradio as gr

import c2s_core
import orchestrator_prompts

HERE = Path(__file__).resolve().parent
EXAMPLES = json.loads((HERE / "data" / "example_cells.json").read_text())
CELLS = EXAMPLES["cells"]
DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash"


def _page_data() -> str:
    data = {
        "cells": [{k: c[k] for k in ("id", "label", "friendly", "genes")} for c in CELLS],
        "prompts": {"understand": orchestrator_prompts.UNDERSTAND,
                    "explain": orchestrator_prompts.EXPLAIN},
    }
    # "</" would end the <script> element early.
    return json.dumps(data).replace("</", "<\\/")


HEAD = """
<script>
window.TTAC = (() => {
  const data = __DATA__;
  const used = new Set();
  const T = { cells: data.cells, prompts: data.prompts };

  T.NO_KEY = "To chat in plain English I need an **OpenRouter key**: open **⚙️ Settings** "
    + "above the chat and paste one in. It stays in your browser and goes only to OpenRouter. "
    + "A key with a small spending cap is a good idea.\\n\\nNo key? The **Expert mode** tab talks to "
    + "C2S directly, no key needed.";

  T.HELP = "I can ask Cell2Sentence to name a cell from its genes, or to write the gene list of a "
    + "typical cell. Try **Show me it working** to test it on a real cell.";

  T.callOR = async (key, model, noReason, system, user, temperature) => {
    const body = {
      model: (model || "").trim() || "__MODEL__",
      messages: [{ role: "system", content: system }, { role: "user", content: user }],
      temperature: temperature,
      max_tokens: 2000,
    };
    if (noReason) body.reasoning = { enabled: false };
    const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + key.trim(),
        "Content-Type": "application/json",
        "X-Title": "Talk to a Cell",
      },
      body: JSON.stringify(body),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error("OpenRouter " + res.status + ": " + ((json.error && json.error.message) || res.statusText));
    const text = json.choices && json.choices[0] && json.choices[0].message && json.choices[0].message.content;
    if (!text || !text.trim()) throw new Error("the model returned nothing (if it is a reasoning model, tick 'Turn off hidden reasoning')");
    return text;
  };

  T.extractJSON = (text) => {
    const t = text.replace(/```(?:json)?/g, "");
    const a = t.indexOf("{"), b = t.lastIndexOf("}");
    if (a < 0 || b <= a) throw new Error("the routing model did not reply with JSON");
    return JSON.parse(t.slice(a, b + 1));
  };

  const contentText = (m) => typeof m.content === "string" ? m.content : "";

  T.historyText = (history) => history.slice(-8).map((m) => {
    const title = m.metadata && m.metadata.title;
    return (title ? "[C2S raw output] " : m.role + ": ") + contentText(m).slice(0, 1500);
  }).filter((s) => s.trim()).join("\\n\\n");

  T.pickCell = (hint) => {
    const h = (hint || "").toLowerCase().replace(/cells?\\b/g, "").trim();
    let pool = T.cells;
    if (h) {
      const match = T.cells.filter((c) => (c.friendly + " " + c.label).toLowerCase().includes(h));
      if (match.length) pool = match;
    }
    let fresh = pool.filter((c) => !used.has(c.id));
    if (!fresh.length) { pool.forEach((c) => used.delete(c.id)); fresh = pool; }
    const cell = fresh[Math.floor(Math.random() * fresh.length)];
    used.add(cell.id);
    return cell;
  };

  T.explainUser = (p, r) => {
    const parts = ["User's question:\\n" + p.question, "Task run: " + r.task];
    if (p.truth) parts.push("This was a REAL cell from a public dataset. Experts labelled it: " + p.truth + ". C2S was not told this.");
    parts.push("Exact prompt sent to C2S:\\n---\\n" + r.prompt.slice(0, 3000) + "\\n---");
    parts.push("C2S raw output:\\n---\\n" + r.raw + "\\n---");
    return parts.join("\\n\\n");
  };

  T.details = (p, r) => {
    const out = ["**Raw output:**", "```", r.raw || "(empty)", "```"];
    if (p.truth) out.push("**Expert label for this cell:** " + p.truth);
    out.push("**Exact prompt sent to C2S** (" + (r.num_genes || "") + (r.num_genes ? " genes" : "") + "):", "```", r.prompt, "```");
    return out.join("\\n");
  };
  return T;
})();
</script>
""".replace("__DATA__", _page_data()).replace("__MODEL__", DEFAULT_MODEL)


UNDERSTAND_JS = """
async (msg, history, key, model, noReason) => {
  // Returns [msg, history, key, model, noReason, plan] to match the inputs; the key slot
  // is always blanked so it never reaches the server.
  const T = window.TTAC;
  const done = (h, plan) => ["", h, "", "", false, plan || ""];
  try {
  msg = (msg || "").trim().replace(/^[^A-Za-z0-9"']+\s/, "");
  history = Array.isArray(history) ? history.slice() : [];
  if (!msg) return done(history);
  const earlier = T.historyText(history);
  history.push({ role: "user", content: msg });
  if (!(key || "").trim()) {
    history.push({ role: "assistant", content: T.NO_KEY });
    return done(history);
  }
  let plan;
  try {
    const user = earlier
      ? "Earlier conversation (most recent last):\\n---\\n" + earlier + "\\n---\\n\\nLatest message, which is what you are routing:\\n" + msg
      : msg;
    plan = T.extractJSON(await T.callOR(key, model, noReason, T.prompts.understand, user, 0));
  } catch (e) {
    history.push({ role: "assistant", content: "⚠️ " + e.message });
    return done(history);
  }
  plan.question = msg;
  if (plan.task === "real_cell_test") {
    const cell = T.pickCell(plan.cell_hint);
    plan.task = "cell_type_prediction";
    plan.genes = cell.genes;
    plan.organism = "Homo sapiens";
    plan.truth = cell.friendly + " (dataset label: " + cell.label + ")";
  }
  const runnable = (plan.task === "cell_type_prediction" && (plan.genes || []).length)
    || (plan.task === "cell_sentence_generation" && plan.cell_type);
  if (!runnable) {
    history.push({ role: "assistant", content: plan.note || T.HELP });
    return done(history);
  }
  history.push({ role: "assistant", content: plan.truth
    ? "🧪 Sending C2S a real blood cell (" + plan.genes.length + " genes, highest first). It isn't told what the cell is…"
    : "🔬 Asking C2S…" });
  return done(history, JSON.stringify(plan));
  } catch (e) {
    return done((Array.isArray(history) ? history : []).concat([{ role: "assistant", content: "⚠️ " + e.message }]));
  }
}
"""

EXPLAIN_JS = """
async (history, plan, result, key, model, noReason) => {
  // Returns [history, plan, result, key, model, noReason] to match the inputs, key blanked.
  const done = (h) => [h, "", "", "", "", false];
  if (!plan || !result) return done(history);
  const T = window.TTAC;
  try {
  history = history.slice();
  const p = JSON.parse(plan), r = JSON.parse(result);
  history.pop();
  if (r.error) {
    history.push({ role: "assistant", content: "⚠️ The C2S call failed: " + r.error });
    return done(history);
  }
  history.push({ role: "assistant", content: T.details(p, r), metadata: { title: "🔬 What C2S actually said", status: "done" } });
  let text;
  try {
    text = await T.callOR(key, model, noReason, T.prompts.explain, T.explainUser(p, r), 0.3);
  } catch (e) {
    text = "C2S answered `" + (r.answer || r.raw).slice(0, 300) + "`. (I couldn't get a plain-English explanation: " + e.message + ")";
  }
  history.push({ role: "assistant", content: text });
  return done(history);
  } catch (e) {
    return done(history.concat([{ role: "assistant", content: "⚠️ " + e.message }]));
  }
}
"""

LOAD_KEY_JS = """
() => { try { const k = localStorage.getItem("ttac.key") || ""; return [k, !!k]; } catch (e) { return ["", false]; } }
"""

SAVE_KEY_JS = """
(key, remember) => {
  try { if (remember && key) localStorage.setItem("ttac.key", key.trim()); else localStorage.removeItem("ttac.key"); } catch (e) {}
  return [];
}
"""


def _no_key(key):
    # Belt and braces: the JS hooks blank the key before the request leaves the browser.
    if key:
        raise gr.Error("Refusing a request that carried an API key to the server.")


def after_understand(_msg, history, key, _model, _no_reason, plan):
    _no_key(key)
    return history, plan, ""


def after_explain(history, _plan, _result, key, _model, _no_reason):
    _no_key(key)
    return history


def run_plan(plan_json: str) -> str:
    """Step 2 of a chat turn. Only C2S work reaches the server; returns "" for no-ops."""
    if not plan_json:
        return ""
    plan = json.loads(plan_json)
    try:
        if plan["task"] == "cell_type_prediction":
            result = c2s_core.predict_cell_type(plan.get("genes") or [], plan.get("organism", ""))
        elif plan["task"] == "cell_sentence_generation":
            result = c2s_core.generate_cell_sentence(
                plan.get("cell_type", ""), plan.get("num_genes") or 100, plan.get("organism", "")
            )
        else:
            return ""
    except Exception as exc:  # noqa: BLE001 - shown to the visitor in the chat
        result = {"error": str(exc)}
    return json.dumps(result)


# ---------------------------------------------------------------- expert mode

EXAMPLE_CHOICES = [(f"Real cell {i + 1} (label hidden)", c["id"]) for i, c in enumerate(CELLS)]
CELL_BY_ID = {c["id"]: c for c in CELLS}


def load_example(cell_id):
    cell = CELL_BY_ID.get(cell_id)
    return (" ".join(cell["genes"]) if cell else ""), cell_id


def expert_predict(genes_text, organism, example_id):
    try:
        r = c2s_core.predict_cell_type(genes_text, organism)
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ {exc}"
    out = [f"### C2S says: **{r['answer'] or '(nothing)'}**",
           f"<small>{r['num_genes']} genes · raw output:</small>", f"```\n{r['raw']}\n```"]
    cell = CELL_BY_ID.get(example_id)
    if cell and c2s_core.parse_genes(genes_text) == cell["genes"]:
        out.append(f"**Experts labelled this cell:** {cell['friendly']} (dataset label: {cell['label']})")
    return "\n\n".join(out)


def expert_generate(cell_type, num_genes, organism):
    try:
        r = c2s_core.generate_cell_sentence(cell_type, num_genes, organism)
    except Exception as exc:  # noqa: BLE001
        return f"⚠️ {exc}", ""
    md = (f"### A typical **{r['cell_type']}**, according to C2S\n\n"
          f"{len(r['genes'])} genes, highest expression first:\n\n```\n{' '.join(r['genes'])}\n```")
    return md, " ".join(r["genes"])


# ---------------------------------------------------------------- page

CSS = """
.ttac-hero { text-align:center; padding: 18px 8px 4px; }
.ttac-hero h1 { font-size: 2.1em; margin: 0; }
.ttac-hero p { opacity: .8; max-width: 760px; margin: 8px auto 0; }
.ttac-quick button { font-size: .9em; }
footer { display:none !important; }
.ttac-foot { font-size: .82em; opacity: .7; text-align:center; padding: 10px; }
"""

HERO = """
<div class="ttac-hero">
  <h1>🧬 Talk to a Cell</h1>
  <p>Chat in plain English with <b>Cell2Sentence</b>, a language model that learned to read
  cells from over 57 million real ones. Its native language is lists of genes; a general AI
  model translates both ways, and you can always see exactly what C2S said.</p>
</div>
"""

FOOT = f"""
<div class="ttac-foot">
Cell model: <a href="https://huggingface.co/{c2s_core.MODEL_ID}" target="_blank">{c2s_core.MODEL_ID}</a>
by the van Dijk Lab (Yale), Google Research and Google DeepMind, CC-BY-4.0 ·
<a href="https://www.biorxiv.org/content/10.1101/2025.04.14.648850v1" target="_blank">paper</a> ·
Example cells: 10x Genomics PBMC 3k ·
GPU time comes from <i>your</i> Hugging Face daily allowance (sign in to huggingface.co for more) ·
A demo for curiosity, not for medical use.
</div>
"""

with gr.Blocks(title="Talk to a Cell", head=HEAD, css=CSS,
               theme=gr.themes.Soft(primary_hue="teal", secondary_hue="indigo")) as demo:
    gr.HTML(HERO)
    plan_box = gr.Textbox(visible=False)
    result_box = gr.Textbox(visible=False)

    with gr.Tab("💬 Chat"):
        with gr.Accordion("⚙️ Settings: your OpenRouter key", open=False):
            gr.Markdown(
                "The chat uses a general AI model through [OpenRouter](https://openrouter.ai), "
                "paid with **your** key. The key stays in this browser tab and is sent only to "
                "OpenRouter, never to this Space's server. A key with a spending cap is a good idea. "
                "Typical cost with the default model: a fraction of a cent per question."
            )
            with gr.Row():
                key = gr.Textbox(label="OpenRouter API key", type="password", placeholder="sk-or-...", scale=3)
                remember = gr.Checkbox(label="Remember on this device", value=False, scale=1)
            with gr.Row():
                model_id = gr.Textbox(label="Translator model (any OpenRouter id)", value=DEFAULT_MODEL, scale=3)
                no_reason = gr.Checkbox(label="Turn off hidden reasoning (faster, cheaper)", value=True, scale=1)

        chatbot = gr.Chatbot(type="messages", height=520, show_copy_button=True, show_label=False,
                             placeholder="Ask anything, or press **Show me it working**.")
        with gr.Row():
            msg = gr.Textbox(show_label=False, placeholder="e.g. Show me a real B cell", scale=5, autofocus=True)
            send = gr.Button("Send", variant="primary", scale=1)
        with gr.Row(elem_classes="ttac-quick"):
            quick = [
                gr.Button("🧪 Show me it working", size="sm"),
                gr.Button("🧠 Which genes define a neuron?", size="sm"),
                gr.Button("🔁 Feed that cell sentence back in", size="sm"),
                gr.Button("❓ What is this, exactly?", size="sm"),
            ]
        clear = gr.Button("Clear chat", size="sm", variant="secondary")

    with gr.Tab("🔬 Expert mode (no key needed)"):
        gr.Markdown("Talk to C2S directly: a ranked gene list in, a cell type out, or the reverse.")
        example_id = gr.State("")
        with gr.Row():
            with gr.Column():
                pick = gr.Dropdown(EXAMPLE_CHOICES, label="Load a real cell (its label is revealed after C2S answers)")
                genes_in = gr.Textbox(label="Gene names, highest expression first", lines=6,
                                      placeholder="MALAT1 B2M TMSB4X CD74 HLA-DRA MS4A1 CD79A ...")
                organism = gr.Radio(list(c2s_core.ORGANISMS), value="Homo sapiens", label="Organism")
                predict_btn = gr.Button("Which cell is this?", variant="primary")
                predict_out = gr.Markdown()
            with gr.Column():
                cell_type_in = gr.Textbox(label="Cell type", placeholder="e.g. B cell, neuron, hepatocyte")
                n_genes = gr.Slider(20, 200, value=100, step=10, label="How many genes")
                gen_btn = gr.Button("Write me a typical cell", variant="primary")
                gen_out = gr.Markdown()
                gen_genes = gr.Textbox(visible=False)
                feed_back = gr.Button("↩ Send these genes to 'Which cell is this?'", size="sm")

    gr.HTML(FOOT)

    # Chat wiring: JS (understand) -> server (C2S) -> JS (explain).
    # Each JS hook runs first and its return value becomes the Python fn's input, so the
    # chain advances through ordinary server events (JS-only events don't fire .then).
    def chain(trigger, source):
        (
            trigger(after_understand, [source, chatbot, key, model_id, no_reason, plan_box],
                    [chatbot, plan_box, msg], js=UNDERSTAND_JS)
            .then(run_plan, plan_box, result_box)
            .then(after_explain, [chatbot, plan_box, result_box, key, model_id, no_reason],
                  chatbot, js=EXPLAIN_JS)
        )

    chain(send.click, msg)
    chain(msg.submit, msg)
    for button in quick:
        chain(button.click, button)
    clear.click(lambda: ([], "", ""), None, [chatbot, plan_box, result_box])

    demo.load(None, None, [key, remember], js=LOAD_KEY_JS)
    key.change(None, [key, remember], None, js=SAVE_KEY_JS)
    remember.change(None, [key, remember], None, js=SAVE_KEY_JS)

    pick.change(load_example, pick, [genes_in, example_id])
    predict_btn.click(expert_predict, [genes_in, organism, example_id], predict_out)
    gen_btn.click(expert_generate, [cell_type_in, n_genes, organism], [gen_out, gen_genes])
    feed_back.click(lambda g: (g, ""), gen_genes, [genes_in, example_id])

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=2).launch(server_name="0.0.0.0")
