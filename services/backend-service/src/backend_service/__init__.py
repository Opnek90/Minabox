"""Minabox Backend Service.

Central orchestration and data management service for the Minabox project.
Provides REST API, WebSocket support, MQTT integration, and database management.
"""

from shared_lib.version import get_version

#: Read from the VERSION file rather than written here: this used to say 0.1.0
#: while VERSION said something else entirely, and it is what the API and the
#: OpenAPI page report about themselves.
__version__ = get_version()
