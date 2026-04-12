Com base em tudo que foi lido e definido nessa conversa, aqui está o planejamento de cada documento:

---

## `/specs/requirements/`

**O que deve conter:**

Um documento de requisitos focado no projeto de escritores mortos como caso de uso primário do TurboQuant integrado.

- **Product vision**: sistema que permite conversar e simular a escrita/fala de escritores falecidos, com fidelidade de estilo e memória longa de sessão
- **User stories**: usuário conversa com "Machado de Assis" por 2h sem degradação de estilo; usuário faz busca semântica no corpus completo de um autor; usuário ouve resposta sintetizada no estilo do período
- **Acceptance criteria técnicos**: sessões de até 128K tokens sem perda de coerência; KV cache com no máximo 5x expansão de memória; recall do RAG acima de 0.9@k nos textos do autor
- **Constraints**: rodar localmente em WSL2/Docker + GPU consumer; sem fine-tuning obrigatório em runtime; modelo base = Gemma 4 E4B
- **Feature list**: corpus ingestion, vector store comprimido com TurboQuant, KV cache quantizado, geração estilizada, TTS opcional

---

## `/specs/architecture/`

**O que deve conter:**

As decisões de design derivadas diretamente do paper e dos dois repos analisados.

- **Decisão 1 — Quantizador**: usar `TurboQuantMSE` para K e V (não `TurboQuantProd`) — justificativa: QJL adiciona variância que o softmax amplifica; MSE bate Prod na prática (scos-lab finding, confirmado no MLX benchmark com Gemma D=256)
- **Decisão 2 — Bit budget por modelo**: Gemma 4 E4B tem head_dim=256, K/V ratio baixo → 3.5-bit uniforme é suficiente; regra de K/V ratio documentada (tabela do scos-lab)
- **Decisão 3 — Mixed precision**: 5-20% dos canais K com RMS alto → 8-bit; resto → 3-bit; estratégia de detecção de outliers por layer
- **Decisão 4 — Arquitetura do RAG**: embeddings do corpus comprimidos com TurboQuant no FAISS index; retrieval por inner product (não cosine) para aproveitar a precisão do quantizador de produto interno
- **Schema do pipeline**: `corpus → embedder → TurboQuantMSE → FAISS → LLM (Gemma 4 E4B) → KV cache quantizado → resposta`
- **Contratos de integração**: interface do `TurboQuantCache` compatível com HuggingFace `DynamicCache`; hook no `SDPA dispatch`
- **Limitações conhecidas**: speedup real é ~1.85x (não 8x do paper); kernels CUDA dos autores não públicos; llama.cpp integration pending merge

---

## `/specs/tasks/`

**O que deve conter:**

Breakdown por feature em ordem de dependência, com estimativas baseadas no que já existe nos repos.

- **Phase 1 — MVP (Kardec + 5 livros)**: ver detalhamento completo em [`specs/tasks/phase-1-mvp.md`](./specs/tasks/phase-1-mvp.md)
  - Backend Foundation: FastAPI scaffolding em `backend/app/` + LLM engine (Gemma 4 E4B)
  - Corpus Pipeline: ingestão, parsing, chunking, embedding, FAISS indexing — tudo em `backend/app/corpus/` e `backend/data/kardec/`
  - Persona + RAG: system prompt + RAG retrieval em `backend/app/persona/`
  - API: Chat + Search endpoints com SSE em `backend/app/api/`
  - Frontend: conectar `frontend/index.html` ao backend (substituir mocks)
  - Docker: `docker compose up` sobe tudo
- **Phase 2 — TurboQuant**: clonar OmarHory/turboquant, validar 30/30 checks, integrar `TurboQuantCache` em `backend/app/cache/`, comprimir FAISS embeddings
- **Phase 3 — Multi-Persona**: Emmanuel, Joanna de Angelis, André Luiz; session persistence; needle-in-haystack tests
- **Phase 4 — TTS (opcional)**: integração de síntese de voz; voice cloning se corpus de áudio disponível
- **Cada task deve ter**: input/output definido, dependências, critério de done, modelo de teste

---

## `AGENTS.md`

**O que deve conter:**

Regras globais que todos os agentes de IA devem seguir ao trabalhar neste projeto. Atualizado para refletir a estrutura `frontend/` + `backend/`.

