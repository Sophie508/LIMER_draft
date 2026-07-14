import subprocess
import unittest

from limer_v0.faults import TcProfile, apply_profile, build_tc_command


class FaultProfileTest(unittest.TestCase):
    def test_builds_rate_delay_profile(self):
        command = build_tc_command("s0-eth3", TcProfile(20.0, 1.0, 0.0))
        self.assertEqual(
            command,
            [
                "tc",
                "qdisc",
                "replace",
                "dev",
                "s0-eth3",
                "root",
                "handle",
                "1:",
                "netem",
                "limit",
                "1000",
                "delay",
                "1.0ms",
                "rate",
                "20.0mbit",
            ],
        )

    def test_adds_loss_only_when_nonzero(self):
        command = build_tc_command("s0-eth3", TcProfile(100.0, 1.0, 0.5))
        self.assertEqual(command[-2:], ["loss", "0.5%"])

    def test_rejects_invalid_interface(self):
        with self.assertRaisesRegex(ValueError, "interface"):
            build_tc_command("s0; reboot", TcProfile(20.0, 1.0, 0.0))

    def test_apply_profile_uses_injected_namespace_accessors(self):
        commands = []

        def run(command):
            commands.append(command)
            stdout = ""
            if command[:4] == ["tc", "-s", "-j", "qdisc"]:
                stdout = '[{"kind":"netem","root":true,"bytes":99}]'
            return subprocess.CompletedProcess(command, 0, stdout, "")

        counters = {
            "operstate": "up\n",
            "rx_bytes": "100\n",
            "rx_packets": "10\n",
            "rx_dropped": "1\n",
            "tx_bytes": "200\n",
            "tx_packets": "20\n",
            "tx_dropped": "2\n",
        }

        def read_text(path):
            return counters[path.rsplit("/", 1)[-1]]

        record = apply_profile(
            "w2-eth0",
            TcProfile(20.0, 1.0, 0.0),
            run_command=run,
            read_text=read_text,
        )
        self.assertEqual(commands[0][:5], ["tc", "qdisc", "replace", "dev", "w2-eth0"])
        self.assertEqual(commands[1], ["tc", "-s", "-j", "qdisc", "show", "dev", "w2-eth0"])
        self.assertEqual(record["operstate"], "up")
        self.assertEqual(record["sample"]["rx_bytes"], 100)
        self.assertEqual(record["sample"]["tx_dropped"], 2)


if __name__ == "__main__":
    unittest.main()
