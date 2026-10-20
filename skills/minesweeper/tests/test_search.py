import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import search  # noqa: E402


class BM25Test(unittest.TestCase):
    def test_ranks_matching_doc_first(self):
        docs = [search.tokens(t) for t in [
            "exactly once delivery is impossible over lossy links; use idempotency keys",
            "colour space conversion in sixteen bit float",
            "licence terms forbid training a competing model",
        ]]
        idx = search.BM25(docs)
        top = idx.top(search.tokens("exactly once retries idempotency"), 3)
        self.assertEqual(top[0][0], 0)

    def test_no_match_returns_empty(self):
        idx = search.BM25([search.tokens("alpha beta")])
        self.assertEqual(idx.top(search.tokens("gamma"), 3), [])

    def test_passages_split_long_text(self):
        text = "\n\n".join("para %d " % i + "word " * 100 for i in range(10))
        chunks = search.passages(text, size=900)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 1800 for c in chunks))


if __name__ == "__main__":
    unittest.main()
