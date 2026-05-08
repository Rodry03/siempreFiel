from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi.templating import Jinja2Templates

_MADRID = ZoneInfo("Europe/Madrid")


def _get_flashes(request) -> list:
    flashes = request.session.get("_flash", [])
    if flashes:
        request.session["_flash"] = []
    return flashes


def _to_madrid(dt: datetime) -> datetime:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_MADRID)


templates = Jinja2Templates(directory="app/templates")
templates.env.globals["enumerate"] = enumerate
templates.env.globals["get_flashes"] = _get_flashes
templates.env.filters["madrid"] = _to_madrid
