"""Fetch bounded native telemetry for this client's request IDs, without local PIDs."""
import server_config


def native_for(identity: str) -> list[dict]:
    """Use native decode speed/allocation; never invent throughput from wall time."""
    try:
        metrics = server_config.get('/metrics', timeout=2)
        recent = metrics.get('recent', [])[-32:]
        if metrics.get('latest'):
            recent = recent + [metrics['latest']]
        selected = {row['request_id']: row for row in recent
                    if identity in str(row.get('request_id', ''))}
        return list(selected.values())
    except (OSError, ValueError, KeyError):
        return []
