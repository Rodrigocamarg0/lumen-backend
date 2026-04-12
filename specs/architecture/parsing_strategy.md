# Corpus Parsing Strategy — Kardec 5 Books

> **Version:** 1.0
> **Date:** 2026-04-11
> **Assignee:** agente-claude (Research Agent)
> **Consumed by:** agente-codex — `backend/app/corpus/parser.py`, `backend/app/corpus/chunker.py`
> **Companion documents:** [architecture.md](./architecture.md) · [requirements.md](../requirements/requirements.md) · [LUMEN_CONTEXT.md](../../LUMEN_CONTEXT.md)

---

## 1. Overview

This document defines the exact extraction and chunking rules for each of the five Kardec books located in `/books/`. The goal is to produce a set of JSON chunks conforming to the canonical `Chunk` metadata schema, ready for embedding and FAISS indexing.

Source files:
```
books/WEB-Livro-dos-Espíritos-Guillon-1.pdf
books/WEB-Livro-dos-Mediuns-Guillon-1.pdf
books/WEB-O-Evangelho-segundo-o-Espiritismo-Guillon.pdf
books/WEB-O-Ceu-e-o-inferno-Guillon.pdf
books/WEB-A-Genese-Guillon.pdf
```

---

## 2. Canonical Chunk Metadata Schema

Every chunk produced by the pipeline must conform to this schema:

```json
{
  "id": "lde-q223",
  "autor": "Allan Kardec",
  "medium": null,
  "obra": "O Livro dos Espíritos",
  "parte": "Parte Segunda — Do Mundo Espírita",
  "capitulo": "I — Os Espíritos",
  "questao": 223,
  "texto": "...",
  "edicao_referencia": "FEB, 2013"
}
```

### Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `str` | Yes | Unique chunk identifier. Format per book (see §3). |
| `autor` | `str` | Yes | Always `"Allan Kardec"` for Phase 1. |
| `medium` | `str \| null` | Yes | Psychographic medium (null for Kardec — he was the codifier). |
| `obra` | `str` | Yes | Full canonical title of the work (see §3 per book). |
| `parte` | `str \| null` | Conditionally | Part/section heading if applicable. |
| `capitulo` | `str \| null` | Conditionally | Chapter heading if applicable. |
| `questao` | `int \| null` | Conditionally | Question number for Q&A works. null for narrative works. |
| `texto` | `str` | Yes | The extracted text content, cleaned of headers/footers/page numbers. |
| `edicao_referencia` | `str` | Yes | Edition reference (see §3 per book). |

---

## 3. Per-Book Extraction Rules

### 3.1 O Livro dos Espíritos (LdE)

**File:** `WEB-Livro-dos-Espíritos-Guillon-1.pdf`
**ID prefix:** `lde-q{N}` (e.g., `lde-q001`, `lde-q1019`)
**Obra:** `"O Livro dos Espíritos"`
**Chunking unit:** One chunk per numbered question (1,019 total)
**Edicao:** `"FEB, 2013 (Tradução Guillon Ribeiro)"`

#### 3.1.1 Document Structure

The PDF is organized as follows:
- Front matter: title page, introduction ("Prolegômenos"), preface
- **Livro Primeiro** — Das Causas Primárias
  - Cap. I — Deus
  - Cap. II — Os Elementos Gerais do Universo
  - Cap. III — Da Criação
  - Cap. IV — Princípio Vital
- **Livro Segundo** — Do Mundo Espírita ou dos Espíritos
  - Cap. I — Dos Espíritos
  - ... (multiple chapters)
- **Livro Terceiro** — Das Leis Morais
  - ... (multiple chapters)
- **Livro Quarto** — Das Esperanças e Consolações
  - ... (multiple chapters)

> **Note:** The top-level divisions are called "Livro" in the Portuguese editions but correspond to "Parte" in the canonical metadata schema used by Lumen. Map accordingly.

#### 3.1.2 Question Block Structure

Each question block in the PDF follows this pattern:
```
{QUESTION_NUMBER}. {QUESTION_TEXT}
"{SPIRIT_ANSWER}"
{OPTIONAL_KARDEC_COMMENTARY}
```

Example:
```
1. O que é Deus?
"Deus é a inteligência suprema, causa primária de todas as coisas."
...
```

Some questions have sub-questions (lettered: a, b, c):
```
77. O que é a alma?
"Um espírito encarnado."
77a. Qual a natureza da alma?
"A natureza do espírito."
```

