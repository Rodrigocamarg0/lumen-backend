"""
Chunking logic for all 5 Kardec books.

Each extractor converts a raw text string (from pdfminer) into a list of
canonical Chunk dicts conforming to the schema in parsing_strategy.md.

Chunking units:
  - LdE:  one chunk per numbered question (1–1019)
  - LdM:  one chunk per numbered article (1–334)
  - ESE:  paragraph-level with 2-paragraph sliding overlap, per chapter
  - CeI:  paragraph-level with 2-paragraph sliding overlap, per part/chapter
  - Gen:  paragraph-level with 2-paragraph sliding overlap, per chapter
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("chunker")

# ---------------------------------------------------------------------------
# Shared regex patterns
# ---------------------------------------------------------------------------

_PAGE_NUM = re.compile(r"^\d+$")
_HEADER = re.compile(
    r"^(O LIVRO DOS ESP[ÍI]RITOS|O LIVRO DOS M[ÉE]DIUNS|"
    r"O EVANGELHO SEGUNDO O ESPIRITISMO|O C[ÉE]U E O INFERNO|"
    r"A G[EÊ]NESE|ALLAN KARDEC)\s*$",
    re.IGNORECASE,
)
_FOOTNOTE = re.compile(r"^[\*†]")

# LdE — actual PDF format:
#   Questions are lone-number lines:  "1. "  (number + period + trailing space)
#   Part/chapter tracked via running page headers: "Parte Primeira – Capítulo I"
#   Chapter titles come from all-caps standalone headings: "CAPÍTULO I"
_LDE_LONE_Q = re.compile(r"^\s*(\d{1,4})\.\s*$")
_LDE_RUNNING_HDR = re.compile(
    r"^Parte\s+(Primeira|Segunda|Terceira|Quarta)\s*[–—-]\s*Cap[ií]tulo\s+([IVXLCM]+)\s*$",
    re.IGNORECASE,
)
_LDE_CAPS_CHAPTER = re.compile(r"^CAP[ÍI]TULO\s+([IVXLCM]+)\s*$")
_LDE_STANDALONE_PARTE = re.compile(
    r"^Parte\s+(Primeira|Segunda|Terceira|Quarta)\s*$", re.IGNORECASE
)
_LDE_DECORATOR = re.compile(r"^M\s*$")  # drop-cap marker pdfminer emits before chapter titles

_LDE_PARTE_NAMES: dict[str, str] = {
    "PRIMEIRA": "Parte Primeira — Das Causas Primárias",
    "SEGUNDA": "Parte Segunda — Do Mundo Espírita",
    "TERCEIRA": "Parte Terceira — Das Leis Morais",
    "QUARTA": "Parte Quarta — Das Esperanças e Consolações",
}

# LdM
_LDM_PART = re.compile(r"^PARTE\s+(PRIMEIRA|SEGUNDA)\b", re.IGNORECASE)
_LDM_CHAPTER = re.compile(
    r"^CAP[ÍI]TULO\s+((?:X{0,3})(IX|IV|V?I{0,3}))\s*[—–-]?\s*(.*)",
    re.IGNORECASE,
)
_LDM_ARTICLE = re.compile(r"^(\d{1,3})\.\s+([A-ZÁÉÍÓÚÂÊÎÔÛÃÕÀÈÌÒÙ].{3,})")

# ESE / CeI / Gen chapter headings
_CHAPTER_HEADING = re.compile(
    r"^CAP[ÍI]TULO\s+((?:X{0,3})(IX|IV|V?I{0,3}|X{1,3}I{0,3}))\s*[—–-]?\s*(.*)",
    re.IGNORECASE,
)
_PART_HEADING = re.compile(r"^PARTE\s+(PRIMEIRA|SEGUNDA)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    lines = text.split("\n")
    cleaned: list[str] = []
    for line in lines:
        s = line.strip()
        if _PAGE_NUM.match(s):
            continue
        if _HEADER.match(s):
            continue
        if _FOOTNOTE.match(s):
            continue
        cleaned.append(line)
    text = "\n".join(cleaned)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Rejoin hyphenated words split across lines
    text = re.sub(r"(\w)-\n\s*([a-záéíóúâêîôûãõàèìòù])", r"\1\2", text)
    # Normalize quotes
    for old, new in [
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u00ab", '"'),
        ("\u00bb", '"'),
    ]:
        text = text.replace(old, new)
    # Normalize dashes
    text = text.replace("\u2013", "—").replace(" - ", " — ")
    return text.strip()


def _extract_paragraphs(text: str, min_chars: int = 30) -> list[str]:
    raw = re.split(r"\n\s*\n", text)
    result = []
    for p in raw:
        s = p.strip()
        if len(s) < min_chars:
            continue
        if _PAGE_NUM.match(s):
            continue
        if _HEADER.match(s):
            continue
        result.append(s)
    return result


def _find_content_start(text: str, pattern: str, skip_toc: bool = True) -> int:
    """
    Find the byte-index of the actual content start (skip TOC occurrences).

    Strategy: collect all occurrences of `pattern`. If there are ≥2, the
    first is assumed to be the TOC entry; return the second. Otherwise
    return the first (or 0 if none found).
    """
    matches = list(re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE))
    if not matches:
        return 0
    if skip_toc and len(matches) >= 2:
        return matches[1].start()
    return matches[0].start()


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_PARTE_MAP = {
    "PRIMEIRO": "Parte Primeira — Das Causas Primárias",
    "SEGUNDO": "Parte Segunda — Do Mundo Espírita",
    "TERCEIRO": "Parte Terceira — Das Leis Morais",
    "QUARTO": "Parte Quarta — Das Esperanças e Consolações",
}

_LDM_PARTE_MAP = {
    "PRIMEIRA": "Parte Primeira — Noções Preliminares",
    "SEGUNDA": "Parte Segunda — Das Manifestações Físicas e Inteligentes",
}


def _roman_to_num(roman: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    roman = roman.upper()
    total = 0
    prev = 0
    for ch in reversed(roman):
        v = vals.get(ch, 0)
        total += v if v >= prev else -v
        prev = v
    return total


# ---------------------------------------------------------------------------
# O Livro dos Espíritos (LdE)
# ---------------------------------------------------------------------------


def extract_lde_chunks(text: str) -> list[dict]:
    """
    Extract one chunk per numbered question (1–1019).

    PDF format (FEB/Guillon Ribeiro edition):
      - Questions are lone-number lines: "N. " (number + period + space, nothing else)
      - Part/chapter tracked via running page headers: "Parte X – Capítulo Y"
      - Chapter titles come from all-caps headings: "CAPÍTULO N" followed by title
      - The "M" line is a drop-cap marker emitted by pdfminer — skip it
    """
    # pdfminer embeds form-feed \x0c (page boundary) inside lines when the
    # running header is the last text on a page.  Normalise to \n so every
    # logical line is truly on its own line before we do anything else.
    text = text.replace("\x0c", "\n")
    lines = text.split("\n")

    def _look_ahead_chapter_title(lines: list[str], pos: int) -> str:
        """
        Starting right after a CAPÍTULO N heading, skip blank lines and an
        optional drop-cap 'M', then collect the chapter title (stops at blank
        or bullet '•' line).
        """
        j = pos + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and _LDE_DECORATOR.match(lines[j].strip()):
            j += 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        parts: list[str] = []
        while j < len(lines):
            ts = lines[j].strip()
            if not ts or ts.startswith("•") or _LDE_LONE_Q.match(ts):
                break
            # Stop if we hit another heading
            if _LDE_CAPS_CHAPTER.match(ts) or _LDE_RUNNING_HDR.match(ts):
                break
            parts.append(ts)
            j += 1
        return " ".join(parts)

    # ── Find content start: back up far enough to capture parte/chapter ───────
    content_start = 0
    for idx, line in enumerate(lines):
        m = _LDE_LONE_Q.match(line)
        if m and int(m.group(1)) == 1:
            # Back up 200 lines to guarantee we pick up the parte + CAPÍTULO I header
            content_start = max(0, idx - 200)
            break

    lines = lines[content_start:]

    # ── Pass 2: chunk by lone question numbers ───────────────────────────────
    chunks: list[dict] = []
    current_parte: str | None = None
    current_capitulo: str | None = None
    q_num: int | None = None
    q_buf: list[str] = []
    # Questions that had no body text of their own (shared-answer groups)
    pending_q_nums: list[int] = []

    def flush() -> None:
        """Flush current buffer. If buf is empty, defer until next non-empty flush."""
        nonlocal pending_q_nums
        if q_num is None:
            return
        if not q_buf:
            # No body yet — keep q_num in pending list for the next flush
            pending_q_nums.append(q_num)
            return
        # Emit one chunk per accumulated question number (all share the same text)
        all_nums = [*pending_q_nums, q_num]
        pending_q_nums = []
        text_blob = "\n".join(q_buf)
        for n in all_nums:
            chunks.append(_build_lde(n, [text_blob], current_parte, current_capitulo))

    for line_idx, line in enumerate(lines):
        s = line.strip()

        # ── Skip noise lines ────────────────────────────────────────────────
        if not s:
            if q_num is not None:
                q_buf.append("")
            continue
        if _PAGE_NUM.match(s):
            continue
        if _HEADER.match(s):
            continue
        if _LDE_DECORATOR.match(s):
            continue

        # ── Running page header: update parte + chapter numeral ─────────────
        # (titles are NOT resolved here to avoid cross-part collisions —
        #  the standalone CAPÍTULO heading sets the definitive title instead)
        rh = _LDE_RUNNING_HDR.match(s)
        if rh:
            parte_key = rh.group(1).upper()
            cap_numeral = rh.group(2).upper()
            new_parte = _LDE_PARTE_NAMES.get(parte_key, f"Parte {rh.group(1)}")
            # Only update capitulo numeral if parte also changed (new chapter section)
            # This avoids overwriting the richer title set by the standalone heading
            if current_parte != new_parte:
                current_parte = new_parte
                current_capitulo = f"Capítulo {cap_numeral}"
            elif current_capitulo is None:
                current_capitulo = f"Capítulo {cap_numeral}"
            continue

        # ── Standalone parte boundary ─────────────────────────────────────────
        sp = _LDE_STANDALONE_PARTE.match(s)
        if sp:
            parte_key = sp.group(1).upper()
            current_parte = _LDE_PARTE_NAMES.get(parte_key, f"Parte {sp.group(1)}")
            continue

        # ── All-caps chapter heading → resolve title inline ───────────────────
        cc = _LDE_CAPS_CHAPTER.match(s)
        if cc:
            numeral = cc.group(1).upper()
            title = _look_ahead_chapter_title(lines, line_idx)
            current_capitulo = f"Capítulo {numeral}" + (f" — {title}" if title else "")
            continue

        # ── Lone question number → start new chunk ────────────────────────────
        qm = _LDE_LONE_Q.match(s)
        if qm:
            candidate = int(qm.group(1))
            # Guard: never go backwards; allow gaps (merged/shared answers)
            if q_num is None or candidate > q_num:
                flush()
                q_num = candidate
                q_buf = []
            # If backwards (false positive in prose), absorb as body text
            elif q_num is not None:
                q_buf.append(line)
            continue

        # ── Body text ─────────────────────────────────────────────────────────
        if q_num is not None:
            q_buf.append(line)

    flush()
    logger.info(f"LdE: {len(chunks)} chunks extracted")
    return chunks


def _build_lde(q_num: int, lines: list[str], parte: str | None, capitulo: str | None) -> dict:
    return {
        "id": f"lde-q{q_num:04d}",
        "autor": "Allan Kardec",
        "medium": None,
        "obra": "O Livro dos Espíritos",
        "parte": parte,
        "capitulo": capitulo,
        "questao": q_num,
        "texto": clean_text("\n".join(lines)),
        "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)",
    }


# ---------------------------------------------------------------------------
# O Livro dos Médiuns (LdM)
# ---------------------------------------------------------------------------


def extract_ldm_chunks(text: str) -> list[dict]:
    """
    Extract one chunk per numbered article (1–334).
    """
    start = _find_content_start(text, r"PARTE\s+PRIMEIRA")
    text = text[start:]

    lines = text.split("\n")
    chunks: list[dict] = []
    current_parte: str | None = None
    current_capitulo: str | None = None
    art_num: int | None = None
    art_buf: list[str] = []

    def flush():
        if art_buf and art_num is not None:
            chunks.append(_build_ldm(art_num, art_buf, current_parte, current_capitulo))

    for line in lines:
        s = line.strip()

        if not s or _PAGE_NUM.match(s) or _HEADER.match(s):
            if art_num is not None:
                art_buf.append(line)
            continue

        pm = _LDM_PART.match(s)
        if pm:
            flush()
            art_buf = []
            art_num = None
            ordinal = pm.group(1).upper()
            current_parte = _LDM_PARTE_MAP.get(ordinal, s)
            continue

        cm = _LDM_CHAPTER.match(s)
        if cm:
            flush()
            art_buf = []
            art_num = None
            numeral = cm.group(1)
            title = cm.group(3).strip()
            current_capitulo = f"{numeral} — {title}" if title else numeral
            continue

        am = _LDM_ARTICLE.match(s)
        if am:
            candidate = int(am.group(1))
            if art_num is None and candidate <= 10:
                flush()
                art_num = candidate
                art_buf = [line]
                continue
            if art_num is not None and candidate > art_num and candidate <= art_num + 10:
                flush()
                art_num = candidate
                art_buf = [line]
                continue

        if art_num is not None:
            art_buf.append(line)

    flush()
    logger.info(f"LdM: {len(chunks)} chunks extracted")
    return chunks


def _build_ldm(art_num: int, lines: list[str], parte: str | None, capitulo: str | None) -> dict:
    return {
        "id": f"ldm-a{art_num:03d}",
        "autor": "Allan Kardec",
        "medium": None,
        "obra": "O Livro dos Médiuns",
        "parte": parte,
        "capitulo": capitulo,
        "questao": None,
        "texto": clean_text("\n".join(lines)),
        "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)",
    }


# ---------------------------------------------------------------------------
# O Evangelho Segundo o Espiritismo (ESE)
# ---------------------------------------------------------------------------


def extract_ese_chunks(text: str) -> list[dict]:
    """
    Chapter-aware paragraph chunks with 2-paragraph sliding window.
    """
    start = _find_content_start(text, r"CAP[ÍI]TULO\s+I\b")
    text = text[start:]
    return _paragraph_chunks(
        text=text,
        id_prefix="ese",
        obra="O Evangelho Segundo o Espiritismo",
        header_pattern=r"^O EVANGELHO",
    )


# ---------------------------------------------------------------------------
# O Céu e o Inferno (CeI)
# ---------------------------------------------------------------------------


def extract_cei_chunks(text: str) -> list[dict]:
    """
    Two-part structure; paragraph chunks with 2-paragraph sliding window.
    """
    start = _find_content_start(text, r"PARTE\s+PRIMEIRA")
    text = text[start:]
    return _paragraph_chunks(
        text=text,
        id_prefix="cei",
        obra="O Céu e o Inferno",
        header_pattern=r"^O C[ÉE]U E O INFERNO",
        use_parts=True,
    )


# ---------------------------------------------------------------------------
# A Gênese (Gen)
# ---------------------------------------------------------------------------


def extract_gen_chunks(text: str) -> list[dict]:
    """
    19 chapters; paragraph chunks with 2-paragraph sliding window.
    """
    start = _find_content_start(text, r"CAP[ÍI]TULO\s+I\b")
    text = text[start:]
    return _paragraph_chunks(
        text=text,
        id_prefix="gen",
        obra="A Gênese",
        header_pattern=r"^A G[EÊ]NESE",
    )


# ---------------------------------------------------------------------------
# Generic paragraph chunker (ESE / CeI / Gen)
# ---------------------------------------------------------------------------


def _paragraph_chunks(
    text: str,
    id_prefix: str,
    obra: str,
    header_pattern: str | None = None,
    use_parts: bool = False,
) -> list[dict]:
    """
    Split text into chapters (by CAPÍTULO heading or PARTE heading when
    use_parts=True), then build overlapping 3-paragraph windows within each
    chapter/part.
    """
    chunks: list[dict] = []
    sections = _split_into_sections(text, use_parts=use_parts, header_pattern=header_pattern)

    for (parte, capitulo, chap_id), section_text in sections:
        paragraphs = _extract_paragraphs(section_text)
        if not paragraphs:
            continue
        for i, _ in enumerate(paragraphs):
            window = paragraphs[i : i + 3]
            chunk_text = "\n\n".join(window)
            p_seq = i + 1
            chunks.append(
                {
                    "id": f"{id_prefix}-{chap_id}-p{p_seq:03d}",
                    "autor": "Allan Kardec",
                    "medium": None,
                    "obra": obra,
                    "parte": parte,
                    "capitulo": capitulo,
                    "questao": None,
                    "texto": clean_text(chunk_text),
                    "edicao_referencia": "FEB, 2013 (Tradução Guillon Ribeiro)",
                }
            )

    logger.info(f"{id_prefix.upper()}: {len(chunks)} chunks extracted")
    return chunks


def _split_into_sections(
    text: str,
    use_parts: bool,
    header_pattern: str | None,
) -> list[tuple[tuple[str | None, str | None, str], str]]:
    """
    Returns list of ((parte, capitulo, id_slug), section_text).
    """
    lines = text.split("\n")
    sections: list[tuple[tuple[str | None, str | None, str], str]] = []
    current_parte: str | None = None
    current_capitulo: str | None = None
    current_chap_id: str = "c00"
    buf: list[str] = []
    chap_counter = 0
    part_counter = 0

    def flush():
        if buf:
            sections.append(((current_parte, current_capitulo, current_chap_id), "\n".join(buf)))
            buf.clear()

    for line in lines:
        s = line.strip()

        if not s:
            buf.append(line)
            continue
        if _PAGE_NUM.match(s) or _HEADER.match(s):
            continue
        if header_pattern and re.match(header_pattern, s, re.IGNORECASE):
            continue

        if use_parts:
            pm = _PART_HEADING.match(s)
            if pm:
                flush()
                part_counter += 1
                ordinal = pm.group(1).upper()
                current_parte = f"Parte {'Primeira' if ordinal == 'PRIMEIRA' else 'Segunda'}"
                current_chap_id = f"p{part_counter}"
                continue

        cm = _CHAPTER_HEADING.match(s)
        if cm:
            flush()
            chap_counter += 1
            numeral = cm.group(1)
            title = cm.group(3).strip() if (cm.lastindex or 0) >= 3 else ""
            current_capitulo = f"Capítulo {numeral}" + (f" — {title}" if title else "")
            if use_parts:
                # Keep part prefix in id, add chapter sub-id
                current_chap_id = f"p{part_counter}-c{chap_counter:02d}"
            else:
                current_chap_id = f"c{chap_counter:02d}"
            continue

        buf.append(line)

    flush()
    return sections


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_chunks(chunks: list[dict], book_id: str) -> list[str]:
    """
    Returns a list of error strings (empty = all OK).
    """
    errors: list[str] = []
    if not chunks:
        errors.append(f"{book_id}: no chunks extracted")
        return errors
    ids = [c.get("id") for c in chunks]
    if len(set(ids)) != len(ids):
        errors.append(f"{book_id}: duplicate chunk IDs detected")
    for c in chunks:
        if not c.get("texto") or len(c["texto"]) < 10:
            errors.append(f"{book_id}: empty texto in chunk {c.get('id')}")
    if book_id == "lde":
        q_nums = sorted(c["questao"] for c in chunks if c.get("questao"))
        if q_nums:
            if q_nums[0] != 1:
                errors.append(f"LdE: first question is {q_nums[0]}, expected 1")
            if q_nums[-1] != 1019:
                errors.append(f"LdE: last question is {q_nums[-1]}, expected 1019")
    return errors
