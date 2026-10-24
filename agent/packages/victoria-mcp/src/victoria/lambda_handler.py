from aws_lambda_powertools import Logger
from mangum import Mangum

from victoria.mcp.server import build_app

logger = Logger()


@logger.inject_lambda_context
def handler(event: dict, context: object) -> dict:
    return Mangum(build_app(), lifespan="auto")(event, context)
