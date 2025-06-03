import functools
import logging
import collections
import time


def is_iterable(x):
    """Returns true if a function is a non-string iterable."""
    if isinstance(x, collections.Iterable) \
            and not isinstance(x, str):
        return True
    return False


def benchmark(func):
    """Decorator that prints the time a function takes to execute."""

    @functools.wraps(func)
    def decorator(*args, **kwargs):
        t = time.clock()
        ret = func(*args, **kwargs)
        logging.info("%s took %.3f us" % (func.__name__, (time.clock() - t) * 1e6))
        return ret

    return decorator


def trace(func):
    """Decorator to print arguments to called function and the return value."""

    @functools.wraps(func)
    def decorator(*args, **kwargs):
        logging.debug("%s(%s, %s)" % (func.__name__, args, kwargs))
        ret = func(*args, **kwargs)
        logging.debug("%s returned %s" % (func.__name__, ret))
        return ret

    return decorator


def nop(func):
    """Non-decorator (does nothing).

    Can be used to disable a decorator by importing with "as".
    For example, to use traces:
    from decorators import trace
    But to then disable traces without actually removing them, use instead:
    from decorators import nop as trace
    """
    return func
