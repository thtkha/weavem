import unittest
from implementation import run


class NormalizeTests(unittest.TestCase):
    def test_normalizes_text(self):
        self.assertEqual(run("  Hello Weavem  "), "hello weavem")

    def test_can_keep_case(self):
        self.assertEqual(run("  Hello  ", lowercase=False), "Hello")