Sub-questions are included as part of the parent question chunk. Do NOT split sub-questions into separate chunks.

#### 3.1.3 Regex Extraction Patterns

```python
import re

# Detect question start — one or more digits, followed by period and space
QUESTION_START = re.compile(r'^(\d+)\.\s+(.+)', re.MULTILINE)

# Detect sub-question (appended to parent chunk)
SUB_QUESTION = re.compile(r'^(\d+)([a-z])\.\s+(.+)', re.MULTILINE)

# Detect part heading (Livro → Parte)
PART_HEADING = re.compile(
    r'^(LIVRO\s+(?:PRIMEIRO|SEGUNDO|TERCEIRO|QUARTO))',
    re.IGNORECASE | re.MULTILINE
)

# Detect chapter heading
CHAPTER_HEADING = re.compile(
    r'^CAPÍTULO\s+(I{1,3}V?|V?I{0,3}X?)\s*[—–-]\s*(.+)',
    re.IGNORECASE | re.MULTILINE
)

# Page number / header artifact (to strip)
PAGE_ARTIFACT = re.compile(r'^\d+\s*$', re.MULTILINE)
HEADER_ARTIFACT = re.compile(
    r'^(O LIVRO DOS ESPÍRITOS|ALLAN KARDEC)\s*$',
    re.IGNORECASE | re.MULTILINE
)
```

#### 3.1.4 Extraction Algorithm (Pseudo-code)

```python
def extract_lde_chunks(text: str) -> list[dict]:
    chunks = []
    current_parte = None
    current_capitulo = None

    lines = text.split('\n')
    i = 0
    question_buffer = []
    current_question_number = None

    while i < len(lines):
        line = lines[i].strip()

        # Strip page artifacts
        if PAGE_ARTIFACT.match(line) or HEADER_ARTIFACT.match(line):
            i += 1
            continue

        # Detect part heading
        part_match = PART_HEADING.match(line)
        if part_match:
            # Flush any buffered question
            if question_buffer and current_question_number:
                chunks.append(build_lde_chunk(
                    current_question_number, question_buffer,
                    current_parte, current_capitulo
                ))
                question_buffer = []
                current_question_number = None
            current_parte = normalize_parte(part_match.group(1))
            i += 1
            continue

        # Detect chapter heading
        chapter_match = CHAPTER_HEADING.match(line)
        if chapter_match:
            if question_buffer and current_question_number:
                chunks.append(build_lde_chunk(...))
                question_buffer = []
                current_question_number = None
            current_capitulo = f"{chapter_match.group(1)} — {chapter_match.group(2)}"
            i += 1
            continue

        # Detect new question start (flush previous)
        question_match = QUESTION_START.match(line)
        if question_match:
            q_num = int(question_match.group(1))
            # Only treat as new question if number is sequential (prevents false positives)
            if current_question_number is None or q_num == current_question_number + 1:
                if question_buffer and current_question_number:
                    chunks.append(build_lde_chunk(
                        current_question_number, question_buffer,
                        current_parte, current_capitulo
                    ))
                current_question_number = q_num
                question_buffer = [line]
                i += 1
                continue

        # Accumulate into current question buffer
        if current_question_number is not None:
            question_buffer.append(line)
        i += 1

    # Flush final question
    if question_buffer and current_question_number:
        chunks.append(build_lde_chunk(...))

    return chunks


def build_lde_chunk(q_num, lines, parte, capitulo) -> dict:
    return {
        "id": f"lde-q{q_num:04d}",
        "autor": "Allan Kardec",
        "medium": None,
        "obra": "O Livro dos Espíritos",
        "parte": parte,
        "capitulo": capitulo,
        "questao": q_num,
        "texto": clean_text('\n'.join(lines)),
        "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)"
    }
```

#### 3.1.5 ID Mapping

| Question Range | Parte | Notes |
|---|---|---|
| 1–49 | Parte Primeira — Das Causas Primárias | Includes sub-questions (1a, 1b, etc.) |
| 50–228 | Parte Segunda — Do Mundo Espírita | Longest section |
| 229–421 | Parte Terceira — Das Leis Morais | |
| 422–1019 | Parte Quarta — Das Esperanças e Consolações | |

> **Validation:** After extraction, `len(chunks)` must be between 1019 and ~1100 (sub-questions may inflate count if split; they should NOT be split). Assert `max(c['questao'] for c in chunks) == 1019`.

