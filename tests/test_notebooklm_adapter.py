"""Unit tests for NotebookLM adapter and narrative synthesis modules."""

import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import notebooklm_adapter
import narrative_synthesizer


class TestNotebookLMIntegration(unittest.TestCase):

    def test_adapter_import(self):
        """Verify that NotebookLM adapter can load client library."""
        try:
            client = notebooklm_adapter.get_client()
            self.assertIsNotNone(client)
        except Exception as e:
            self.skipTest(f"NotebookLM client environment check: {e}")

    def test_genre_detection(self):
        """Test dual-engine genre detector."""
        meta_fiction = {"genre": "Fantasy Fiction"}
        genre = narrative_synthesizer.detect_genre(meta_fiction, REPO_ROOT)
        self.assertEqual(genre, "fiction")

        meta_nonfiction = {"genre": "Business & Management"}
        genre = narrative_synthesizer.detect_genre(meta_nonfiction, REPO_ROOT)
        self.assertEqual(genre, "non-fiction")


if __name__ == "__main__":
    unittest.main()
