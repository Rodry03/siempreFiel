from fastapi.templating import Jinja2Templates


def _get_flashes(request) -> list:
    flashes = request.session.get("_flash", [])
    if flashes:
        request.session["_flash"] = []
    return flashes


templates = Jinja2Templates(directory="app/templates")
templates.env.globals["enumerate"] = enumerate
templates.env.globals["get_flashes"] = _get_flashes
