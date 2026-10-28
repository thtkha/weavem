import unittest
from implementation import run


class CountTests(unittest.TestCase):
    def test_counts_text(self):
        self.assertEqual(run("hello weavem"), {"words": 2, "characters": 12})

    def test_empty_text(self):
        self.assertEqual(run(""), {"words": 0, "characters": 0})
