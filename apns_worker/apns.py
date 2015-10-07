from __future__ import unicode_literals, absolute_import

from binascii import hexlify, unhexlify
from calendar import timegm
from collections import namedtuple
from datetime import datetime, timedelta
from importlib import import_module
from itertools import repeat
import json
import logging
from struct import unpack

from six import python_2_unicode_compatible
from six.moves import map, range

from .data import Notification
from .queue import NotificationQueue


logger = logging.getLogger(__name__)


class ApnsManager(object):
    """
    Top-level object for sending Apple push notifications.

    One instance of this object manages a single connection to the Apple push
    notification service and a single queue of notifications to send. For most
    purposes, a single global instance should be sufficient. For high volumes,
    it may be worthwhile to create multiple instances and distribute messages
    across them.

    :param str key_path: Path to your PEM-encoded APNs client key.
    :param str cert_path: Path to your PEM-encoded APNs client certificate.

    :param str environment: APNs environment: `'sandbox'` or `'production'`.

    :param str backend_path: Module path to a subclass of
        :class:`apns_worker.backend.base.Backend`. The backend provides the
        network access and concurrency.

    :param int message_grace: Number of seconds to hold on to a delivered
        message before assuming that it was successful.

    :param error_handler: An optional function to process delivery errors. The
        function should take one argument, which will be an
        :class:`~apns_worker.Error`.

    """
    def __init__(self, key_path, cert_path,
                 environment='production',
                 backend_path='apns_worker.backend.threaded.Backend',
                 message_grace=5, error_handler=None):

        self._queue = NotificationQueue(grace=message_grace)
        self._backend = self._load_backend(backend_path, environment, key_path, cert_path, error_handler)

        self._backend.start()

    def _load_backend(self, path, environment, key_path, cert_path, error_handler):
        path, name = path.rsplit('.', 1)
        mod = import_module(path)
        backend_cls = getattr(mod, name)

        return backend_cls(self._queue, environment, key_path, cert_path, error_handler)

    #
    # Client APIs
    #

    def send_aps(self, tokens, alert=None, badge=None, sound=None, content_available=None, category=None):
        """
        A convenience API to send a standard notification.

        If you're sending a simple notification with a standard payload, you
        can use this shortcut API instead of constructing a :class:`Message`
        manually. Specify any arguments that you wish to include in the `'aps'
        dictionary
        <https://developer.apple.com/library/ios/documentation/NetworkingInternet/Conceptual/RemoteNotificationsPG/Chapters/ApplePushService.html#//apple_ref/doc/uid/TP40008194-CH100-SW1>`_
        of the payload.

        :param tokens:
        :type tokens: list of str
        :param alert:
        :type alert: str or dictionary
        :param int badge:
        :param str sound:
        :param bool content_available:
        :param str category:

        """
        aps = {}
        if alert is not None:
            aps['alert'] = alert
        if badge is not None:
            aps['badge'] = badge
        if sound is not None:
            aps['sound'] = sound
        if content_available:
            aps['content-available'] = 1
        if category is not None:
            aps['category'] = category

        message = Message(tokens, {'aps': aps})

        return self.send_message(message)

    def send_message(self, message):
        """
        Queues a message for delivery.

        :param message:
        :type message: :class:`~apns_worker.Message`

        """
        self._queue.append(message)

    def flush_messages(self):
        """
        Wait until all queued messages have been delivered.

        This will not return until all messages have been presumed successful
        (according to the delivery grace period).

        The only reason to call this is to make sure the queue is empty before
        allowing a process to terminate.

        """
        delay = self._queue.purge_expired()
        while not self._queue.is_empty():
            self._backend.sleep(delay)
            delay = self._queue.purge_expired()

    def get_feedback(self, callback):
        """
        Start retrieving tokens from the APNs feedback service.

        This will deliver :class:`~apns_worker.Feedback` items to the callback
        asynchronously.

        :param callback: A function that takes a single
            :class:`~apns_worker.Feedback` object. The callback will be called
            zero or more times.

        """
        self._backend.start_feedback(callback)


