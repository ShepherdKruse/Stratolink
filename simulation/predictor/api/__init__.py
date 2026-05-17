"""FastAPI app for the Stratolink trajectory predictor."""

from predictor.api.predict import app, create_app

__all__ = ["app", "create_app"]
