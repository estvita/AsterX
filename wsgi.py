import config
import importlib

engine_module = config.ENGINE

module_path = f"{engine_module}.app"
engine_app = importlib.import_module(module_path)

app = getattr(engine_app, 'app')

if __name__ == "__main__":
    app.run()