---

### 3.2 O Livro dos Médiuns (LdM)

**File:** `WEB-Livro-dos-Mediuns-Guillon-1.pdf`
**ID prefix:** `ldm-a{N}` (e.g., `ldm-a001`, `ldm-a334`)
**Obra:** `"O Livro dos Médiuns"`
**Chunking unit:** One chunk per numbered article (334 total)
**Edicao:** `"FEB, 2013 (Tradução Guillon Ribeiro)"`

#### 3.2.1 Document Structure

O Livro dos Médiuns is organized into two parts:
- **Parte Primeira** — Noções Preliminares
- **Parte Segunda** — Das Manifestações Físicas e Inteligentes
  - Cap. I — Teoria das Manifestações Físicas
  - Cap. II — Das Mesas e dos Objetos Girantes
  - ... (multiple chapters of Q&A and narrative)

The text mixes narrative passages with numbered Q&A articles. Articles are numbered sequentially within sections.

#### 3.2.2 Article Detection

Articles in LdM begin with a bold or capitalized heading:

```python
ARTICLE_HEADING = re.compile(
    r'^(\d+)\.\s+(.{5,80}?)(?:\n|$)',  # numbered heading, 5–80 chars
    re.MULTILINE
)

# Alternative: some editions use "Art." prefix
ARTICLE_PREFIX = re.compile(r'^Art\.\s+(\d+)', re.MULTILINE | re.IGNORECASE)
```

**Heuristic:** Treat any line matching `^\d+\.\s+[A-ZÁÉÍÓÚ]` as a potential article start. Filter false positives by requiring the article number to be sequential (±1 from previous article) or within the known range 1–334.

#### 3.2.3 Chunk Construction

```python
def build_ldm_chunk(art_num, lines, parte, capitulo) -> dict:
    return {
        "id": f"ldm-a{art_num:03d}",
        "autor": "Allan Kardec",
        "medium": None,
        "obra": "O Livro dos Médiuns",
        "parte": parte,
        "capitulo": capitulo,
        "questao": None,  # LdM uses articles, not numbered questions
        "texto": clean_text('\n'.join(lines)),
        "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)"
    }
```

---

### 3.3 O Evangelho Segundo o Espiritismo (ESE)

**File:** `WEB-O-Evangelho-segundo-o-Espiritismo-Guillon.pdf`
**ID prefix:** `ese-c{NN}-p{NNN}` (e.g., `ese-c01-p001`)
**Obra:** `"O Evangelho Segundo o Espiritismo"`
**Chunking unit:** Paragraph-level with 2-paragraph sliding overlap
**Edicao:** `"FEB, 2013 (Tradução Guillon Ribeiro)"`

#### 3.3.1 Document Structure

O Evangelho consists of 28 chapters, each with:
- A title (e.g., "Cap. I — O Sermão da Montanha")
- Introductory narrative
- Numbered items or sections (some chapters)
- Kardec's commentary after scriptural quotes

#### 3.3.2 Paragraph Extraction

```python
def extract_ese_chunks(text: str) -> list[dict]:
    chunks = []
    chapters = split_by_chapter(text)  # splits at "CAPÍTULO I", "CAPÍTULO II", etc.

    CHAPTER_HEADING = re.compile(
        r'CAP[ÍI]TULO\s+(I{1,3}V?|V?I{0,3}X?|X{1,3})\s*[—–-]?\s*(.*)',
        re.IGNORECASE
    )

    for chap_num, (chap_heading, chap_text) in enumerate(chapters, start=1):
        paragraphs = extract_paragraphs(chap_text)  # split on blank lines, min 30 chars
        p_seq = 0

        for i, para in enumerate(paragraphs):
            # Build windowed chunk: current paragraph + up to 2 following paragraphs
            window = paragraphs[i:i+3]  # overlap = 2 paragraphs
            chunk_text = '\n\n'.join(window)
            p_seq += 1

            chunks.append({
                "id": f"ese-c{chap_num:02d}-p{p_seq:03d}",
                "autor": "Allan Kardec",
                "medium": None,
                "obra": "O Evangelho Segundo o Espiritismo",
                "parte": None,
                "capitulo": chap_heading,
                "questao": None,
                "texto": clean_text(chunk_text),
                "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)"
            })

    return chunks
```

