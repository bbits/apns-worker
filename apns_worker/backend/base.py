from abc import ABCMeta, abstractmethod

from six import add_metaclass


@add_metaclass(ABCMeta)
class Backend(object):
    """
    Base class for APNs backends.

    The arguments to __init__ are unspecified and subject to change. If a
    subclass wishes to add its own initialization, it must accept any arguments
    and pass them to the superclass.

    Backend instances will have key parameters set as instance attributes.

    .. attribute:: queue

        Our :class:`~apns_worker.queue.NotificationQueue`.

    .. attribute:: environment

        The APNs environment to talk to (`'sandbox'` or `'production'`).

    .. attribute:: key_path

        Path to our PEM-encoded TLS client key.

    .. attribute:: cert_path

        Path to our PEM-encoded TLS client certificate.

    """
    def __init__(self, queue, environment, key_path, cert_path, error_handler):
        self.queue = queue
        self.environment = environment
        self.key_path = key_path
        self.cert_path = cert_path
        self._error_handler = error_handler

        queue._set_backend(self)

    @abstractmethod
    def start(self):
        """
        Override this.

        Starts processing notifications.

        """

    @abstractmethod
    def stop(self):
        """
        Override this.

        Stops processing notifications.

        """

    @abstractmethod
    def start_feedback(self, callback):
        """
        Override this.

        Opens the APNs feedback connection. The callback will be called zero or
        more times with a :class:`~apns_worker.Feedback` object as the single
        argument.

        """

    @abstractmethod
    def queue_lock(self):
        """
        Override this.

        Returns an object compatible with :class:`threading.Lock`. Subclasses
        that don't require locking may return a dummy lock.

        """

    @abstractmethod
    def queue_notify(self):
        """
        Override this.

        Notifies listeners that the queue may have new items available.

        This is always called while the object returned by
        :meth:`~apns_worker.backend.base.Backend.queue_lock` is acquired,
        making it compatible with condition variable semantics.

        """

    @abstractmethod
    def sleep(self, seconds):
        """
        Override this.

        Sleeps for the given number of seconds.

        """

    def delivery_error(self, error):
        """
        Reports a permanent error delivering a message.

        :type message: :class:`~apns_worker.Message`
        :param str token: The specific token that failed.
        :type error: :class:`~apns_worker.Error`

        """
        if self._error_handler is not None:
            self._error_handler(error)
