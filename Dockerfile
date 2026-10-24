# Local / self-hosted run (CPU by default). On Hugging Face this app runs as a Gradio
# ZeroGPU Space instead; the @spaces.GPU decorators are no-ops here.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.8.0
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "gradio==5.49.1"
COPY app.py c2s_core.py orchestrator_prompts.py ./
COPY data/example_cells.json data/
ENV GRADIO_SERVER_NAME=0.0.0.0 GRADIO_SERVER_PORT=7860 HF_HOME=/models
VOLUME /models
EXPOSE 7860
CMD ["python", "app.py"]
