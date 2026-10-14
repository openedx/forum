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

*

[0.2.1]
*******

Security
--------

* The forum HTTP API under ``/forum/api/v1/`` and ``/forum/api/v2/`` is no
  longer routed unless ``FORUM_ENABLE_HTTP_API`` is set to ``True``, and when
  routed it only accepts callers authenticated as a staff account. See
  `GHSA-c6fp-f54c-6cv4
  <https://github.com/openedx/forum/security/advisories/GHSA-c6fp-f54c-6cv4>`_.

0.1.0 – 2024-11-12
******************

* First release on PyPI.
