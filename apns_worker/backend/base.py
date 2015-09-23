class Backend(object):
    """
    Base class for APNs backends.

    The arguments to __init__ are unspecified and subject to change. If a
    subclass wishes to add its own initialization, it must accept any arguments
    and pass them to the superclass. It is preferable to perform initialization
    in the :meth:`start` method.

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

    def start(self):
        """
        Start processing notifications.
        """
        raise NotImplementedError()

    def stop(self):
        """
        Stop processing notifications.
        """
        raise NotImplementedError()

    def start_feedback(self, callback):
        """
        Open the APNs feedback connection.

        The callback will be called zero or more times with a
        :class:`~apns_worker.Feedback` object as the single argument.

        """
        raise NotImplementedError()

    def queue_lock(self):
        """
        Returns an object compatible with :class:`threading.Lock`.
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
        Sleeps for the given number of seconds.
        """
        raise NotImplementedError()

    def delivery_error(self, error):
        """
        Reports a permanent error delivering a message.

        :type message: :class:`~apns_worker.apns.Message`.
        :param str token: The specific token that failed.
        :type error: :class:`~apns_worker.apns.Error`.

        """
        if self._error_handler is not None:
            self._error_handler(error)
