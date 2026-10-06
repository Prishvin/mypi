"""Share the executor's nonblocking project lock with knowledge publication."""
from contextlib import contextmanager
import fcntl
import hashlib


@contextmanager
def exclusive(root, base):
    """Refuse a concurrent source runner instead of changing its frozen snapshot."""
    folder = base/'runner-locks'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/(hashlib.sha256(str(root.resolve()).encode()).hexdigest()+'.lock')
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A project runner or knowledge update is active; retry after it stops')
        yield
