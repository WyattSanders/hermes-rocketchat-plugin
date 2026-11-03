"""Install the Hermes gateway stubs before pytest imports anything else.

The repository root is a Python package (``__init__.py`` imports the adapter),
and pytest imports that ``__init__.py`` when it sets up the package for
``tests/test_adapter.py``. The stubs therefore have to exist before collection
so the plugin package stays importable without a Hermes install.
"""

from _gateway_stubs import install_gateway_stubs

install_gateway_stubs()
