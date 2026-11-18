import unittest
import sys
from types import SimpleNamespace

# Le runtime de test local ne fournit pas nécessairement python-dotenv.
sys.modules.setdefault("dotenv", SimpleNamespace(load_dotenv=lambda: None))

import config
from utils.boss_rewards import calculate_mvp_bonus, calculate_reward_pool


class BossRewardScalingTests(unittest.TestCase):
    def test_reward_pool_uses_hp_tiers(self):
        expected = {
            4_000: 1_600,
            9_000: 3_600,
            15_000: 6_750,
            25_000: 11_250,
            40_000: 20_000,
            70_000: 38_500,
            100_000: 55_000,
            200_000: 120_000,
        }
        for max_hp, reward in expected.items():
            with self.subTest(max_hp=max_hp):
                self.assertEqual(
                    calculate_reward_pool(max_hp, config.BOSS_REWARD_SCALING),
                    reward,
                )

    def test_reward_pool_rejects_non_positive_hp(self):
        self.assertEqual(calculate_reward_pool(0, config.BOSS_REWARD_SCALING), 0)
        self.assertEqual(calculate_reward_pool(-100, config.BOSS_REWARD_SCALING), 0)

    def test_mvp_bonus_has_minimum_scales_and_is_capped(self):
        args = (
            config.BOSS_MVP_BONUS_RATIO,
            config.BOSS_MVP_BONUS_MIN,
            config.BOSS_MVP_BONUS_MAX,
        )
        self.assertEqual(calculate_mvp_bonus(1_600, *args), 500)
        self.assertEqual(calculate_mvp_bonus(20_000, *args), 2_000)
        self.assertEqual(calculate_mvp_bonus(120_000, *args), 10_000)
        self.assertEqual(calculate_mvp_bonus(0, *args), 0)


if __name__ == "__main__":
    unittest.main()
