"""Vérifie que les schémas SQLite du flux de propositions sont exécutables."""

import ast
import sqlite3
import unittest
from pathlib import Path


DATABASE = Path(__file__).resolve().parents[1] / "database.py"


def _schema_constants() -> dict[str, str]:
    tree = ast.parse(DATABASE.read_text(encoding="utf-8"))
    values: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id.startswith("CREATE_GIVEAWAY_"):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    values[target.id] = node.value.value
    return values


class GiveawayProposalSchemaTests(unittest.TestCase):
    def test_points_and_proposal_tables_can_be_created(self):
        schemas = _schema_constants()
        required = {
            "CREATE_GIVEAWAY_PRIZE_ITEMS_TABLE",
            "CREATE_GIVEAWAY_POINT_SETTINGS_TABLE",
            "CREATE_GIVEAWAY_MEMBER_POINTS_TABLE",
            "CREATE_GIVEAWAY_POINT_ROLES_TABLE",
            "CREATE_GIVEAWAY_POINT_AWARDS_TABLE",
            "CREATE_GIVEAWAY_PROPOSALS_TABLE",
        }
        self.assertTrue(required.issubset(schemas))
        connection = sqlite3.connect(":memory:")
        for name in required:
            connection.execute(schemas[name])
        connection.execute(
            "INSERT INTO giveaway_proposals "
            "(guild_id, ticket_channel_id, proposer_id, prize_name, prize_points, created_at) "
            "VALUES (1, 2, 3, 'Test', 10, '2026-10-28T00:00:00+00:00')"
        )
        row = connection.execute(
            "SELECT status, prize_points FROM giveaway_proposals"
        ).fetchone()
        self.assertEqual(("pending", 10), row)


if __name__ == "__main__":
    unittest.main()
