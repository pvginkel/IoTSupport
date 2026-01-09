"""Development server entry point."""

import logging
import os

from waitress import serve

from app import create_app
from app.config import get_settings


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = get_settings()
    app = create_app(settings)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3201"))

    if settings.DEBUG:
        app.logger.info("Running in debug mode with Flask development server")
        app.run(host=host, port=port, debug=True)
    else:
        app.logger.info("Running in production mode with Waitress")
        serve(app, host=host, port=port, threads=4)


if __name__ == "__main__":
    main()
