# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from datetime import datetime, timedelta
from threading import Condition
import unittest

from apns_worker.apns import Message
from apns_worker.backend.base import Backend
from apns_worker.datetime import Now
from apns_worker.queue import NotificationQueue


_token1 = '1111111111111111111111111111111111111111111111111111111111111111'
_token2 = '2222222222222222222222222222222222222222222222222222222222222222'
_token3 = '3333333333333333333333333333333333333333333333333333333333333333'


class QueueTestCase(unittest.TestCase):
    def setUp(self):
        super(QueueTestCase, self).setUp()

        self.backend = TestBackend()
        self.queue = NotificationQueue(self.backend, grace=10)

    def tearDown(self):
        del self.queue
        del self.backend

        super(QueueTestCase, self).tearDown()

    def test_append(self):
        message = Message([_token1, _token2], {})

        self.queue.append(message)

        self.assertEqual(len(self.queue._queue), 2)
        self.assertTrue(all(item.expires is None for item in self.queue._queue))
        self.assertEqual(self.backend.notifies, 1)

    def test_claim_empty(self):
        notif = self.queue.claim()

        self.assertTrue(notif is None)

    def test_claim(self):
        message = Message([_token1, _token2], {})

        self.queue.append(message)
        notif = self.queue.claim()

        self.assertTrue(notif is not None)
        self.assertEqual(len(self.queue._queue), 2)
        self.assertEqual(self.queue._next, 1)
        self.assertTrue(self.queue._queue[0].expires is not None)
        self.assertTrue(self.queue._queue[1].expires is None)

    def test_claim_all(self):
        message = Message([_token1, _token2], {})

        self.queue.append(message)
        self.queue.claim()
        self.queue.claim()
        notif = self.queue.claim()

        self.assertTrue(notif is None)
        self.assertEqual(len(self.queue._queue), 2)
        self.assertEqual(self.queue._next, 2)
        self.assertTrue(all(item.expires is not None for item in self.queue._queue))

    def test_backtrack_empty(self):
        self.queue.backtrack(0)

        self.assertEqual(len(self.queue._queue), 0)
        self.assertEqual(self.queue._next, 0)

    def test_backtrack_all(self):
        message = Message([_token1, _token2], {})

        self.queue.append(message)
        self.queue.claim()
        self.queue.claim()
        self.queue.backtrack(0, inclusive=True)

        self.assertEqual(len(self.queue._queue), 2)
        self.assertEqual(self.queue._next, 0)
        self.assertTrue(all(item.expires is None for item in self.queue._queue))
        self.assertEqual(self.backend.notifies, 2)

    def test_backtrack_exclusive(self):
        message = Message([_token1, _token2, _token3], {})

        self.queue.append(message)
        self.queue.claim()
        self.queue.claim()
        self.queue.backtrack(0, inclusive=False)

        self.assertEqual(len(self.queue._queue), 2)
        self.assertEqual(self.queue._next, 0)
        self.assertTrue(all(item.expires is None for item in self.queue._queue))
        self.assertEqual(self.backend.notifies, 2)

    def test_purge_none(self):
        message = Message([_token1, _token2, _token3], {})

        self.queue.append(message)
        self.queue.claim()
        self.queue.claim()
        delay = self.queue.purge_expired()

        self.assertEqual(len(self.queue._queue), 3)
        self.assertEqual(self.queue._next, 2)
        self.assertLessEqual(delay, self.queue._grace)

    def test_purge(self):
        start = datetime(2015, 1, 1)
        message = Message([_token1, _token2, _token3], {})

        self.queue.append(message)
        with Now(start):
            self.queue.claim()
        with Now(start + timedelta(seconds=5)):
            self.queue.claim()

        with Now(start + timedelta(seconds=self.queue._grace + 1)):
            delay = self.queue.purge_expired()

        self.assertEqual(len(self.queue._queue), 2)
        self.assertEqual(self.queue._next, 1)
        self.assertLessEqual(delay, self.queue._grace)

    def test_purge_all(self):
        start = datetime(2015, 1, 1)
        message = Message([_token1, _token2, _token3], {})

        self.queue.append(message)
        with Now(start + timedelta(seconds=5)):
            self.queue.claim()
            self.queue.claim()
            self.queue.claim()

        with Now(start + timedelta(seconds=self.queue._grace + 6)):
            delay = self.queue.purge_expired()

        self.assertEqual(len(self.queue._queue), 0)
        self.assertEqual(self.queue._next, 0)
        self.assertEqual(delay, self.queue._grace)

    def test_is_empty_new(self):
        self.assertTrue(self.queue.is_empty())

    def test_not_empty(self):
        message = Message([_token1, _token2, _token3], {})

        self.queue.append(message)

        self.assertFalse(self.queue.is_empty())


class TestBackend(Backend):
    def __init__(self):
        self.lock = Condition()

        # Statistics
        self.notifies = 0

    def queue_lock(self):
        return self.lock

    def queue_notify(self):
        self.notifies += 1

        self.lock.notify_all()