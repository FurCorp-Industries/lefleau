import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import config
import database as db


class CustomShopDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        config.DATABASE_PATH = str(Path(self.temp_dir.name) / "economy.db")
        await db.init_db()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_purchase_is_case_insensitive_and_updates_inventory(self):
        await db.upsert_custom_item(1, "Clé VIP", "Objet test", 250, "🔑", 99)

        result = await db.purchase_custom_item(42, 1, "clé vip", 2)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["wallet"], 0)
        self.assertEqual(result["quantity_owned"], 2)

    async def test_insufficient_funds_does_not_add_an_item(self):
        await db.upsert_custom_item(1, "Navire", "Objet cher", 600, "⛵", 99)

        result = await db.purchase_custom_item(42, 1, "Navire", 1)

        self.assertEqual(result["status"], "insufficient_funds")
        self.assertEqual(await db.get_custom_inventory(42, 1), [])

    async def test_disabled_item_stays_owned_but_cannot_be_bought(self):
        await db.upsert_custom_item(1, "Badge", "Souvenir", 100, "🏅", 99)
        await db.purchase_custom_item(42, 1, "Badge", 1)
        self.assertTrue(await db.disable_custom_item(1, "BADGE"))

        result = await db.purchase_custom_item(42, 1, "Badge", 1)
        inventory = await db.get_custom_inventory(42, 1)

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(inventory[0]["quantity"], 1)
        self.assertFalse(inventory[0]["active"])

    async def test_panel_can_disable_and_reactivate_an_item(self):
        await db.upsert_custom_item(1, "Ticket doré", "Accès spécial", 300, "🎟️", 99)

        self.assertTrue(await db.set_custom_item_active(1, "ticket doré", False))
        self.assertIsNone(await db.get_custom_item(1, "Ticket doré"))
        self.assertTrue(await db.set_custom_item_active(1, "TICKET DORÉ", True))

        item = await db.get_custom_item(1, "Ticket doré")
        self.assertIsNotNone(item)
        self.assertTrue(item["active"])

    async def test_global_stats_include_custom_items(self):
        await db.upsert_custom_item(1, "Boussole", "Objet de navigation", 100, "🧭", 99)
        await db.purchase_custom_item(42, 1, "Boussole", 2)

        stats = await db.get_global_stats()

        self.assertEqual(stats["custom_items"], 1)
        self.assertEqual(stats["active_custom_items"], 1)
        self.assertEqual(stats["custom_items_owned"], 2)


if __name__ == "__main__":
    unittest.main()
