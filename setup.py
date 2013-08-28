# -*- encoding: utf-8 -*-
from setuptools import setup, find_packages
import sys
import os

version = '0.1'

if __name__ == '__main__':
    setup(
        name='pyzar',
        version=version,
        description="Utilities for enabling automation of financial information retrieval in South Africa",
        classifiers=["Development Status :: 4 - Beta",
                     "Intended Audience :: Developers",
                     "License :: OSI Approved :: GNU General Public License (GPL)",
                     "Operating System :: OS Independent",
                     "Programming Language :: Python",
                     "Topic :: Office/Business :: Financial",
                     ],
        keywords='',
        author='David Fraser',
        author_email='davidf@sjsoft.com',
        url='http://github.org/davidfraser/pyzar',
        license='GPL',
        packages=find_packages(),
        include_package_data=True,
        zip_safe=False,
        install_requires=['html5lib', 'requests', 'genshi', 'lxml'],
        entry_points = {
            'console_scripts': [
                'stdbank_download_statements = pyzar.stdbank.download_statements:main',
                'stdbank_csv2ofx = pyzar.stdbank.csv2ofx:main',
                'discoverycard_download_statements = pyzar.discoverycard.download_statements:main',
                'discoverycard_csv2ofx = pyzar.discoverycard.csv2ofx:main',
                'discoverycard_extractofx = pyzar.discoverycard.extractofx:main',
            ],
        },
        )

