# Re-export everything from agcap_platform.app so all notebooks continue to work
# unchanged (they import: from scripts.app import *)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # project root, so this file also runs as a script

from agcap_platform.app import *  # noqa: F401, F403
from agcap_platform.app import agcap_explorer, create_app, run_platform, select_language  # explicit re-export for IDE support

if __name__ == '__main__':
    # python scripts/app.py: run the platform with the newest analysis output in data/processed/input_analyzed
    run_platform(lang=select_language())
