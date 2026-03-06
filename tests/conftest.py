import sys
from pathlib import Path

# Ensure repo root is importable so tests can import top-level tools under ./scripts
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
