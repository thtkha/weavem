import unittest
from implementation import double


class DoubleTests(unittest.TestCase):
    def test_double(self):
        self.assertEqual(double(21), 42)
