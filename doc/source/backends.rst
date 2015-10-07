Custom backends
===============

apns-worker is designed to support pluggable backends that can implement
different concurrency models. The default backend uses Python threads to manage
connections, but it should be possible to implement other backends, such as one
based on gevent. Note that this has not been tested, so there may still be some
rough edges in the API.

To write your own backend, just subclass
:class:`apns_worker.backend.base.Backend` and fill in all of the abstract
methods. The backend will be responsible for starting and stopping asynchronous
network operations as well as providing queue synchronization, if necessary.
:class:`apns_worker.backend.threaded.Backend` can serve as a reference
implementation.
