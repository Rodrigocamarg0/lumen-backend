from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.corpus.chunker import _build_lde


class LdeChunkerTests(unittest.TestCase):
    def test_build_lde_trims_q1019_end_matter(self) -> None:
        lines = [
            "Poderá jamais implantar-se na Terra o reinado do bem?",
            '"Sim."',
            "",
            "26 N.E.: Ver Nota explicativa, p. 477.",
            "",
            "Conclusão",
            "Texto que não deve entrar.",
            "",
            "ÍNDICE GERAL28",
        ]

        chunk = _build_lde(1019, lines, "Parte Quarta", "Capítulo Único")

        self.assertEqual(chunk["id"], "lde-q1019")
        self.assertNotIn("Conclusão", chunk["texto"])
        self.assertNotIn("Nota explicativa", chunk["texto"])
        self.assertNotIn("ÍNDICE GERAL", chunk["texto"])
        self.assertIn("Poderá jamais implantar-se", chunk["texto"])


if __name__ == "__main__":
    unittest.main()
