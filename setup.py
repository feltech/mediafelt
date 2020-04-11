from setuptools import setup

setup(
    name='mediafelt',
    version='1.0',
    packages=['mediafelt'],
    url='',
    license='GPL',
    author='David Feltell',
    author_email='',
    description=(
        'Parse and rename/move media files to a Kodi-compatible directory'
        ' structure'
    ),
    install_requires=[
        'guessit', 'pyyaml'
    ],
    package_data={
        'mediafelt': ["logging.yaml"]
    },
    entry_points={
        'console_scripts': [
            'mediafelt=mediafelt.main:main',
        ]
    }
)
