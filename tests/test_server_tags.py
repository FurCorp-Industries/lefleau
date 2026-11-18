import unittest
from types import SimpleNamespace

from utils.server_tags import (
    get_primary_guild_identity,
    normalize_server_tag,
    user_matches_server_tag,
)


def make_user(tag=None, guild_id=None, enabled=True):
    primary = SimpleNamespace(tag=tag, id=guild_id, identity_enabled=enabled)
    return SimpleNamespace(primary_guild=primary)


class ServerTagTests(unittest.TestCase):
    def test_normalizes_case_and_spaces(self):
        self.assertEqual(normalize_server_tag("  FLÉO "), "fléo")

    def test_reads_visible_primary_guild(self):
        self.assertEqual(get_primary_guild_identity(make_user("FLEO", 123)), ("fleo", 123))

    def test_ignores_hidden_tag(self):
        self.assertEqual(get_primary_guild_identity(make_user("FLEO", 123, False)), (None, None))

    def test_matches_tag_and_optional_source_guild(self):
        user = make_user("FLEO", 123)
        self.assertTrue(user_matches_server_tag(user, "fleo"))
        self.assertTrue(user_matches_server_tag(user, "fleo", 123))
        self.assertFalse(user_matches_server_tag(user, "fleo", 456))
        self.assertFalse(user_matches_server_tag(user, "other", 123))


if __name__ == "__main__":
    unittest.main()
