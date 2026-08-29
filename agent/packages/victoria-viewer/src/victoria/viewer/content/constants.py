from pathlib import Path

from starlette.templating import Jinja2Templates

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
