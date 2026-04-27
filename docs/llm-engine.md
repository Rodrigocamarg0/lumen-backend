# LLM Engine

Lumen currently runs with external OpenAI models only.

Runtime configuration:

```env
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4.1-nano
OPENAI_API_KEY=
OPENAI_REASONING_EFFORT=
```

The backend does not install local model dependencies in Docker. It should not pull Torch, CUDA,
BitsAndBytes, Transformers, or MLX packages.

RAG remains local to the backend: OpenAI embeddings are searched with FAISS, and the retrieved
corpus chunks are injected into the OpenAI chat prompt.

Docker commands:

```bash
# Local
cd docker
docker compose -f docker-compose.yml up -d --build

# VPS
cd docker
docker compose -f docker-compose.prod.yml up -d --build
```
