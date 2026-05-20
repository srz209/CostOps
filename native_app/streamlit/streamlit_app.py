from pathlib import Path
import os
import sys


os.environ["COSTOPS_NATIVE_APP"] = "1"

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

shared_entrypoint = ROOT / "app" / "streamlit_app.py"
exec(compile(shared_entrypoint.read_text(), str(shared_entrypoint), "exec"), globals())