#### 3.3.3 Paragraph Splitting Heuristic

```python
def extract_paragraphs(text: str, min_chars: int = 30) -> list[str]:
    """
    Split on blank lines. Filter out headers, page numbers, and very short
    lines (likely artifacts). Minimum 30 chars per paragraph to skip
    section headings that appear as standalone lines.
    """
    raw_paras = re.split(r'\n\s*\n', text)
    return [
        p.strip() for p in raw_paras
        if len(p.strip()) >= min_chars
        and not re.match(r'^\d+\s*$', p.strip())  # not a page number
        and not re.match(r'^O EVANGELHO', p.strip(), re.IGNORECASE)  # not a header
    ]
```

---

### 3.4 O Céu e o Inferno (CeI)

**File:** `WEB-O-Ceu-e-o-inferno-Guillon.pdf`
**ID prefix:** `cei-p{N}-p{NNN}` (e.g., `cei-p1-p001`, `cei-p2-p001`)
**Obra:** `"O Céu e o Inferno"`
**Chunking unit:** Paragraph-level with 2-paragraph overlap
**Edicao:** `"FEB, 2013 (Tradução Guillon Ribeiro)"`

#### 3.4.1 Document Structure

O Céu e o Inferno has two major parts:
- **Parte Primeira** — Doutrina (doctrinal chapters)
- **Parte Segunda** — Exemplos (case studies / narrative accounts of spirits)

The Parte Segunda chapters are structured as individual spirit accounts and can be chunked at the account level rather than paragraph level when the account is clearly delimited.

#### 3.4.2 Part Detection

```python
PART_ONE = re.compile(r'PARTE\s+PRIMEIRA', re.IGNORECASE)
PART_TWO = re.compile(r'PARTE\s+SEGUNDA', re.IGNORECASE)

SPIRIT_ACCOUNT = re.compile(
    r'^(\d+)\.\s+([A-Z][A-ZÁÉÍÓÚ\s]+?)(?:\n|\.)',  # numbered spirit accounts in Part 2
    re.MULTILINE
)
```

#### 3.4.3 Chunk Construction

```python
def build_cei_chunk(parte_num, para_seq, lines, capitulo) -> dict:
    return {
        "id": f"cei-p{parte_num}-p{para_seq:03d}",
        "autor": "Allan Kardec",
        "medium": None,
        "obra": "O Céu e o Inferno",
        "parte": f"Parte {'Primeira' if parte_num == 1 else 'Segunda'}",
        "capitulo": capitulo,
        "questao": None,
        "texto": clean_text('\n'.join(lines)),
        "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)"
    }
```

---

### 3.5 A Gênese (Gen)

**File:** `WEB-A-Genese-Guillon.pdf`
**ID prefix:** `gen-c{NN}-p{NNN}` (e.g., `gen-c01-p001`)
**Obra:** `"A Gênese"`
**Chunking unit:** Paragraph-level with 2-paragraph overlap
**Edicao:** `"FEB, 2013 (Tradução Guillon Ribeiro)"`

#### 3.5.1 Document Structure

A Gênese has 19 chapters covering scientific and spiritual cosmology:
- Cap. I — Prolegômenos
- Cap. II — Gênese Espírita
- ... through Cap. XIX

Each chapter is heavily scientific in tone, referencing 19th-century astronomy, geology, and biology alongside Spiritist doctrine.

#### 3.5.2 Chapter Detection

```python
CHAPTER_HEADING_GEN = re.compile(
    r'CAP[ÍI]TULO\s+(I{1,3}V?|V?I{0,3}X{0,3}I{0,3})\s*[—–-]?\s*(.*)',
    re.IGNORECASE | re.MULTILINE
)
```

#### 3.5.3 Chunk Construction

Same as ESE (§3.3), replacing `ese` with `gen` in the ID prefix.

---

## 4. Text Cleaning Functions

These functions must be applied to every chunk's `texto` field before storage.

