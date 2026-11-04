import os, subprocess, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))


class NetworkDemo(unittest.TestCase):
    def test_three_nodes(self):
        """Runs examples/three_nodes.py (about a minute)."""
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "examples", "three_nodes.py")],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])

    def test_private_sites(self):
        """Runs examples/private_site.py (trusted-peers allowlist)."""
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "examples", "private_site.py")],
                           capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])

    def test_relay_discovery_after_a_minute(self):
        """Runs examples/relay_discovery.py (about 2.5 minutes): late readers still discover via a relay."""
        r = subprocess.run([sys.executable, os.path.join(HERE, "..", "examples", "relay_discovery.py")],
                           capture_output=True, text=True, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])


if __name__ == "__main__":
    unittest.main()
