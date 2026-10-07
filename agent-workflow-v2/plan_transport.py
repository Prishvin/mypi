"""Decode bounded literal plan JSON; never guess or repair behavioral data."""
import json

MAX_BYTES = 1048576


def unique_pairs(pairs):
    """Reject duplicate keys rather than silently discard a model-authored value."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate serialized plan key: ' + key)
        result[key] = value
    return result


def reject_constant(value):
    """JSON transport does not admit Python's nonfinite number extensions."""
    raise ValueError('Invalid JSON constant: ' + value)


def task_list(value):
    """Accept an object array or one literal JSON encoding, with bounded diagnostics."""
    encoded = isinstance(value, str)
    if encoded:
        if len(value.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Serialized tasks exceeds 1 MiB')
        try:
            value = json.loads(value, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
        except json.JSONDecodeError as error:
            excerpt = value[max(0, error.pos - 100):error.pos + 100]
            raise ValueError(f'tasks contains malformed JSON at character {error.pos} '
                             f'(line {error.lineno}, column {error.colno}): {error.msg}. '
                             f'Nearby text: {excerpt!r}. The original proposal is retained; '
                             'repair its syntax without resending the entire plan.') from None
        except RecursionError:
            raise ValueError('Serialized tasks nesting is too deep') from None
    if not isinstance(value, list) or not value:
        raise ValueError('tasks must be a nonempty array of task objects')
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f'tasks[{index}] must be an object; do not double-encode individual tasks')
    return value, encoded
