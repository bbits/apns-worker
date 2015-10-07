"""
APNs data structures with serialization.
"""
from __future__ import unicode_literals, absolute_import

from binascii import hexlify
from struct import pack

from six import python_2_unicode_compatible


@python_2_unicode_compatible
class Notification(object):
    """
    An internal representation of a single notification to send.

    :param message: The original message.
    :type message: :class:`apns_worker.Message`

    :param bytes encoded_token: Binary representation of a device token.
    :param int ident: 32-bit notification identifier.

    """
    def __init__(self, message, encoded_token, ident):
        self.message = message
        self.encoded_token = encoded_token
        self.ident = ident

    def __str__(self):
        return "{0} -> {1}".format(self.message._encoded_payload, self.token)

    @property
    def token(self):
        """
        This notification's hex-encoded token.

        :rtype: str

        """
        return hexlify(self.encoded_token)

    def frame(self):
        """
        Renders this notification to an APNs frame.

        :returns: A complete frame, ready to be put on the wire.
        :rtype: bytes

        """
        encoded_payload = self.message._encoded_payload
        encoded_expiration = self.message._encoded_expiration
        priority = self.message.priority

        content = b''.join([
            pack('!BH32s', 1, 32, self.encoded_token),
            self._pack_data(2, encoded_payload),
            pack('!BHI', 3, 4, self.ident) if (self.ident is not None) else b'',
            pack('!BHI', 4, 4, encoded_expiration) if (encoded_expiration is not None) else b'',
            pack('!BHB', 5, 1, priority) if (priority is not None) else b'',
        ])

        frame = pack('!BI', 2, len(content)) + content

        return frame

    def _pack_data(self, item_id, data):
        """ Packs variable size data. """
        packed = b''

        if data is not None:
            length = len(data)
            packed = pack('!BH{0}s'.format(length), item_id, length, data)

        return packed
