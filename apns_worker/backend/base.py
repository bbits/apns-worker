class Backend(object):
    """
    Base class for APNs backends.

    The arguments to __init__ are unspecified and subject to change. If a
    subclass wishes to add its own initialization, it must accept any arguments
    and pass them to the superclass. It is preferable to perform initialization
    in the :meth:`start` method.

    .. attribute:: environment

        The APNs environment to talk to (`'sandbox'` or `'production'`).

    .. attribute:: cert_path

        Path to our PEM-encoded TLS client certificate.

    .. attribute:: key_path

        Path to our PEM-encoded TLS client key.

    """
    def __init__(self, manager, environment, key_path, cert_path):
        self._manager = manager
        self.environment = environment
        self.key_path = key_path
        self.cert_path = cert_path

    def start(self, queue):
        """
        Start processing notifications from the given queue.
        """
        raise NotImplementedError()

    def start_feedback(self, callback):
        """
        Open the APNs feedback connection.

        The callback should be called with an iterable of
        :class:`~apns_worker.apns.Feedback` objects. The callback may be called
        multiple times if the records are being loaded asynchronously.

        """
        raise NotImplementedError()

    def queue_lock(self):
        """
        Return an object compatible with :class:`threading.Lock`.
        """
        raise NotImplementedError()

    def queue_notify(self):
        """
        Notification that the queue may have new items available.

        This is always called while the object returned by :meth:`queue_lock`
        is acquired, making it compatible with condition variable semantics.

        """
        raise NotImplementedError()

    def sleep(self, seconds):
        """
        Sleep for the given number of seconds.

        This should use a sleep function compatible with the backend's
        concurrency model.

        :type seconds: float

        """
        raise NotImplementedError()

    def delivery_error(self, error):
        """
        Reports a permanent error delivering a message.

        :type message: :class:`~apns_worker.apns.Message`.
        :param str token: The specific token that failed.
        :type error: :class:`~apns_worker.apns.Error`.

        """
        self._manager.delivery_error(error)
