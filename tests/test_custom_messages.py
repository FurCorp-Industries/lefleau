import unittest

from utils.custom_messages import DEFAULT_MESSAGE_COLOR, is_valid_image_url, parse_embed_color


class CustomMessageTests(unittest.TestCase):
    def test_parses_default_and_hex_colors(self):
        self.assertEqual(parse_embed_color(""), DEFAULT_MESSAGE_COLOR)
        self.assertEqual(parse_embed_color("#5865F2"), 0x5865F2)
        self.assertEqual(parse_embed_color("ffcc00"), 0xFFCC00)

    def test_rejects_invalid_colors(self):
        self.assertIsNone(parse_embed_color("#FFF"))
        self.assertIsNone(parse_embed_color("blue"))

    def test_accepts_only_web_image_urls(self):
        self.assertTrue(is_valid_image_url(""))
        self.assertTrue(is_valid_image_url("https://example.com/rules.png"))
        self.assertTrue(is_valid_image_url("http://example.com/rules.png"))
        self.assertFalse(is_valid_image_url("file:///secret.png"))
