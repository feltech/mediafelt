from setuptools import setup

setup(
    name='mediafelt',
    version='1.0',
    packages=[''],
    url='',
    license='GPL',
    author='David Feltell',
    author_email='',
    description='Parse and move media files',
    install_requires=[
        'guessit', 'pyyaml'
    ],
    package_data={
        'mediafelt': ["logging.yaml", "logging.yaml"]
    },
    entry_points={
        'console_scripts': [
            'mediafelt=mediafelt.main:main',
        ]
    }
)
