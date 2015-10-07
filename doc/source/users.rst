Using apns-worker
=================


Sending notifications
---------------------

To send notifications, you first need an :class:`~apns_worker.ApnsManager`
instance. Typically this will be a global instance, created at program
initialization time, although you can create more than one. Note that rapidly
creating and abandoning instances will create many connections to Apple's
service, which their systems may regard as a denial of service attack.

::

    from apns_worker import ApnsManager

    apns = None

    def init_apns(key_path, cert_path):
        """ Call this once at program init time. """
        global apns

        apns = ApnsManager(key_path, cert_path)


To quickly send a standard message, call
:meth:`~apns_worker.ApnsManager.send_aps`::

    apns.send_aps(tokens, badge=1)
    apns.send_aps(tokens, alert="Your phlebotinum has arrived.")

APNs also allows you to include custom keys and values in the payload, as long
as it can be encoded in less than 2KB of JSON. To build your own payload, create
a :class:`~apns_worker.Message` instance and deliver it with
:class:`~apns_worker.ApnsManager.send_message`::

    from apns_worker import Message

    message = Message(tokens, {'aps': {'badge': 1}, 'channel': 'public'}, priority=5)
    apns.send_message(message)

Creating a Message also allows you to set the expiration and priority.


Handling errors
---------------

When creating your :class:`~apns_worker.ApnsManager` instance, you can provide a
callback to be notified of permanent delivery errors for your notifications::

    import logging

    logger = logging.getLogger(__name__)

    def init_apns(path_to_key, path_to_cert):
        """ Call this once at program init time. """
        global apns

        apns = ApnsManager(path_to_key, path_to_cert,
                           error_handler=_log_apns_error)

    def _log_apns_error(error):
        logger.info(str(error))


Getting feedback
----------------

The feedback service identifies device tokens that are no longer available to
accept notifications, such as when the app has been uninstalled. You should
check for feedback daily with :meth:`~apns_worker.ApnsManager.get_feedback` and
remove these device tokens from your database. For example, a Django app might
do the following in a daily task::

    def feedback_task():
        apns.get_feedback(_process_feedback)

    def _process_feedback(feedback):
        IOSDevice.objects.filter(token=feedback.token, last_seen__lt=feedback.when) \
                         .delete()

Feedback will be retrieved asynchronously by the backend and
:class:`~apns_worker.Feedback` objects will be passed to the provided callback.
