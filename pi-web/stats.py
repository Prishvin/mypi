"""Keep per-phase measured usage separate from request limits and context capacity."""

def aggregate(attempts):
    """Sum recorded work, without counting cached completed-run replays again."""
    result={key:0 for key in ['requests','input_tokens_sum','output_tokens_sum','cache_read_tokens_sum','request_seconds','wall_seconds','server_rss_peak_sampled_bytes']}
    result['native_requests']=[]
    for attempt in attempts:
        metric=attempt.get('metrics',{})
        for key in ['requests','input_tokens_sum','output_tokens_sum','cache_read_tokens_sum','request_seconds']:
            result[key]+=metric.get(key,0) or 0
        result['wall_seconds']+=attempt.get('wall_seconds',0) or 0
        result['server_rss_peak_sampled_bytes']=max(result['server_rss_peak_sampled_bytes'],metric.get('server_rss_peak_sampled_bytes',0) or 0)
        result['native_requests'].extend(metric.get('native_requests',[]))
    return result
