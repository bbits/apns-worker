from __future__ import unicode_literals, absolute_import

from collections import deque
from datetime import timedelta

from six.moves import map, range

from .datetime import now


class NotificationQueue(object):
    """
    A special queue for Notification objects.

    When a notification is claimed from the queue, we retain a reference to it
    with an expiration. Once expired, sent notifications are eventually purged.
    However, if a delivery failure is subsequently detected, the
    :meth:`backtrack` method can be used to rewind the queue to the first
    notification that failed.

    :param backend: A :cls:`~apns_worker.backend.base.Backend` to provide
    synchronization mechanisms.

    :param int grace: Seconds to leave a claimed notification in the queue
        before purging it.

    """
    def __init__(self, backend, grace):
        self._backend = backend
        self._grace = grace

        self._queue = deque()
        self._next = 0
        self._idents = _gen_identifiers()

        self._auto_purge_at = now() + timedelta(seconds=grace)

    def append(self, message):
        """
        Queues a message for delivery.

        :param message: A single message to queue for delivery.
        :type message: :cls:`~apns_worker.apns.Message`.

        """
        with self._backend.queue_lock():
            self._queue.extend(map(QueuedNotification, message.notifications(self._idents)))
            self._backend.queue_notify()

        self._auto_purge()

    def claim(self):
        """
        Returns the next notification to be sent.

        The returned notification is provisionally removed from the queue, but
        can be restored with a timely call to :meth:`backtrack`.

        """
        notification = None

        with self._backend.queue_lock():
            if self._next < len(self._queue):
                queued = self._queue[self._next]
                queued.expires = now() + timedelta(seconds=self._grace)
                notification = queued.notification
                self._next += 1

        return notification

    def backtrack(self, ident, inclusive=False):
        """
        Returns claimed notifications to the queue.

        All notifications after (and optionally including) `ident` are known to
        have failed and need to be re-queued. All notifications before `ident`
        are now known to have succeeded.

        :param int ident: Ident of the first failed notification.
        :param bool inclusive: True if the identified notification should be
            retried. False to abandon it and restart with the next one.

        :returns: The notification with the given ident, if found.
        :rtype: :class:`~apns_worker.data.Notification` or None.

        """
        notification = None

        with self._backend.queue_lock():
            queue = self._queue
            i = (self._next - 1) if (self._next > 0) else 0

            # Try to find the failed notification. We'll stop if we hit the
            # beginning of the queue.
            while (i > 0) and (queue[i].notification.ident != ident):
                i -= 1

            if i < len(queue) and (queue[i].notification.ident == ident):
                notification = queue[i].notification
                # Optionally skip over the one that failed.
                if (not inclusive):
                    i += 1

            # Everything else either succeeded or failed permanently.
            for j in range(i):
                queue.popleft()

            # Reset all expirations.
            for item in queue:
                item.expires = None

            self._next = 0

            self._backend.queue_notify()

        return notification

    def purge_expired(self):
        """
        Permanently removes notifications that have expired.

        This is called auomatically as oppotunities arise, but can also be
        called manually, for instance to drain the queue for termination.

        :returns: A recommended number of seconds to wait until the next call.
        :rtype: float

        """
        with self._backend.queue_lock():
            _now = now()
            is_expired = lambda queued: queued.is_claimed() and (queued.expires <= _now)

            while (len(self._queue) > 0) and is_expired(self._queue[0]):
                self._queue.popleft()
                self._next -= 1

            if len(self._queue) > 0 and self._queue[0].is_claimed():
                delay = (self._queue[0].expires - _now).total_seconds()
            else:
                delay = self._grace

        return max(delay, 1.0)

    def has_unclaimed(self):
        """
        Returns `True` if the queue has any unclaimed items.

        :rtype: bool

        """
        with self._backend.queue_lock():
            has_unclaimed = (self._next < len(self._queue))

        return has_unclaimed

    def is_empty(self):
        """
        Returns `True` if the queue has no items.

        This includes claimed and unclaimed items. Use this with
        :meth:`purge_expired` to wait for a decommissioned queue to drain.

        :rtype: bool

        """
        with self._backend.queue_lock():
            is_empty = (len(self._queue) == 0)

        return is_empty

    #
    # Internal
    #

    def _auto_purge(self):
        _now = now()

        with self._backend.queue_lock():
            if _now > self._auto_purge_at:
                delay = self.purge_expired()
                self._auto_purge_at = _now + timedelta(seconds=delay)


def _gen_identifiers():
    """ Generates sequential 32-bit notification identifiers. """
    while True:
        for i in range(2 ** 32):
            yield i


class QueuedNotification(object):
    __slots__ = ['notification', 'expires']

    def __init__(self, notification):
        self.notification = notification
        self.expires = None

    def is_claimed(self):
        return (self.expires is not None)
