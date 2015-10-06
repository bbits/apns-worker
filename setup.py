from setuptools import setup


setup(
    name='apns-worker',
    version='0.1',

    install_requires=[
        'six',
    ],
    packages=[
        'apns_worker',
        'apns_worker.backend',
        'apns_worker.tests',
    ],
    include_package_data=True,
    zip_safe=False,

    test_suite='apns_worker.tests',
    tests_require=[
        'mock',
    ],
)
