from mangum import Mangum

from victoria.mcp.server import build_app

_mangum = Mangum(build_app(), lifespan="auto")


def handler(event: dict, context: object) -> dict:
    return _mangum(event, context)
