import inspect
from typing import Any, Callable, List, Dict
from functools import wraps


def AgentCall(func: Callable) -> Callable:
    """
    装饰器：标记可以被智能体调用的方法
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    # 添加元数据标记
    wrapper._is_agent_call = True
    wrapper._original_func = func
    return wrapper


def prepare_with_metadata(plugin_instance: Any, annotation_type: str) -> List[Dict[str, Any]]:
    """
    提取插件中带有指定注解类型的方法及其元数据

    Args:
        plugin_instance: 插件实例
        annotation_type: 注解类型（如 "AgentCall"）

    Returns:
        List[Dict[str, Any]]: 方法信息列表
    """
    methods = []

    for name, method in inspect.getmembers(plugin_instance, predicate=inspect.ismethod):
        # 检查方法是否有 _is_agent_call 标记
        if hasattr(method, '_is_agent_call') and method._is_agent_call:
            # 获取方法签名
            sig = inspect.signature(method)

            # 构建方法信息
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
