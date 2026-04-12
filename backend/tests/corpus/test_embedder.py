from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.corpus.embedder import _SAFE_MAX_TOKENS, Embedder


class EmbedderTests(unittest.TestCase):
    def test_prepare_text_stays_within_safe_token_budget(self) -> None:
        embedder = Embedder(cache_dir=None)
        text = "espiritismo " * 12000

        prepared = embedder._prepare_text(text)

        self.assertLessEqual(embedder._token_count(prepared), _SAFE_MAX_TOKENS)
        self.assertLess(len(prepared), len(text))


if __name__ == "__main__":
    unittest.main()
