 1. Build a Gold Dataset
  Create a set of user-like questions where you know which chunk(s) should be retrieved.

  Use three categories:

  - exact_question: original L.E. question text.
  - near_paraphrase: same question rewritten with synonyms.
  - conceptual_query: user asks the idea, not the wording.

  Example:

  {
    "query": "Antes de reencarnar, o espírito sabe o que vai passar na vida?",
    "expected_ids": ["lde-q0258"],
    "type": "near_paraphrase"
  }

  Important: allow multiple valid chunks. Some fixture labels may be too strict; for “inferno”, a CeI chunk may be better than L.E. Q1008.

  2. Measure Retrieval Before Generation
  Do not test the LLM answer first. Test whether the right documents are even reaching the model.

  Metrics:

  - Recall@10: is the expected chunk in the top 10?
  - MRR: how high is the first correct chunk?
  - NDCG@10: useful if multiple chunks are relevant.
  - Miss analysis: what came top instead?

  Your current data says:

  - Exact L.E. question text: Recall@10 = 1.0
  - Short paraphrase fixture: Recall@10 = 0.36, reranked 0.44

  That means embeddings work for exact wording, but not enough for conceptual/paraphrased questions.

  3. Inspect Failures Manually
  For every miss, classify why it failed:

  - Expected chunk is wrong or too narrow.
  - Query is too short/vague.
  - A better chunk from another book was retrieved.
  - Chunk text is too long and answer dilutes the question embedding.
  - User wording uses synonyms absent from the source.
  - The retrieved result is actually acceptable.

  This is where you decide whether the issue is dataset labeling, chunking, embedding, or ranking.

  4. Test Improvements One at a Time
  A good experiment ladder:

  1. Baseline FAISS embedding search.
  2. Larger candidate pool: top 50, 100, 200.
  3. Question-text reranker, like we added.
  4. Hybrid lexical + semantic search, e.g. BM25 plus embeddings.
  5. Query expansion, e.g. generate 3 alternative search queries.
  6. Cross-encoder/LLM reranker over top 50 candidates.
  7. Chunk representation changes: embed question separately from answer.

  For this corpus, I would test these next:

  - Embed question_only separately for L.E. chunks.
  - Search against both texto and question_only.
  - Add BM25 lexical retrieval for exact doctrinal terms.
  - Rerank top 50 with a small LLM or cross-encoder-style prompt.

  5. Optimize for Answer Quality, Not Just Chunk ID
  After retrieval improves, evaluate the LLM answer:

  - Did it cite the right chunk?
  - Did it answer from the retrieved text?
  - Did it hallucinate?
  - Was the answer complete?

  But this should come after retrieval metrics are stable.

  Best Next Step
  I’d create a stronger eval set with about:

  - 100 exact questions
  - 100 paraphrases
  - 100 conceptual questions
  - multiple accepted chunk IDs per query

  Then run every retrieval strategy against that. The output should be a table like:

  strategy                 exact@10   paraphrase@10   conceptual@10
  semantic baseline        1.00       0.36            0.28
  question rerank          1.00       0.44            0.30
  hybrid bm25+semantic     ...
  question-only embeddings ...
  LLM reranker             ...

  That tells you scientifically what actually improves responses.
