from mangum import Mangum

from victoria.mcp.server import build_app


def handler(event: dict, context: object) -> dict:
    return Mangum(build_app(), lifespan="auto")(event, context)
