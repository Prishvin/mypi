"""Describe missing telemetry explicitly without inventing tokens or throughput."""


def request_key(value):
    """Normalize the optional server prefix while keeping exact request identity."""
    if not isinstance(value, str) or not value:
        return None
    return value.removeprefix('chatcmpl-')


def summarize(events, native):
    """Match started/completed calls and flag observed reasoning with zero usage."""
    ends = [row for row in events if row.get('type') == 'request_end']
    started = {request_key(row.get('request_id')) for row in events
               if row.get('type') in {'request_start', 'request_end'}} - {None}
    completed = {request_key(row.get('request_id')) for row in ends
                 if not row.get('partial')} - {None}
    records = {request_key(row.get('request_id')): row for row in native
               if request_key(row.get('request_id'))}
    reasoning = {request_key(row.get('request_id')) for row in events
                 if row.get('kind') == 'thinking_delta'} - {None}
    missing_reasoning = sorted({request_key(row.get('request_id')) for row in ends
                               if request_key(row.get('request_id')) in reasoning
                               and not row.get('usage', {}).get('reasoning')})
    speeds = {key for key, row in records.items() if row.get('decode_tok_s') is not None
              and not (row.get('request_cancelled') or row.get('stream_cancelled_by_client'))}
    unidentified = sum(not request_key(row.get('request_id')) for row in ends)
    missing = sorted(started - records.keys())
    return {
        'started_requests_with_ids': len(started),
        'completed_requests_with_ids': len(completed),
        'unidentified_provider_results': unidentified,
        'native_matched_requests': len(started & records.keys()),
        'native_missing_request_ids': missing,
        'native_complete': bool(started) and not missing and not unidentified,
        'completed_requests_with_decode_speed': len(completed & speeds),
        'completed_speed_coverage_complete': bool(completed) and completed <= speeds and not unidentified,
        'reasoning_usage_missing_request_ids': missing_reasoning,
        'reasoning_usage_observed_incomplete': bool(missing_reasoning),
        'note': 'Coverage is by exact request ID. Speed summaries use only available native '
                'records; missing records are unknown. Observed thinking with zero/absent '
                'reasoning usage makes the reported reasoning sum a partial count, not zero thinking. '
                'No stream-text token estimates replace backend usage.'}
