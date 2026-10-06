uchrom_browser (the web browser)
================================

The web browser is the package ``uchrom-browser`` (``packages/uchrom-browser``).  Start it with
``python -m uchrom_browser STORE`` (or :func:`uchrom_browser.serve`); drive an open browser from Python
with :func:`uchrom_browser.connect`.  The HTTP API is documented in ``uchrom_browser/API.md``.

Starting a server
-----------------

.. autofunction:: uchrom_browser.serve

.. autofunction:: uchrom_browser.create_app

Driving the browser from Python
-------------------------------

.. autofunction:: uchrom_browser.connect

.. autoclass:: uchrom_browser.Workspace
   :members:

.. autoclass:: uchrom_browser.BrowserError

The data layer
--------------

.. autoclass:: uchrom_browser.DatasetStore
   :members: load, get, list
