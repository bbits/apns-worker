from binascii import hexlify
import logging
import os.path
import socket
import ssl
import struct
from threading import Thread, RLock, Condition
import time

import apns_worker
from apns_worker import apns

from . import base


logger = logging.getLogger(__name__)


class Backend(base.Backend):
    """
    A backend that uses the native Python concurrency model.

    This uses Python threads to interact with APNs.

    """
    def start(self, queue, daemon=True):
        self.queue_cond = Condition()

        thread = ReadThread(self, self.environment, self.cert_path, self.key_path, queue, self.queue_cond)
        thread.deamon = daemon
        thread.start()

    def start_feedback(self, callback):
        pass

    def queue_lock(self):
        return self.queue_cond

    def queue_notify(self):
        self.queue_cond.notify_all()

    def sleep(self, seconds):
        time.sleep(seconds)


class ReadThread(Thread):
    """
    The master thread managing our APNs connection.

    This creates our connection to the service and waits for errors to arrive.
    It runs indefinitely, reconnecting as necessary.

    """
    def __init__(self, backend, environment, key_path, cert_path, queue, queue_cond):
        super(ReadThread, self).__init__()

        self.backend = backend
        self.connection = Connection(self._address(environment), key_path, cert_path)
        self.queue = queue
        self.queue_cond = queue_cond

    def _address(self, environment):
        if environment == 'production':
            host = 'gateway.push.apple.com'
        else:
            host = 'gateway.sandbox.push.apple.com'

        return (host, 2195)

    def run(self):
        logger.debug("Read thread starting.")

        while True:
            try:
                self.wait_for_notification()
                self.start_writing()
                self.wait_for_error()
            except Exception as e:
                logger.warning("Uncaught exception in read thread: {0}".format(e))
            finally:
                self.reset()

        logger.debug("Read thread terminating.")

    def wait_for_notification(self):
        """ Blocks until we have a notification to send. """
        with self.queue_cond:
            while not self.queue.has_unclaimed():
                self.queue_cond.wait()

    def start_writing(self):
        self.writer = WriteThread(self.connection, self.queue, self.queue_cond)
        self.writer.start()

    def wait_for_error(self):
        try:
            try:
                buf = self.connection.recv(6)
            finally:
                self.reset()

            if buf is not None:
                logger.debug("Received error response from APNs push service.")
                self.handle_response_data(buf)
        except socket.error as e:
            logger.info("Socket error while reading: {0}.".format(e))
        except Exception as e:
            logger.warning("Exception while reading: {0}".format(e))

    def reset(self):
        logger.debug("Resetting connection.")

        self.connection.close()
        self.stop_writing()

    def stop_writing(self):
        if self.writer is not None:
            self.writer.terminate(wait=True)
            self.writer = None

    def handle_response_data(self, buf):
        """ Process an error from the service. """
        try:
            _, status, ident = struct.unpack('!BBI', buf)
        except Exception as e:
            logger.warning("Failed to parse APNs response {0}: {1}".format(hexlify(buf), e))
        else:
            is_shutdown = (status == 10)
            notification = self.queue.backtrack(ident, inclusive=is_shutdown)
            if (notification is not None) and (not is_shutdown):
                error = apns.Error(status, notification.message, notification.token)
                self.backend.delivery_error(error)


class WriteThread(Thread):
    """
    A thread to pull notifications from the queue and send them over the wire.

    This is subordinate to the read thread, above. Once the connection is open,
    this thread is started and writes notifications indefinitely. When the
    socket closes, it terminates. The read thread will spawn a new write thread
    when it's ready to start writing again.

    """
    def __init__(self, connection, queue, queue_cond):
        super(WriteThread, self).__init__()

        self.connection = connection
        self.queue = queue
        self.queue_cond = queue_cond

        self._should_terminate = False

    def run(self):
        logger.debug("Write thread starting.")

        try:
            while not self._should_terminate:
                self.send_more_notifications()
        except socket.error as e:
            logger.info("Socket error while writing {0}.".format(e))
        except Exception as e:
            logger.warning("Exception while writing: {0}".format(e))

        logger.debug("Write thread terminating.")

    def send_more_notifications(self):
        notification = self.wait_for_notification()
        if notification is not None:
            self.connection.sendall(notification.frame())

    def wait_for_notification(self):
        with self.queue_cond:
            notification = self.claim_notification()
            while (notification is None) and (not self._should_terminate):
                self.queue_cond.wait()
                notification = self.claim_notification()

        return notification

    def claim_notification(self):
        return (self.queue.claim() if (not self._should_terminate) else None)

    def terminate(self, wait=True):
        with self.queue_cond:
            self._should_terminate = True
            self.queue_cond.notify_all()

        if wait:
            self.join(1)
            if self.is_alive():
                logger.warning("Write thread did not terminate cleanly.")


class FeedbackThread(Thread):
    """
    Handles a connection to the feedback service.

    This makes a new connection to the feedback service and sends items to the
    callback as they arrive. It terminates when the connection is closed from
    the other end.

    """
    def __init__(self, cert_path, key_path, environment, callback):
        super(FeedbackThread, self).__init__()

        self.cert_path = cert_path
        self.key_path = key_path
        self.environment = environment
        self.callback = callback

    def run(self):
        pass


class Connection(object):
    """
    A thread-safe read-write connection to the APN service.

    The actual TCP connection is created or recreated as needed. All exceptions
    are allowed to propagate.

    """
    def __init__(self, address, key_path, cert_path):
        self.address = address
        self.cert_path = cert_path
        self.key_path = key_path

        self.lock = RLock()
        self._sock = None

    def connect(self):
        return (self.sock is not None)

    def recv(self, bufsize):
        return self.sock.recv(bufsize)

    def sendall(self, buf):
        return self.sock.sendall(buf)

    def close(self):
        with self.lock:
            if self._sock is not None:
                try:
                    self._sock.close()
                finally:
                    self._sock = None

    @property
    def sock(self):
        with self.lock:
            if self._sock is None:
                sock = socket.create_connection(self.address)
                sock = ssl.wrap_socket(sock, self.key_path, self.cert_path, ca_certs=self.ca_certs())
                self._sock = sock

        return self._sock

    def ca_certs(self):
        """ Path to the anchor certs. """
        return os.path.join(os.path.dirname(apns_worker.__file__), 'certs/anchors.pem')
