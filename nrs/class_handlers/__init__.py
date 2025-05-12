import logging

from nrs.class_handlers.database import DatabaseHandler # Required to be in locals()
from nrs.game.PropertyTypes import ClassHandler


logging.getLogger("ClassHandlers").debug(f"Registering handlers")

for var in list(locals().values()): # Cast to list to avoid size change
    if isinstance(var, type) and issubclass(var, ClassHandler):
        var.register_handlers()