from drsai_ui.run_ui import ui
from pathlib import Path
here = Path(__file__).parent.absolute()
import os,sys
parent_path = os.path.dirname(os.path.abspath(__file__))
appdir = os.path.join(parent_path, "tmp/drsai_ui")
os.makedirs(appdir, exist_ok=True)
db_file = Path(appdir) / "drsai_ui.db"
db_uri = f"sqlite:///{db_file.as_posix()}"
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(parent_path, ".env"), override=True)
UI_PORT = int(os.getenv("RONGZAI_UI_PORT", "8081"))

if __name__ == "__main__":
    ui(
        # reload=True,
        port=UI_PORT,
        appdir=appdir,
        database_uri=db_uri,
    )