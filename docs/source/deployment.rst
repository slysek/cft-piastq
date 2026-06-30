Publishing on GitHub Pages
==========================

The repository includes a GitHub Actions workflow that builds the Sphinx site
and publishes it to GitHub Pages.

Repository settings
-------------------

In GitHub, enable Pages with this source:

* Source: ``GitHub Actions``

The workflow builds on pushes to ``main`` and can also be started manually from
the Actions tab.

Local build
-----------

Install documentation dependencies:

.. code-block:: powershell

   python -m pip install -r docs/requirements.txt

Build HTML locally:

.. code-block:: powershell

   python -m sphinx -b html docs/source docs/_build/html

Open ``docs/_build/html/index.html`` in a browser to inspect the generated site.

Generated output
----------------

The ``docs/_build`` directory is build output. It should not be committed unless
the project intentionally chooses a static-file-only publishing flow.
