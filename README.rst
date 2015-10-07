apns-worker
===========

This is a client library for Apple's push notification service. It is not the
first such library for Python, but, as is often the way, the existing options
didn't quite meet our needs:

#. **No dependencies** (other than six).
#. **Fire and forget**. APNs is a quirky binary protocol that frequently requires
   reconnecting to the service and re-sending notifications after an error.
#. **Robust**. We don't do quick and dirty here. Readability, tests, and
   documentation are not optional.


Quick start
-----------

An APNs client is by nature stateful. The default apns-worker backend uses
Python threads to asynchronously process a queue of messages to send to the
service. Most users will want to maintain a global ApnsManager instance to
process messages. Note that if your own program is threaded, you may need to
take care to create this global instance safely.

::

    from apns_worker import ApnsManager

    apns = None

    def init_apns(key_path, cert_path):
        """ Call this once at program init time. """
        global apns
        apns = ApnsManager(key_path, cert_path)

    def send_badge(token, badge=1):
        """ Badge the app on a single device. """
        apns.send_aps([token], badge=badge)
