import logging

from mk_utils.nrs.games.mk11.class_handlers.database import DatabaseHandler as MK11DatabaseHandler # Required to be in locals()
from mk_utils.nrs.ue3_common import ClassHandler


logging.getLogger("ClassHandlers").debug(f"Registering handlers")

for var in list(locals().values()): # Cast to list to avoid size change
    if isinstance(var, type) and issubclass(var, ClassHandler): # TODO: Considering making it clear the handlers first
        var.register_handlers()
