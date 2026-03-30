import importlib
import pkgutil
import logging
from typing import Dict, Type, Optional, List

from .base import Task

logger = logging.getLogger(__name__)

class TaskRegistry:
    _tasks: Dict[str, Type[Task]] = {}
    
    @classmethod
    def register(cls, task_class: Type[Task]):
        """Register a task class"""
        cls._tasks[task_class.name] = task_class
        return task_class
    
    @classmethod
    def get_task(cls, name: str) -> Optional[Type[Task]]:
        """Get a task class by name"""
        return cls._tasks.get(name)
    
    @classmethod
    def list_tasks(cls) -> List[str]:
        """List all registered task names"""
        return list(cls._tasks.keys())

def load_tasks():
    """Dynamically load all task modules and register their tasks"""
    import tasks  # Import the tasks package itself
    package = tasks.__package__ or tasks.__name__

    # Iterate through all modules in the tasks package
    for _, module_name, _ in pkgutil.iter_modules(tasks.__path__):
        if module_name != 'base':  # Skip the base module
            try:
                module = importlib.import_module(f"{package}.{module_name}")
                # Look for Task subclasses in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, Task) and 
                        attr != Task):  # Skip the base Task class
                        TaskRegistry.register(attr)
                        logger.debug(f"Registered task: {attr.name}")
            except Exception as e:
                logger.error(f"Error loading task module {module_name}: {e}")

# Load all tasks when the package is imported
load_tasks() 