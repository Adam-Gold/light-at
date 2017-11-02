import re
from setuptools import setup, find_packages

PYPI_RST_FILTERS = (
    # Replace code-blocks
    (r'\.\.\s? code-block::\s*(\w|\+)+', '::'),
    # Replace image
    (r'\.\.\s? image::.*', ''),
    # Remove travis ci badge
    (r'.*travis-ci\.org/.*', ''),
    # Remove pypip.in badges
    (r'.*pypip\.in/.*', ''),
    (r'.*crate\.io/.*', ''),
    (r'.*coveralls\.io/.*', ''),
)


def rst(filename):
    """
Load rst file and sanitize it for PyPI.
Remove unsupported git tags:
- code-block directive
- travis ci build badge
"""
    content = open(filename).read()
    for regex, replacement in PYPI_RST_FILTERS:
        content = re.sub(regex, replacement, content)
    return content


def required(filename):
    with open(filename) as f:
        packages = f.read().splitlines()

    return packages


setup(
    name="light-at",
    version="0.1.0",
    description="Light Ansible Tower",
    long_description=rst('README.rst') + rst('CHANGELOG.txt'),
    author="Adam Gold Balali",
    author_email="adambalali@gmail.com",
    url="https://github.com/AdamBalali/light-at",
    license="MIT",
    install_requires=required('requirements.txt'),
    setup_requires=[],
    # tests_require=[
    #     'pep8',
    #     'coveralls'
    # ],
    test_suite='tests',
    packages=find_packages(),
    include_package_data=True,
    package_data={'lightAt/config': ['config/*.ini']},
    zip_safe=False,
    scripts=[],
    entry_points={
        'console_scripts': [
            "lightAt=lightAt.lightAt:main",
            "lightAt-worker=lightAt.worker:main"
        ],
    },

    classifiers=[
        'Programming Language :: Python',
    ],
)
