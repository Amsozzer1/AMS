"""infra.http — the HTTP adapter: the app assembly (``app.py``) and its shared wire shapes.

Deliberately empty of imports. ``app.py`` imports ``amsx.routes``, and the routes import
``amsx.system.infra.http.view`` — if this module pulled in ``app`` those two would form an
import cycle. Import ``create_app`` from ``amsx.system.infra.http.app``.
"""
