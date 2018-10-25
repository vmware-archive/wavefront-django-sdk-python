# coding: utf-8

"""
    Wavefront Django SDK
    <p>This is a Wavefront Django SDK</p>  # noqa: E501
"""

from setuptools import setup, find_packages  # noqa: H301

NAME = 'wavefront_django_sdk_python'
VERSION = '0.1.0'
# To install the library, run the following
#
# python setup.py install
#
# prerequisite: setuptools
# http://pypi.python.org/pypi/setuptools

REQUIRES = ['wavefront_pyformance']

setup(
    name=NAME,
    version=VERSION,
    description="Wavefront Django Python SDK",
    author_email="songhao@vmware.com",
    url="https://github.com/wavefrontHQ/wavefront-django-sdk-python",
    keywords=["Wavefront SDK", "Wavefront", "Django"],
    install_requires=REQUIRES,
    packages=find_packages(exclude=["*.tests", "*.tests.*", "tests.*", "tests"]),
    include_package_data=True,
    long_description="""\
    """
)
