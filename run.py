from enterprise_ai.api import create_app
from enterprise_ai.config import load_config


config = load_config()
app = create_app(config)


if __name__ == "__main__":
    app.run(host=config.app_host, port=config.app_port, debug=config.debug)