```python
import re
import unicodedata

def clean_text(text: str) -> str:
    """
    Apply all cleaning steps to extracted text.
    """
    text = strip_page_artifacts(text)
    text = normalize_whitespace(text)
    text = normalize_quotes(text)
    text = normalize_dashes(text)
    return text.strip()


def strip_page_artifacts(text: str) -> str:
    """
    Remove page numbers, running headers, and footer artifacts.
    """
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip pure page number lines
        if re.match(r'^\d+$', stripped):
            continue
        # Skip known header patterns
        if re.match(
            r'^(O LIVRO DOS ESP[ÍI]RITOS|O LIVRO DOS M[ÉE]DIUNS|'
            r'O EVANGELHO SEGUNDO O ESPIRITISMO|O C[ÉE]U E O INFERNO|'
            r'A G[EÊ]NESE|ALLAN KARDEC)\s*$',
            stripped, re.IGNORECASE
        ):
            continue
        cleaned.append(line)
    return '\n'.join(cleaned)


def normalize_whitespace(text: str) -> str:
    """
    Collapse multiple blank lines to one, strip trailing spaces per line.
    """
    text = re.sub(r'[ \t]+', ' ', text)           # collapse inline spaces
    text = re.sub(r'\n{3,}', '\n\n', text)         # max one blank line
    return text


def normalize_quotes(text: str) -> str:
    """
    Normalize typographic quotes to standard ASCII.
    Portuguese PDFs often use « » or " " or '' variants.
    Preserve the spirit-answer convention of double quotes.
    """
    text = text.replace('\u201c', '"').replace('\u201d', '"')  # curly double
    text = text.replace('\u2018', "'").replace('\u2019', "'")  # curly single
    text = text.replace('\u00ab', '"').replace('\u00bb', '"')  # guillemets
    return text


def normalize_dashes(text: str) -> str:
    """
    Normalize em-dash variants to a standard em-dash (—).
    """
    text = text.replace('\u2013', '—')  # en-dash → em-dash
    text = text.replace(' - ', ' — ')   # spaced hyphen → em-dash
    return text
```

---

## 5. PDF Text Extraction

### 5.1 Recommended Library

Use **`pdfminer.six`** (Python) for text extraction. It handles Portuguese characters and multi-column layouts better than `PyPDF2` for these specific Guillon editions.

```python
from pdfminer.high_level import extract_text

def pdf_to_text(pdf_path: str) -> str:
    """
    Extract raw text from PDF preserving paragraph structure.
    Use layout analysis (laparams) to group lines into paragraphs.
    """
    from pdfminer.layout import LAParams
    laparams = LAParams(
        line_margin=0.3,    # lines within 30% of line height are grouped
        word_margin=0.1,    # words within 10% of char width are joined
        char_margin=1.5,    # chars within 1.5x char width joined
        boxes_flow=0.5,     # balanced horizontal/vertical flow
        detect_vertical=False
    )
    return extract_text(pdf_path, laparams=laparams)
```

### 5.2 Alternative: pypdf + Layout Heuristics

If `pdfminer` produces mis-ordered lines (rare in single-column PDFs), fall back to:

```python
from pypdf import PdfReader

def pdf_to_text_pypdf(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text(extraction_mode="layout"))
    return '\n\n'.join(pages)
```

### 5.3 Validation After Extraction

```python
def validate_extraction(chunks: list[dict], book_id: str) -> None:
    """
    Basic sanity checks after extraction.
    Raises AssertionError with descriptive message on failure.
    """
    assert len(chunks) > 0, f"{book_id}: No chunks extracted"
    assert all('id' in c for c in chunks), f"{book_id}: Missing 'id' field"
    assert all('texto' in c and len(c['texto']) > 10 for c in chunks), \
        f"{book_id}: Empty or near-empty texto field"
    assert len(set(c['id'] for c in chunks)) == len(chunks), \
        f"{book_id}: Duplicate chunk IDs detected"

    # Book-specific checks
    if book_id == 'lde':
        q_numbers = sorted(c['questao'] for c in chunks if c['questao'])
        assert q_numbers[-1] == 1019, \
            f"LdE: last question should be 1019, got {q_numbers[-1]}"
        assert q_numbers[0] == 1, \
            f"LdE: first question should be 1, got {q_numbers[0]}"
```

---

## 6. Output Format

### 6.1 File Layout

Chunks are written as a JSONL file (one JSON object per line) for streaming-compatible loading:

```
backend/data/kardec/chunks/
├── lde_chunks.jsonl          # O Livro dos Espíritos (1,019 chunks)
├── ldm_chunks.jsonl          # O Livro dos Médiuns (~334 chunks)
├── ese_chunks.jsonl          # O Evangelho Segundo o Espiritismo
├── cei_chunks.jsonl          # O Céu e o Inferno
└── gen_chunks.jsonl          # A Gênese
```