class Message(object):
    """
    A single push notification to be sent to one or more devices.

    :param list tokens: A list of hex-encoded device tokens.
    :param dict payload: `Payload dictionary
        <https://developer.apple.com/library/ios/documentation/NetworkingInternet/Conceptual/RemoteNotificationsPG/Chapters/ApplePushService.html#//apple_ref/doc/uid/TP40008194-CH100-SW1>`_.
    :param datetime expiration: An expiration time (optional). If this is a
        naive datetime, it is assumed to be UTC.
    :param int priority: Notification priority (optional). According to the
        current docs, 10 = send now and 5 = send when convenient.

    This validates arguments fairly aggressively and may raise standard
    exceptions.

    """
    def __init__(self, tokens, payload, expiration=None, priority=None):
        self._tokens = tokens
        self._payload = payload
        self._expiration = expiration
        self._priority = priority

        self._validate()

    def _validate(self):
        self._validate_tokens()
        self._validate_payload()
        self._validate_expiration()
        self._validate_priority()

    def _validate_tokens(self):
        self._encoded_tokens = list(map(unhexlify, self._tokens))

    def _validate_payload(self):
        self._encoded_payload = json.dumps(self.payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')

    def _validate_expiration(self):
        if self.expiration is not None:
            self._encoded_expiration = int(timegm(self.expiration.utctimetuple()))
        else:
            self._encoded_expiration = None

    def _validate_priority(self):
        if self.priority is None:
            pass
        elif isinstance(self.priority, int) and self.priority in range(0, 256):
            pass
        else:
            raise TypeError("Priority must be an integer in [0, 255] or None")

    @property
    def tokens(self):
        return self._tokens

    @property
    def payload(self):
        return self._payload

    @property
    def expiration(self):
        return self._expiration

    @property
    def priority(self):
        return self._priority

    def notifications(self, idents=None):
        """
        Generates a sequence of serializable notifications.

        This generates a sequence of Notification objects, each of which can be
        serialized onto the wire.

        :param iterable idents: An optional iterable of 32-bit identifiers for
            the notifications. :func:`itertools.count` is useful here.

        """
        if idents is None:
            idents = repeat(None)

        for encoded_token in self._encoded_tokens:
            yield Notification(self, encoded_token, next(idents))


@python_2_unicode_compatible
class Error(namedtuple('Error', ['status', 'message', 'token'])):
    """
    Represents a delivery error returned by APNs.

    These are only generated for unrecoverable errors that the client might
    want to know about.

    .. attribute:: status

        The `APNs status code
        <https://developer.apple.com/library/ios/documentation/NetworkingInternet/Conceptual/RemoteNotificationsPG/Chapters/CommunicatingWIthAPS.html#//apple_ref/doc/uid/TP40008194-CH101-SW4>`_.

    .. attribute:: description

        A human-readable description of the error.

    .. attribute:: message

        The :class:`~apns_worker.Message` that generated the error.

    .. attribute:: token

        The specific device token that generated the error.

    """
    ERR_PROCESSING = 1
    ERR_NO_TOKEN = 2
    ERR_NO_TOPIC = 3
    ERR_NO_PAYLOAD = 4
    ERR_TOKEN_SIZE = 5
    ERR_TOPIC_SIZE = 6
    ERR_PAYLOAD_SIZE = 7
    ERR_TOKEN_INVAL = 8
    ERR_UNKNOWN = 255

    descriptions = {
        ERR_PROCESSING: "Processing error",
        ERR_NO_TOKEN: "Missing device token",
        ERR_NO_TOPIC: "Missing topic",
        ERR_NO_PAYLOAD: "Missing payload",
        ERR_TOKEN_SIZE: "Invalid token size",
        ERR_TOPIC_SIZE: "Invalid topic size",
        ERR_PAYLOAD_SIZE: "Invalid payload size",
        ERR_TOKEN_INVAL: "Invalid token",
    }

    def __str__(self):
        return "APNs error {0}: {1}".format(self.status, self.description)

    @property
    def description(self):
        return self.descriptions.get(self.status, "Unknown")


class Feedback(namedtuple('Feedback', ['token', 'when'])):
    """
    A single record from the APNs feedback service.

    .. attribute:: token

        A hex-encoded device token that can not receive notifications.

    .. attribute:: when

        The time at which this device stopped receiving notifications as a
        naive UTC datetime. If the device was registered with your service
        after this time, you can ignore this feedback.

    """
    _epoch = datetime(1970, 1, 1)

    @classmethod
    def parse(cls, buf):
        """
        Parses one Feedback object from the head of a byte string.

        :returns: A two-tuple with the parsed :class:`~apns_worker.Feedback`
            and the remaining bytes. The first element of the tuple will be
            `None` if it could not be parsed.
        :rtype: (:class:`~apns_worker.Feedback`, bytes)

        """
        feedback = None
        remainder = buf

        if len(buf) >= 6:
            timestamp, token_len = unpack('!IH', buf[:6])
            total_len = 6 + token_len

            if len(buf) >= total_len:
                token = hexlify(buf[6:total_len]).decode('ascii')
                when = cls._epoch + timedelta(seconds=timestamp)

                feedback = cls(token, when)
                remainder = buf[total_len:]

        return (feedback, remainder)
