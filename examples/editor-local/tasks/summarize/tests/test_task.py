import unittest
from implementation import run


class SummaryTests(unittest.TestCase):
    def test_formats_counts(self):
        self.assertEqual(
            run({"words": 2, "characters": 12}),
            "Document: 2 words, 12 characters",
        )

    def test_custom_prefix(self):
        self.assertEqual(run({"words": 0, "characters": 0}, prefix="Note"),
                         "Note: 0 words, 0 characters")
