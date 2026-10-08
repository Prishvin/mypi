"""Sample backend memory without equating allocation, physical footprint and RSS."""
import time
import server_config
from remote_metrics import snapshot

FIELDS = ('active_memory_bytes', 'peak_memory_bytes', 'cache_memory_bytes',
          'phys_footprint_bytes', 'model_weights_bytes', 'session_bank_bytes',
          'generation_working_bytes', 'host_overhang_bytes')


def sizes(value):
    """Retain only known nonnegative byte counts; no prompts or PID assumptions."""
    if not isinstance(value, dict):
        return {}
    return {k: v for k, v in value.items() if k in FIELDS and type(v) is int and v >= 0}


def sample():
    """Use health RSS when provided; obtain current native counters independently."""
    row = {'epoch': time.time(), 'server_rss_bytes': None, 'native_memory': {}}
    try:
        health = server_config.get('/health', timeout=2)
        rss = health.get('server_rss_bytes')
        if type(rss) is int and rss >= 0:
            row['server_rss_bytes'] = rss
        row['native_memory'] = sizes(health)
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        row['native_memory'].update(sizes(snapshot().get('mem')))
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return row


def summarize(rows):
    """Report attempt-local sampled maxima; absent measurements remain unknown."""
    result = {'memory_sample_count': len(rows)}
    for source, key in [('phys_footprint_bytes', 'server_phys_footprint'),
                        ('active_memory_bytes', 'active_allocation')]:
        values = [sizes(row.get('native_memory')).get(source) for row in rows]
        values = [value for value in values if value is not None]
        result[key + '_peak_sampled_bytes'] = max(values, default=None)
        result[key + '_samples'] = len(values)
    return result
