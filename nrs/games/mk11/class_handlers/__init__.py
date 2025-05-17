import logging

from nrs.games.mk11.class_handlers.database import DatabaseHandler # Required to be in locals()
from nrs.ue3_common import ClassHandler


logging.getLogger("ClassHandlers").debug(f"Registering handlers")

for var in list(locals().values()): # Cast to list to avoid size change
    if isinstance(var, type) and issubclass(var, ClassHandler): # TODO: Considering making it clear the handlers first
        var.register_handlers()
