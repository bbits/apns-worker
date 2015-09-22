from binascii import hexlify
from collections import namedtuple
from itertools import takewhile, repeat
import json
import logging
import socket
import struct
from threading import Condition
from time import sleep
import unittest

import mock
from six import BytesIO

from apns_worker import ApnsManager, Message


_token1 = '0101010101010101010101010101010101010101010101010101010101010101'
_token2 = '0202020202020202020202020202020202020202020202020202020202020202'
_token3 = '0303030303030303030303030303030303030303030303030303030303030303'


class BackendTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super(BackendTestCase, cls).setUpClass()

        logger = logging.getLogger('apns_worker')
        logger.setLevel(logging.WARNING)
        logger.addHandler(logging.StreamHandler())

    def setUp(self):
        super(BackendTestCase, self).setUp()

        self._connection_patch = mock.patch('apns_worker.backend.threaded._new_connection', self.new_connection)
        self._connection_patch.start()

        self._apns = None
        self.connections = []
        self.apns_error = None

    def tearDown(self):
        if self._apns is not None:
            self._apns._backend.stop()
            self._apns = None

        self._connection_patch.stop()
        del self._connection_patch

        super(BackendTestCase, self).tearDown()

    def test_wait_for_notification(self):
        self.assertFalse(self.apns._backend.thread.connection.opened)

    def test_send_notification(self):
        msg = Message([_token1], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.assertEqual(self.sent_tokens, [_token1])

    def test_send_multiple(self):
        msg = Message([_token1, _token2], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.assertEqual(self.sent_tokens, [_token1, _token2])

    def test_reject_last(self):
        msg = Message([_token1, _token2], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.connection.set_read_error(struct.pack('!BBI', 8, 1, self.sent_frames[-1].ident))

        sleep(0.1)

        self.assertEqual(self.connections_opened, 1)
        self.assertEqual(self.connections_closed, 1)
        self.assertEqual(self.sent_tokens, [_token1, _token2])
        self.assertEqual(self.apns_error.status, 1)

    def test_reject_middle(self):
        msg = Message([_token1, _token2, _token3], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.connection.set_read_error(struct.pack('!BBI', 8, 1, self.sent_frames[-2].ident))

        sleep(0.1)

        self.assertEqual(self.connections_opened, 2)
        self.assertEqual(self.connections_closed, 1)
        self.assertEqual(self.sent_tokens, [_token1, _token2, _token3, _token3])
        self.assertEqual(self.apns_error.status, 1)

    def test_reject_unknown(self):
        msg = Message([_token1, _token2, _token3], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.connection.set_read_error(struct.pack('!BBI', 8, 1, 100))

        sleep(0.1)

        self.assertEqual(self.connections_opened, 2)
        self.assertEqual(self.connections_closed, 1)
        self.assertEqual(self.sent_tokens, [_token1, _token2, _token3, _token1, _token2, _token3])
        self.assertEqual(self.apns_error, None)

    def test_shutdown(self):
        msg = Message([_token1, _token2, _token3], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.connection.set_read_error(struct.pack('!BBI', 8, 10, self.sent_frames[-2].ident))

        sleep(0.1)

        self.assertEqual(self.connections_opened, 2)
        self.assertEqual(self.connections_closed, 1)
        self.assertEqual(self.sent_tokens, [_token1, _token2, _token3, _token3])
        self.assertEqual(self.apns_error, None)

    def test_read_exc(self):
        msg = Message([_token1], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.connection.set_read_error(socket.error("Test error"))

        sleep(0.1)

        self.apns.send_message(msg)

        sleep(0.1)

        self.assertEqual(self.connections_opened, 2)
        self.assertEqual(self.connections_closed, 1)
        self.assertEqual(self.sent_tokens, [_token1, _token1])
        self.assertEqual(self.apns_error, None)

    def test_write_exc(self):
        self.apns
        self.connection.set_write_exc(socket.error("Test error"))
        msg = Message([_token1], {'aps': {'badge': 1}})
        self.apns.send_message(msg)

        sleep(0.1)

        self.assertEqual(self.connections_opened, 2)
        self.assertEqual(self.connections_closed, 1)
        self.assertEqual(self.sent_tokens, [_token1])
        self.assertEqual(self.apns_error, None)

    #
    # Hooks
    #

    def new_connection(self, *args, **kwargs):
        connection = TestConnection(self)
        self.connections.append(connection)

        return connection

    def handle_error(self, error):
        self.apns_error = error

    #
    # State
    #

    @property
    def apns(self):
        if self._apns is None:
            self._apns = ApnsManager(
                'key-path', 'cert-path',
                backend_path='apns_worker.backend.threaded.Backend',
                error_handler=self.handle_error
            )

        return self._apns

    @property
    def connection(self):
        return self.connections[-1] if len(self.connections) > 0 else None

    @property
    def connections_opened(self):
        return len([c for c in self.connections if c.opened])

    @property
    def connections_closed(self):
        return len([c for c in self.connections if c.closed])

    @property
    def sent_tokens(self):
        """ Tokens of send frames, in order. """
        return [frame.token for frame in self.sent_frames]

    @property
    def sent_idents(self):
        """ Idents of sent frames, in order. """
        return [frame.ident for frame in self.sent_frames]

    @property
    def sent_frames(self):
        """ All sent frames, in order. """
        return [frame for connection in self.connections for frame in connection.sent_frames]


class TestConnection(object):
    """ A fake apns_worker.backend.threaded.Connection. """
    def __init__(self, test_case):
        self.test_case = test_case

        self.outbuf = BytesIO()

        self.read_err = None
        self.write_exc = None

        self.cond = Condition()
        self.opened = False
        self.closed = False

        self._sent_frames = None

    def __copy__(self):
        return self.test_case.new_connection()

    def connect(self):
        self.opened = True

        return (not self.closed)

    def recv(self, bufsize):
        self.opened = True

        with self.cond:
            while (not self.closed) and (self.read_err is None):
                self.cond.wait()

            val = self.read_err or b''
            self.read_err = None

        if isinstance(val, Exception):
            raise val
        else:
            return val

    def sendall(self, buf):
        if self.closed:
            return 0

        self.opened = True
        self._sent_frames = None

        err = self.write_exc
        if err is not None:
            self.write_exc = None
            raise err
        else:
            return self.outbuf.write(buf)

    def close(self):
        with self.cond:
            self.closed = True
            self.cond.notify_all()

    #
    # Test methods
    #

    def set_read_error(self, val):
        """ Send data or an exception to the read thread. """
        with self.cond:
            self.read_err = val
            self.cond.notify_all()

    def set_write_exc(self, exc):
        """ Set an exception for sendall. """
        self.write_exc = exc

    @property
    def sent_frames(self):
        """ Returns Frame objects representing sent frames. """
        if self._sent_frames is None:
            stream = BytesIO(self.outbuf.getvalue())
            self._sent_frames = list(takewhile(lambda f: f is not None, (Frame.parse(stream) for i in repeat(None))))

        return self._sent_frames


class Frame(namedtuple('Frame', ['token', 'payload', 'ident', 'expiration', 'priority'])):
    """ A parsed APNs frame. """
    @classmethod
    def parse(cls, stream):
        frame = None

        try:
            cmd, length = struct.unpack('!BI', stream.read(5))
            if cmd == 2:
                items = cls._parse_items(stream, length)
                frame = cls(**items)
        except struct.error:
            pass

        return frame

    @classmethod
    def _parse_items(cls, stream, length):
        items = {
            'token': None,
            'payload': None,
            'ident': None,
            'expiration': None,
            'priority': None,
        }

        while length > 0:
            item_id, data_len = struct.unpack('!BH', stream.read(3))
            data = stream.read(data_len)

            if item_id == 1:
                items['token'] = hexlify(data).decode('ascii')
            elif item_id == 2:
                items['payload'] = data
            elif item_id == 3:
                items['ident'] = struct.unpack('!I', data)[0]
            elif item_id == 4:
                items['expiration'] = struct.unpack('!I', data)[0]
            elif item_id == 5:
                items['priority'] = struct.unpack('!B', data)[0]
            else:
                raise ValueError("Unknown item ID in frame: {0}".format(item_id))

            length -= (3 + data_len)

        return items

    @property
    def decoded(self):
        return json.loads(self.payload)
