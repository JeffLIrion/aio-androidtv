from setuptools import setup

with open('README.rst') as f:
    readme = f.read()

setup(
    name='aio_androidtv',
    version='0.0.3',
    description='Communicate with an Android TV or Fire TV device via ADB over a network.',
    long_description=readme,
    keywords=['adb', 'android', 'androidtv', 'firetv'],
    url='https://github.com/JeffLIrion/aio-androidtv/',
    license='MIT',
    author='Jeff Irion',
    author_email='jefflirion@users.noreply.github.com',
    packages=['aio_androidtv'],
    install_requires=['aio-adb-shell'],
    python_requires='>=3.7',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
    ],
    test_suite='tests'
)
