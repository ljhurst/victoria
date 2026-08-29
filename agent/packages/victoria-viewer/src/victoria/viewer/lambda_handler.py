from mangum import Mangum

from victoria.viewer.app import build_app

handler = Mangum(build_app(), lifespan="off")
