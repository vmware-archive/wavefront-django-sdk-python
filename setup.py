#!/usr/bin/env python3
# coding: utf-8
"""Wavefront Django SDK.

<p>This is a Wavefront Django SDK</p>
"""

import os

import setuptools

with open(os.path.join(os.path.abspath(os.path.dirname(__file__)),
                       'README.md')) as fd:
    LONG_DESCRIPTION = fd.read()

setuptools.setup(
    name='wavefront-django-sdk-python',
    version='1.0',
    author='Wavefront by VMware',
    author_email='songhao@vmware.com',
    url='https://github.com/wavefrontHQ/wavefront-django-sdk-python',
    license='Apache-2.0',
    description='Wavefront Django SDK',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    keywords=[
        'Wavefront',
        'Wavefront SDK',
        'Django'
    ],
    classifiers=[
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ],
    include_package_data=True,
    packages=setuptools.find_packages(exclude=('*.tests', '*.tests.*',
                                               'tests.*', 'tests')),
    install_requires=(
        'django>=1.11',
        'django-opentracing>=1.1',
        'wavefront-opentracing-sdk-python>=1.2'
    )
)
