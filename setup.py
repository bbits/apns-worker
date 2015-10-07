from setuptools import setup
import sys


setup(
    name='apns-worker',
    version='0.1',
    description="A robust client library for Apple's push notification service.",
    long_description=open('README.rst').read(),
    author='Peter Sagerson',
    author_email='psagers@getcloak.com',
    url='https://github.com/bbits/apns-worker',
    license='BSD',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

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
    tests_require=['mock'] if sys.version_info < (3, 3) else [],
)
