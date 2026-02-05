import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]


def _run_metrics(py_hash_seed: str) -> dict:
    script = r"""
import json
from server.miscite.analysis.deep_analysis.network import compute_network_metrics

nodes = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]
out = compute_network_metrics(
    nodes=set(nodes),
    edges=[],
    key_nodes={"a"},
    original_nodes=set(nodes),
    original_ref_id_by_node={n: n for n in nodes},
    cite_counts_by_ref_id={},
)
print(json.dumps(out, sort_keys=True))
""".strip()

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(py_hash_seed)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout.strip() or "{}")


class TestNetworkDeterminism(unittest.TestCase):
    def test_metrics_stable_across_hash_seed(self) -> None:
        out_a = _run_metrics("1")
        out_b = _run_metrics("2")
        self.assertEqual(out_a, out_b)


if __name__ == "__main__":
    unittest.main()

