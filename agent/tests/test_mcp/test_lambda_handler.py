import subprocess
import sys


def test_cold_start_does_not_import_anthropic():
    """The Anthropic SDK costs about a second of Lambda init, so only the
    tools that call the model should load it. Runs in a fresh interpreter
    because this test process has already imported it elsewhere."""
    code = "import sys, victoria.lambda_handler; sys.exit('anthropic' in sys.modules)"

    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr or "anthropic was imported at startup"
