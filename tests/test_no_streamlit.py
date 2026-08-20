"""Guard: the web dashboard server must not depend on Streamlit.

Running the dashboard data path should never import the legacy Streamlit
stack. This runs in a fresh interpreter so a previously imported `streamlit`
from another test cannot produce a false pass.
"""
import subprocess
import sys


def test_dashboard_imports_without_streamlit():
    code = (
        "import sys\n"
        "import modules.dashboard_api as d\n"  # import the full data path
        "import modules.financial, modules.database\n"
        "assert 'streamlit' not in sys.modules, 'streamlit leaked into dashboard imports'\n"
        "print('OK no streamlit')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=".",
        capture_output=True,
        text=True,
        env={**__import__("os").environ},
    )
    assert result.returncode == 0, (
        f"dashboard imported streamlit or failed:\n{result.stdout}\n{result.stderr}"
    )