### 6.2 JSONL Format

```
{"id": "lde-q0001", "autor": "Allan Kardec", "medium": null, "obra": "O Livro dos Espíritos", "parte": "Parte Primeira — Das Causas Primárias", "capitulo": "I — Deus", "questao": 1, "texto": "O que é Deus?\n\"Deus é a inteligência suprema, causa primária de todas as coisas.\"", "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)"}
{"id": "lde-q0002", ...}
```

### 6.3 Summary Statistics File

After extraction, write a `_stats.json` alongside each JSONL:

```json
{
  "book": "O Livro dos Espíritos",
  "book_id": "lde",
  "total_chunks": 1019,
  "total_chars": 1234567,
  "avg_chars_per_chunk": 1213,
  "min_chars": 42,
  "max_chars": 3847,
  "partes": ["Parte Primeira — Das Causas Primárias", "..."],
  "extraction_date": "2026-04-11T00:00:00Z"
}
```

---

## 7. CLI Interface for Codex

The `parser.py` module must expose a CLI compatible with:

```bash
python -m app.corpus.parser \
  --source backend/data/kardec/raw/ \
  --output backend/data/kardec/chunks/ \
  --book lde          # or ldm, ese, cei, gen, or 'all'
  --validate          # run post-extraction assertions
```

The module should log progress at INFO level:
```
[parser] Extracting O Livro dos Espíritos...
[parser] Page 1/482: 0 chunks
[parser] ...
[parser] Extraction complete: 1019 chunks, 0 validation errors
[parser] Written to backend/data/kardec/chunks/lde_chunks.jsonl
```

---

## 8. Edge Cases and Pitfalls

| Pitfall | Detail | Mitigation |
|---|---|---|
| **Hyphenated words across lines** | PDFs often break long Portuguese words with a hyphen at line end (e.g., `espiritua-\nlismo`) | Detect trailing hyphen + lowercase next line start → join with no space |
| **Question numbering gaps** | Some editions skip numbers or have editorial notes between questions | Track last seen number; if gap > 1, log a warning but continue |
| **Sub-questions (77a, 77b)** | Must remain part of parent chunk (77) | Only recognize integer patterns for new chunk start; append sub-questions |
| **Footnotes** | Guillon editions have translator footnotes at page bottom | Strip lines beginning with `*` or `†` that appear at very end of page text |
| **Spirit answer delimiters** | Spirit answers are enclosed in quotes: `"..."` — but nested quotes exist | Preserve raw quote structure; do not attempt to parse dialogue |
| **Chapter headings as false question starts** | Some chapter headings contain numerals that might match QUESTION_START | Require sequential numbering — a jump from chapter context to q.500 is flagged |
| **Unicode normalization** | PDF extraction may produce NFC or NFD forms of Portuguese characters | Apply `unicodedata.normalize('NFC', text)` after extraction |
| **Blank pages and front matter** | Title pages, copyright pages, indexes — these should not produce chunks | Filter pages with < 100 meaningful characters |

---

## 9. Chunking Summary Table

| Book | ID prefix | Unit | Overlap | Expected chunks | Notes |
|---|---|---|---|---|---|
| O Livro dos Espíritos | `lde-q{N}` | Question | None (self-contained) | 1,019 | Sub-questions stay with parent |
| O Livro dos Médiuns | `ldm-a{N}` | Article | None | ~334 | Mixed Q&A + narrative |
| O Evangelho Segundo o Espiritismo | `ese-c{N}-p{N}` | Paragraph | 2-paragraph window | ~600–900 | 28 chapters |
| O Céu e o Inferno | `cei-p{N}-p{N}` | Paragraph | 2-paragraph window | ~400–600 | 2 parts; Part 2 has spirit accounts |
| A Gênese | `gen-c{N}-p{N}` | Paragraph | 2-paragraph window | ~500–800 | 19 chapters; scientific tone |

---

## 10. References

| Resource | Link |
|---|---|
| Architecture document | [architecture.md](./architecture.md) |
| Requirements spec | [requirements.md](../requirements/requirements.md) |
| Corpus Notes | [LUMEN_CONTEXT.md § 8](../../LUMEN_CONTEXT.md) |
| pdfminer.six docs | https://pdfminersix.readthedocs.io |
| AGENTS.md corpus schema | [AGENTS.md § 12](../../AGENTS.md) |
