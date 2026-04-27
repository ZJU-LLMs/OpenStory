import inspect
from typing import Any, Callable, List, Dict
from functools import wraps


def AgentCall(func: Callable) -> Callable:
    """
    Decorator: marks a method that can be called by an agent.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    # Add metadata marker
    wrapper._is_agent_call = True
    wrapper._original_func = func
    return wrapper


def prepare_with_metadata(plugin_instance: Any, annotation_type: str) -> List[Dict[str, Any]]:
    """
    Extract methods with specified annotation type and their metadata from the plugin.

    Args:
        plugin_instance: The plugin instance
        annotation_type: The annotation type (e.g., "AgentCall")

    Returns:
        List[Dict[str, Any]]: A list of method information dictionaries
    """
    methods = []

    for name, method in inspect.getmembers(plugin_instance, predicate=inspect.ismethod):
        # Check if the method has the _is_agent_call marker
        if hasattr(method, '_is_agent_call') and method._is_agent_call:
            # Get the method signature
            sig = inspect.signature(method)

            # Build method info
            method_info = {
                "name": name,
                "method": method,
                "signature": sig,
                "parameters": {
                    param_name: {
                        "annotation": param.annotation,
                        "default": param.default if param.default != inspect.Parameter.empty else None
                    }
                    for param_name, param in sig.parameters.items()
                },
                "doc": inspect.getdoc(method) or ""
            }
            methods.append(method_info)

    return methods
