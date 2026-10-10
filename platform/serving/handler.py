"""AWS Lambda entry point for the serving template.

API Gateway (HTTP type) invokes this handler, and Mangum passes each request to
the FastAPI app in app.py.
"""

from mangum import Mangum

from app import app

handler = Mangum(app, lifespan="off")
