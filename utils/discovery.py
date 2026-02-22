import os
import importlib.util
import inspect

def get_available_connectors(logger):
    """
    Scans the connectors/ directory and returns a map of {slug: connector_class}.
    """
    connectors = {}
    connectors_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'connectors')
    
    if not os.path.exists(connectors_dir):
        logger.error(f"Connectors directory not found: {connectors_dir}")
        return connectors

    for filename in os.listdir(connectors_dir):
        if filename.endswith('.py') and not filename.startswith('__'):
            module_name = filename[:-3]
            module_path = os.path.join(connectors_dir, filename)
            
            try:
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Find classes in the module that have DISPLAY_NAME and SLUG
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and hasattr(obj, 'SLUG') and hasattr(obj, 'DISPLAY_NAME'):
                        connectors[obj.SLUG] = obj
            except Exception as e:
                logger.error(f"Error loading connector {module_name}: {e}")
                
    return connectors
