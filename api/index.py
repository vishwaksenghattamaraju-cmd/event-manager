import os
import sys
from pathlib import Path

# Add root directory to sys.path so backend package can be resolved
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from wsgi import app
