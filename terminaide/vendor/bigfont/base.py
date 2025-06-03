import logging


class BaseObject(object):
    """Ancestor class for all other classes."""

    def __init__(self, *args, **kwargs):
        super(BaseObject, self).__init__()

        if args or kwargs:
            logging.debug("%s has unused parameters %s, %s"
                          % (self, args, kwargs))
