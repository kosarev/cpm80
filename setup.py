#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import inspect
import os
import setuptools


here = os.path.abspath(os.path.dirname(inspect.getsource(lambda: 0)))

with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()


setuptools.setup(
    name='cpm80',
    version='1.0a6',
    description='CP/M-80 2.2 emulator with API',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Ivan Kosarev',
    author_email='mail@ivankosarev.com',
    url='https://github.com/kosarev/cpm80',
    license='MIT',
    packages=['cpm80'],
    install_requires=['z80', 'appdirs'],
    package_data={'cpm80': ['*.bin']},
    entry_points={
        'console_scripts': [
            'cpm80 = cpm80:main',
        ],
    },
    # TODO: test_suite='tests.testsuite.suite',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: Education',
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Information Technology',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Education',
        'Topic :: Games/Entertainment',
        'Topic :: Software Development',
        'Topic :: Software Development :: Libraries',
        'Topic :: System :: Emulators',
        'Topic :: System :: Operating System',
    ],
    )
