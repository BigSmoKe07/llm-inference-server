"""
Stub out heavy optional dependencies that are not installed in the test
environment (transformers / torch) so that unit tests can import
worker.inference without requiring those packages.
"""
import sys
from unittest.mock import MagicMock

# Only stub if not already present (avoids overwriting a real install).
if "transformers" not in sys.modules:
    sys.modules["transformers"] = MagicMock()
