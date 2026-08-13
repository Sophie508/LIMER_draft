import struct
import unittest

from limer_v0.linkwatch import (
    IFF_LOWER_UP,
    IFF_RUNNING,
    IFINFOMSG,
    IFLA_OPERSTATE,
    NLMSG_HDR,
    RTATTR_HDR,
    RTM_DELLINK,
    RTM_NEWLINK,
    parse_link_messages,
)


def build_message(
    msg_type=RTM_NEWLINK,
    ifindex=7,
    flags=IFF_LOWER_UP | IFF_RUNNING | 1,
    operstate=None,
):
    attrs = b""
    if operstate is not None:
        attr_len = RTATTR_HDR.size + 1
        attrs = RTATTR_HDR.pack(attr_len, IFLA_OPERSTATE) + bytes([operstate])
        attrs += b"\x00" * (-len(attrs) % 4)
    body = IFINFOMSG.pack(0, 0, 1, ifindex, flags, 0) + attrs
    header = NLMSG_HDR.pack(NLMSG_HDR.size + len(body), msg_type, 0, 0, 0)
    return header + body


class ParseLinkMessagesTest(unittest.TestCase):
    def test_healthy_link_is_not_down(self):
        records = parse_link_messages(build_message(operstate=6))
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0]["link_down"])
        self.assertEqual(records[0]["operstate"], "up")
        self.assertEqual(records[0]["ifindex"], 7)

    def test_carrier_loss_is_down(self):
        records = parse_link_messages(
            build_message(flags=1, operstate=3)  # IFF_UP only, lowerlayerdown
        )
        self.assertTrue(records[0]["link_down"])
        self.assertEqual(records[0]["operstate"], "lowerlayerdown")

    def test_admin_down_without_operstate_attr_is_down(self):
        records = parse_link_messages(build_message(flags=0))
        self.assertTrue(records[0]["link_down"])
        self.assertIsNone(records[0]["operstate"])

    def test_dellink_is_down(self):
        records = parse_link_messages(
            build_message(msg_type=RTM_DELLINK, flags=IFF_LOWER_UP | IFF_RUNNING | 1)
        )
        self.assertTrue(records[0]["link_down"])
        self.assertTrue(records[0]["deleted"])

    def test_multiple_messages_in_one_datagram(self):
        data = build_message(ifindex=3, operstate=6) + build_message(
            ifindex=9, flags=1, operstate=2
        )
        records = parse_link_messages(data)
        self.assertEqual([record["ifindex"] for record in records], [3, 9])
        self.assertEqual(
            [record["link_down"] for record in records], [False, True]
        )

    def test_truncated_datagram_is_tolerated(self):
        data = build_message(operstate=6)
        self.assertEqual(len(parse_link_messages(data[:10])), 0)
        records = parse_link_messages(data + data[:6])
        self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
