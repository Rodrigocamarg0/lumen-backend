from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.corpus.chunker import _build_lde, clean_text


class LdeChunkerTests(unittest.TestCase):
    def test_clean_text_collapses_pdf_line_wraps(self) -> None:
        text = clean_text(
            "Deus é a inteligência suprema, causa primária de todas as \n"
            "coisas.\n\n"
            "Não penseis que eu tenha vindo des-\n\n"
            "truir a lei."
        )

        self.assertIn("todas as coisas.", text)
        self.assertIn("destruir a lei.", text)
        self.assertNotIn("todas as \ncoisas", text)

    def test_clean_text_merges_blank_line_visual_wraps(self) -> None:
        text = clean_text(
            "Dizer\n\n"
            "que Deus é o infinito é tomar o atributo de uma coisa pela coisa mesma,\n\n"
            "é definir uma coisa que não está conhecida por outra.\n\n"
            "Novo parágrafo completo."
        )

        self.assertIn(
            "Dizer que Deus é o infinito é tomar o atributo de uma coisa pela coisa mesma, "
            "é definir uma coisa que não está conhecida por outra.",
            text,
        )
        self.assertIn("outra.\n\nNovo parágrafo", text)

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
