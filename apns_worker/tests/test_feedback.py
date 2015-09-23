# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from binascii import unhexlify
from datetime import datetime, timedelta
from struct import pack
import unittest

from apns_worker.apns import Feedback


_token1 = '1ba97ad1311307c189696e2369c89fa83d652611a6e3c7370881289e45668fd3'
_token2 = '4c23f042050f48da350cb1079d61189cf7a47cb8df087429c0b2da65226cbecc'


class FeedbackTestCase(unittest.TestCase):
    _when = datetime(2015, 9, 1)
    _timestamp = int((_when - datetime(1970, 1, 1)).total_seconds())

    def test_parse_empty(self):
        buf = b''
        feedback, remainder = Feedback.parse(buf)

        self.assertEqual(feedback, None)
        self.assertEqual(remainder, buf)

    def test_parse_partial_1(self):
        buf = pack('!I', self._timestamp)
        feedback, remainder = Feedback.parse(buf)

        self.assertEqual(feedback, None)
        self.assertEqual(remainder, buf)

    def test_parse_partial_2(self):
        buf = pack('!IH', self._timestamp, 32)
        feedback, remainder = Feedback.parse(buf)

        self.assertEqual(feedback, None)
        self.assertEqual(remainder, buf)

    def test_parse_partial_3(self):
        buf = pack('!IH30s', self._timestamp, 32, unhexlify(_token1))
        feedback, remainder = Feedback.parse(buf)

        self.assertEqual(feedback, None)
        self.assertEqual(remainder, buf)

    def test_parse_one(self):
        buf = pack('!IH32s', self._timestamp, 32, unhexlify(_token1))
        feedback, remainder = Feedback.parse(buf)

        self.assertEqual(feedback.token, _token1)
        self.assertEqual(feedback.when, self._when)
        self.assertEqual(remainder, b'')

    def test_parse_leftovers(self):
        buf = pack('!IH32sI', self._timestamp, 32, unhexlify(_token1), 0x01020304)
        feedback, remainder = Feedback.parse(buf)

        self.assertEqual(feedback.token, _token1)
        self.assertEqual(feedback.when, self._when)
        self.assertEqual(remainder, b'\x01\x02\x03\x04')

    def test_parse_two(self):
        buf = pack(
            '!IH32sIH32s',
            self._timestamp, 32, unhexlify(_token1),
            self._timestamp + 1, 32, unhexlify(_token2)
        )
        f1, remainder = Feedback.parse(buf)
        f2, remainder = Feedback.parse(remainder)

        self.assertEqual(f1.token, _token1)
        self.assertEqual(f1.when, self._when)
        self.assertEqual(f2.token, _token2)
        self.assertEqual(f2.when, self._when + timedelta(seconds=1))
        self.assertEqual(remainder, b'')
