from binascii import hexlify
from copy import copy
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
    def __init__(self, *args, **kwargs):
        super(Backend, self).__init__(*args, **kwargs)

        self.queue_cond = Condition()
        self.thread = None

    def start(self):
        self.thread = ReadThread(
            self, self.environment, self.key_path, self.cert_path,
            self.queue, self.queue_cond
        )
        self.thread.setDaemon(True)
        self.thread.start()

    def stop(self):
        if self.thread is not None:
            self.thread.terminate(wait=True)
            self.thread = None

    def start_feedback(self, callback):
        thread = FeedbackThread(self.environment, self.key_path, self.cert_path, callback)
        thread.start()

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
        self.connection = _new_connection(self._address(environment), key_path, cert_path)
        self.queue = queue
        self.queue_cond = queue_cond

        self.writer = None
        self._should_terminate = False

    def _address(self, environment):
        if environment == 'production':
            host = 'gateway.push.apple.com'
        else:
            host = 'gateway.sandbox.push.apple.com'

        return (host, 2195)

    def terminate(self, wait=True):
        with self.queue_cond:
            self._should_terminate = True
            self.connection.close()
            self.queue_cond.notify_all()

        if wait:
            self.join(1)
            if self.is_alive():
                logger.warning("Read thread did not terminate cleanly.")

    def run(self):
        logger.debug("Read thread starting.")

        while not self._should_terminate:
            try:
                self.wait_for_notification()
                if not self._should_terminate:
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
            while (not self.queue.has_unclaimed()) and (not self._should_terminate):
                self.queue_cond.wait()

    def start_writing(self):
        self.writer = WriteThread(self.connection, self.queue, self.queue_cond)
        self.writer.start()

    def wait_for_error(self):
        try:
            try:
                buf = self.connection.recv_min(6)
            finally:
                self.connection.close()
                self.stop_writing(wait=True)

            if len(buf) >= 6:
                self.handle_response_data(buf)
        except socket.error as e:
            logger.info("Socket error while reading: {0}.".format(e))
        except Exception as e:
            logger.warning("Exception while reading: {0}".format(e))

    def handle_response_data(self, buf):
        """ Process an error from the service. """
        try:
            _, status, ident = struct.unpack('!BBI', buf)
        except Exception as e:
            logger.warning("Failed to parse APNs response {0}: {1}".format(hexlify(buf), e))
        else:
            is_shutdown = (status == 10)
            notification = self.queue.backtrack(ident)
            if (notification is not None) and (not is_shutdown):
                error = apns.Error(status, notification.message, notification.token)
                logger.debug("Received response from push service: {0}".format(error))
                self.backend.delivery_error(error)

    def reset(self):
        self.connection.close()
        self.stop_writing(wait=False)
        self.connection = copy(self.connection)

    def stop_writing(self, wait=False):
        if self.writer is not None:
            self.writer.terminate(wait=wait)
            self.writer = None


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
        finally:
            self.connection.close()

        logger.debug("Write thread terminating.")

    def send_more_notifications(self):
        notification = self.wait_for_notification()
        if notification is not None:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Sending {0}".format(notification))

            try:
                self.connection.sendall(notification.frame())
            except Exception:
                self.queue.unclaim(notification)
                raise

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
    def __init__(self, environment, key_path, cert_path, callback):
        super(FeedbackThread, self).__init__()

        self.connection = _new_connection(self._address(environment), key_path, cert_path)
        self.callback = callback
        self.buf = b''

    def _address(self, environment):
        if environment == 'production':
            host = 'feedback.push.apple.com'
        else:
            host = 'feedback.sandbox.push.apple.com'

        return (host, 2196)

    def run(self):
        logger.debug("Feedback thread starting.")

        while not self.connection.is_closed:
            self.read_more()
            self.process_buffer()

        logger.debug("Feedback thread terminating.")

    def read_more(self):
        more = self.connection.recv()
        if len(more) > 0:
            self.buf += more
        else:
            self.connection.close()

    def process_buffer(self):
        feedback, remain = apns.Feedback.parse(self.buf)
        while feedback is not None:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("Received feedback: {0}".format(feedback))

            self.callback(feedback)
            feedback, remain = apns.Feedback.parse(remain)

        self.buf = remain


def _new_connection(address, key_path, cert_path):
    """ Mock target. """
    return Connection(address, key_path, cert_path)


class Connection(object):
    """
    A thread-safe read-write connection to the APN service.

    The TCP connection will be opened the first time it's needed. Once the
    connection is closed, it can not be reopened. Use the copy module to create
    a shallow copy with a new uninitialized socket.

    """
    def __init__(self, address, key_path, cert_path):
        self.address = address
        self.key_path = key_path
        self.cert_path = cert_path

        self.lock = RLock()
        self._sock = None
        self._is_closed = False

    def __copy__(self):
        return self.__class__(self.address, self.key_path, self.cert_path)

    def connect(self):
        """ Force connection, if necssary. """
        return (self.sock() is not None)

    @property
    def is_closed(self):
        return self._is_closed

    def recv_min(self, count):
        """
        Reads a specific number of bytes.

        This won't return until the requested bytes are read or the connection
        is closed.

        :param int count: Minimum bytes to wait for.

        """
        buf = b''

        while len(buf) < count:
            more = self.recv(count - len(buf))
            if len(more) > 0:
                buf += more
            else:
                break

        return buf

    def recv(self, bufsize=4096):
        sock = self.sock()

        return sock.recv(bufsize) if (sock is not None) else b''

    def sendall(self, buf):
        sock = self.sock()

        return sock.sendall(buf) if (sock is not None) else 0

    def close(self):
        with self.lock:
            if self._sock is not None:
                try:
                    logger.debug("Closing connection to {0}.".format(self.address))
                    self._sock.close()
                finally:
                    self._sock = None

            self._is_closed = True

    def sock(self):
        with self.lock:
            if (self._sock is None) and (not self._is_closed):
                logger.debug("Opening connection to {0}.".format(self.address))
                sock = socket.create_connection(self.address)
                sock = ssl.wrap_socket(
                    sock, self.key_path, self.cert_path,
                    ssl_version=ssl.PROTOCOL_TLSv1, ca_certs=self.ca_certs()
                )
                self._sock = sock

        return self._sock

    def ca_certs(self):
        """ Path to the anchor certs. """
        return os.path.join(os.path.dirname(apns_worker.__file__), 'certs/anchors.pem')
