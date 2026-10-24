from aws_lambda_powertools import Logger
from mangum import Mangum

from victoria.viewer.app import build_app

logger = Logger()
_mangum = Mangum(build_app(), lifespan="off")


@logger.inject_lambda_context
def handler(event: dict, context: object) -> dict:
    return _mangum(event, context)