- **Contexto do projeto**: sistema de compressão de KV cache para sessões longas; modelo alvo Gemma 4 E4B; stack Python/FastAPI/Docker/WSL2
- **Estrutura do projeto**: `frontend/` para HTML/JS/Tailwind estático; `backend/` para Python/FastAPI; `specs/` para documentação; `evals/` para avaliações; `docker/` para contêineres
- **Restrições de código**: nunca usar `TurboQuantProd` para K ou V sem justificativa explícita; sempre verificar K/V ratio do modelo antes de definir bit budget; não assumir que o speedup de 8x do paper é atingível sem kernels CUDA otimizados
- **Padrão de validação**: toda mudança no quantizador deve passar nos 30 checks do `validate_algorithms.py` e medir MSE contra os bounds teóricos do paper
- **Regras de memória/contexto**: agentes não devem dequantizar o KV cache para operações intermediárias — operar diretamente nos índices comprimidos via QuantizedAttention
- **Referências canônicas**: arXiv 2504.19874 como verdade do algoritmo; scos-lab/turboquant como referência de findings empíricos; OmarHory/turboquant como referência de implementação GPU

---

## `/specs/agents/agente-codex.md` (a ser criado)

**O que deve conter:**

Steering específico para o agente que vai escrever e modificar código do pipeline.

- **Responsabilidade**: implementação dos módulos em `backend/app/` — corpus, llm, persona, api; e integrações no `frontend/`
- **Conhecimento requerido**: estrutura dos dois repos (OmarHory para GPU, scos-lab para referência NumPy); diferença entre `TurboQuantMSE` e `TurboQuantProd` e quando usar cada um; layout de memória dos índices comprimidos (52 bytes por vetor de 128 valores a 3-bit)
- **Padrões obrigatórios**: usar `dataclass(frozen=True)` para `QuantizedMSE` e `QuantizedProd`; separar rotation matrix da lógica de quantização; nunca armazenar a rotation matrix junto com os índices comprimidos
- **Armadilhas documentadas**: Gemma 4 tem `head_dim=256` — codebooks Lloyd-Max pré-computados para d=128 não servem diretamente; Qwen com K/V ratio > 100x não funciona bem com 3-bit uniforme

---

## `/specs/agents/agente-claude.md` (a ser criado)

**O que deve conter:**

Steering para o agente que vai coordenar pesquisa, análise de papers e decisões de arquitetura.

- **Responsabilidade**: interpretação de novos papers relacionados a quantização e KV cache; atualização dos docs de arquitetura quando findings empíricos contradizerem o paper (ex: MSE > Prod na prática); análise do K/V ratio de novos modelos alvo antes de definir bit budget
- **Fontes canônicas e como usá-las**: arXiv 2504.19874 seções 3.1 e 3.2 como referência de algoritmo; scos-lab BENCHMARK_RESULTS.md como referência de findings não documentados no paper; Incept5/gemma4-benchmark como referência de comportamento em contexto longo
- **Protocolo de decisão**: quando há contradição entre paper e findings empíricos, documentar ambos em `/specs/architecture/` com o contexto (ex: MSE vs Prod depende do modelo e do head_dim); nunca descartar o paper sem evidência empírica documentada
- **Output esperado**: atualizações nos docs de `/specs/architecture/` com decisões justificadas; tasks novas em `/specs/tasks/` quando descoberta de pesquisa exige mudança de implementação

---

## `/evals/`

**O que deve conter:**

Suite de avaliação para o pipeline TurboQuant + escritores mortos.

- **`turboquant_eval.py`**: validação dos 30 checks de bounds teóricos (já existe no OmarHory repo, adaptar); distorção MSE vs bounds do paper para Gemma 4 E4B com head_dim=256; inner product error com e sem QJL
- **`kv_cache_eval.py`**: medir compressão real de memória (alvo: ~5x como nos benchmarks do Gemma 4); degradação de perplexidade em 3.5-bit (alvo: zero-loss); needle-in-haystack no corpus do escritor em 4K, 16K, 64K, 128K tokens
- **`persona_eval.py`**: métricas de fidelidade de estilo ao longo da sessão (n-gram overlap com corpus, perplexidade do modelo no estilo do autor); coerência de persona em sessões de 50+ turnos; recall do RAG no corpus
- **Critério de regressão**: qualquer mudança no quantizador deve ser acompanhada de diff nas métricas destes três arquivos antes do merge
