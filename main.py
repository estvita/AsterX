import configparser
import importlib
import sys

def main():
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    try:
        engine_name = config.get('app', 'engine')
    except Exception as e:
        sys.exit(f"Error reading configuration file: {e}")
    
    module_path = f"{engine_name}.engine"
    
    try:
        engine_module = importlib.import_module(module_path)
    except ImportError as e:
        sys.exit(f"Failed to import module '{module_path}': {e}")
    
    if not hasattr(engine_module, 'run'):
        sys.exit(f"Module '{module_path}' does not have 'run' function defined")
    
    engine_module.run()

if __name__ == '__main__':
    main()
