Change Log
##########

..
   All enhancements and patches to forum will be documented
   in this file.  It adheres to the structure of https://keepachangelog.com/ ,
   but in reStructuredText instead of Markdown (for ease of incorporation into
   Sphinx documentation and the PyPI description).

   This project adheres to Semantic Versioning (https://semver.org/).

.. There should always be an "Unreleased" section for changes pending release.

Unreleased
**********

* Add support for Typesense as the search backend.

[0.4.0] – 2026-03-12
*********************

Breaking Changes
----------------

* Drop Python 3.11 support; Python 3.12 is now required.
* Upgrade typesense-python from 1.x to 2.0. This release requires
  **Typesense Server >= v30.0** (previously >= v28.0). See the
  `typesense-python compatibility table
  <https://github.com/typesense/typesense-python#compatibility>`_
  for details. If you are running an older Typesense server you must
  upgrade it before deploying this version of openedx-forum.

0.3.4 – 2025-08-13
******************

Added
-----

* CI check to validate the Python package.

Fixed
-----

* CHANGELOG header formatting.

0.3.3 – 2025-08-12
******************

Fixed
-----

* Do not raise runtime errors if an incorrect course ID is provided when
  checking if the MySQL backend is enabled.


0.3.0 – 2025-04-23
******************

* Add support for django 5.2

*

0.1.0 – 2024-11-12
******************

* First release on PyPI.
