"""Test environment: temp DB, no AI key (offline mode), deterministic bank and date."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="finpilot-test-")
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["MOCK_BANK_FAILURE_RATE"] = "0"
os.environ["DEMO_TODAY"] = "2026-11-21"
