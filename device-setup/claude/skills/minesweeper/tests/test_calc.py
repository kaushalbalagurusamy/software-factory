import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from checks import calc  # noqa: E402


class CalcTest(unittest.TestCase):
    def test_memory_five_48mp_rgba_fp32(self):
        # 5 frames x 48 MP x 4 channels x 4 bytes = 3.84 GB
        r = calc.memory(frames=5, width=8000, height=6000, channels=4, bytes_per_channel=4)
        self.assertAlmostEqual(r["gb"], 3.84, places=6)

    def test_bandwidth_4k60_fp16_rgba(self):
        r = calc.bandwidth(width=3840, height=2160, channels=4, bytes_per_channel=2, fps=60)
        self.assertAlmostEqual(r["gb_per_s"], 3.981312, places=6)

    def test_fanout_tail_p99_50(self):
        self.assertAlmostEqual(calc.fanout_tail(0.99, 50)["percent"], 39.4994, places=3)

    def test_fanout_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            calc.fanout_tail(1.2, 3)

    def test_bft_quorum(self):
        self.assertEqual(calc.bft_quorum(1), {"min_replicas": 4, "quorum": 3, "tolerates": 1})
        self.assertEqual(calc.bft_tolerates(3)["max_faulty"], 0)
        self.assertEqual(calc.bft_tolerates(7)["max_faulty"], 2)

    def test_cft_quorum(self):
        self.assertEqual(calc.cft_quorum(2), {"min_replicas": 5, "quorum": 3, "tolerates": 2})

    def test_egress_cost_needs_explicit_price(self):
        self.assertAlmostEqual(calc.egress_cost(1000, 0.05)["cost"], 50.0)
        with self.assertRaises(TypeError):
            calc.egress_cost(1000)  # no recalled default price

    def test_payload_mtu(self):
        self.assertEqual(calc.payload_mtu(1472)["packets"], 1)
        r = calc.payload_mtu(1473)
        self.assertEqual(r["packets"], 2)
        self.assertTrue(r["fragmented"])

    def test_birthday_collision_96bit_nonce(self):
        # 2^32 random 96-bit nonces: about 2^-33 collision probability
        p = calc.birthday_collision(96, 2 ** 32)["p_collision"]
        self.assertAlmostEqual(p, 2 ** -33, delta=2 ** -40)


if __name__ == "__main__":
    unittest.main()
