API reference
=============


For users
---------

.. module:: apns_worker

.. autoclass:: ApnsManager
    :members: send_message, send_aps, flush_messages, get_feedback

.. autoclass:: Message
    :members: tokens, payload, expiration, priority

.. autoclass:: Error
    :members: ERR_PROCESSING, ERR_NO_TOKEN, ERR_NO_TOPIC, ERR_NO_PAYLOAD, ERR_TOKEN_SIZE, ERR_TOPIC_SIZE, ERR_PAYLOAD_SIZE, ERR_TOKEN_INVAL, ERR_UNKNOWN
    :undoc-members:

.. autoclass:: Feedback


For backend developers
----------------------

.. autoclass:: apns_worker.backend.base.Backend
    :members:

.. autoclass:: apns_worker.queue.NotificationQueue
    :members:

.. autoclass:: apns_worker.data.Notification
    :members:
