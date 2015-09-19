# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from datetime import datetime
import unittest

from apns_worker.apns import Message


_token1 = '1ba97ad1311307c189696e2369c89fa83d652611a6e3c7370881289e45668fd3'
_token2 = '4c23f042050f48da350cb1079d61189cf7a47cb8df087429c0b2da65226cbecc'


class MessageTestCase(unittest.TestCase):
    def test_bad_token(self):
        with self.assertRaises(Exception):
            Message(['bogus'], {})

    def test_bad_payload(self):
        with self.assertRaises(Exception):
            Message([_token1], object())

    def test_bad_expiration(self):
        with self.assertRaises(Exception):
            Message([_token1], {}, expiration=5)

    def test_bad_priority(self):
        with self.assertRaises(Exception):
            Message([_token1], {}, priority='busted')

    def test_unicode_payload(self):
        Message([_token1], {'aps': {'alert': 'Ümlaut'}})

    def test_expiration(self):
        msg = Message([_token1], {}, expiration=datetime(2015, 1, 1))

        self.assertEqual(msg._encoded_expiration, 1420070400)

    def test_frame_1(self):
        msg = Message([_token1], {'aps': {'badge': 1}})
        frames = [notif.frame() for notif in msg.notifications()]

        self.assertEqual(
            frames,
            [b'\x02\x00\x00\x009\x01\x00 \x1b\xa9z\xd11\x13\x07\xc1\x89in#i\xc8\x9f\xa8=e&\x11\xa6\xe3\xc77\x08\x81(\x9eEf\x8f\xd3\x02\x00\x13{"aps":{"badge":1}}']
        )

    def test_frame_2(self):
        msg = Message([_token1], {'aps': {'badge': 1}}, expiration=datetime(2015, 1, 1), priority=5)
        frames = [notif.frame() for notif in msg.notifications()]

        self.assertEqual(
            frames,
            [b'\x02\x00\x00\x00D\x01\x00 \x1b\xa9z\xd11\x13\x07\xc1\x89in#i\xc8\x9f\xa8=e&\x11\xa6\xe3\xc77\x08\x81(\x9eEf\x8f\xd3\x02\x00\x13{"aps":{"badge":1}}\x04\x00\x04T\xa4\x8e\x00\x05\x00\x01\x05']
        )

    def test_frame_multiple(self):
        msg = Message([_token1, _token2], {'aps': {'badge': 1}}, expiration=datetime(2015, 1, 1), priority=5)
        frames = [notif.frame() for notif in msg.notifications()]

        self.assertEqual(
            frames,
            [
                b'\x02\x00\x00\x00D\x01\x00 \x1b\xa9z\xd11\x13\x07\xc1\x89in#i\xc8\x9f\xa8=e&\x11\xa6\xe3\xc77\x08\x81(\x9eEf\x8f\xd3\x02\x00\x13{"aps":{"badge":1}}\x04\x00\x04T\xa4\x8e\x00\x05\x00\x01\x05',
                b'\x02\x00\x00\x00D\x01\x00 L#\xf0B\x05\x0fH\xda5\x0c\xb1\x07\x9da\x18\x9c\xf7\xa4|\xb8\xdf\x08t)\xc0\xb2\xdae"l\xbe\xcc\x02\x00\x13{"aps":{"badge":1}}\x04\x00\x04T\xa4\x8e\x00\x05\x00\x01\x05',
            ]
        )
