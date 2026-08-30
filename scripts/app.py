# Re-export everything from agcap_platform.app so all notebooks continue to work
# unchanged (they import: from scripts.app import *)
from agcap_platform.app import *  # noqa: F401, F403
from agcap_platform.app import agcap_explorer, create_app  # explicit re-export for IDE support
