"""Summarize recorded model usage without confusing native allocation with RSS."""
import json
from pathlib import Path
from runner_process import BASE, read


def rows(path):
    """Read local JSONL evidence, ignoring incomplete final lines."""
    if not path.exists():
        return []
    result = []
    for line in path.read_text(errors='replace').splitlines():
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result


def transport_for_session(events, transport, session_name):
    """Disambiguate the early adapter's generic session ID using event times."""
    selected=[row for row in transport if str(row.get('request_id','')).startswith(session_name+'-')]
    stamps=[row['timestamp'] for row in events if isinstance(row.get('timestamp'),(int,float))]
    if session_name!='session' or not stamps:
        return selected
    def within_attempt(row):
        try:
            started=int(row['request_id'].rsplit('-',1)[-1])
            return min(stamps)-2000<=started<=max(stamps)
        except (ValueError,KeyError):
            return False
    return [row for row in selected if within_attempt(row)]


def collect(result, folder):
    """Keep backend-measured tokens/timings distinct from admission estimates."""
    session = Path(result['session']) if result.get('session') else None
    if not session:
        return {}
    provider = [r for r in rows(session / 'provider-timing.jsonl') if r.get('type') == 'request_end']
    status = read(BASE.parent / 'reports/quality-main-status.json')
    native = [r for r in rows(Path(status.get('logs', '/nonexistent')) / 'requests.jsonl')
              if session.name in str(r.get('request_id', ''))]
    if not native:
        from remote_metrics import native_for
        native = native_for(session.name)
    memory = rows(folder / 'memory.jsonl')
    verifications=rows(session/'test-timing.jsonl')
    metrics = {'requests': len(provider), 'input_tokens_sum': sum(r.get('usage', {}).get('input', 0) for r in provider),
        'cache_read_tokens_sum': sum(r.get('usage', {}).get('cacheRead', 0) for r in provider),
        'output_tokens_sum': sum(r.get('usage', {}).get('output', 0) for r in provider),
        'reasoning_tokens_sum': sum(r.get('usage', {}).get('reasoning', 0) for r in provider),
        'request_seconds': sum(r.get('wall_seconds', 0) for r in provider),
        'verifier_invocations':len(verifications),
        'failed_verifier_invocations':sum(r.get('exit_code',0)!=0 for r in verifications),
        'native_request_count':len(native),
        'native_completion_tokens_sum':sum(r.get('completion_tokens') or 0 for r in native),
        'native_cancelled_requests':sum(bool(r.get('request_cancelled') or r.get('stream_cancelled_by_client')) for r in native),
        'native_requests': [{k: r.get(k) for k in ('request_id', 'prompt_tokens', 'cached_tokens',
            'completion_tokens', 'prefill_tok_s', 'decode_tok_s', 'ttft_s', 'request_elapsed_s',
            'active_memory_bytes', 'peak_memory_bytes','new_prefill_tokens','prompt_eval_time_s','decode_elapsed_s',
            'request_effective_mtp_depth','request_enable_thinking','resolved_reasoning_effort','thinking_guard',
            'thermal_pressure','thermal_pressure_max','effective_temperature','effective_top_p','effective_top_k',
            'request_cancelled','stream_cancelled_by_client','cancellation_reason','cancellation_elapsed_s')} for r in native],
        'server_rss_peak_sampled_bytes': max((r.get('server_rss_bytes') or 0 for r in memory), default=0),
        'server_rss_available':any((r.get('server_rss_bytes') or 0)>0 for r in memory),
        'admission_estimate': read(session / 'request-budget-result.json'),
        'note': 'Provider usage counts completed requests; native completion totals also include cancelled generation. Input sums repeat context, not maximum occupancy. Native peak is shared-backend high-water allocation. RSS is sampled separately; zero with server_rss_available=false means unavailable.'}
    if not provider:
        gateway=BASE.parent/'reports/overnight-quake-20261006/gateway'
        events=rows(folder / 'pi.log')
        transport=transport_for_session(events,rows(gateway/'events.jsonl'),session.name)
        metrics['transport']=transport
        metrics['request_seconds']=sum(r.get('seconds',0) for r in transport if r.get('phase')=='finished')
        metrics['admission_estimates']=[read(p) for p in gateway.glob(session.name+'-*.budget.json')]
        messages = [r['message'] for r in events if r.get('type') == 'message_end'
                    and r.get('message', {}).get('role') == 'assistant']
        metrics.update(requests=len(messages),
            input_tokens_sum=sum(r.get('usage', {}).get('input', 0) for r in messages),
            cache_read_tokens_sum=sum(r.get('usage', {}).get('cacheRead', 0) for r in messages),
            output_tokens_sum=sum(r.get('usage', {}).get('output', 0) for r in messages))
        steps=[r['part'].get('tokens',{}) for r in events if r.get('type')=='step_finish']
        if steps:
            visible=sum(r.get('output',0) for r in steps)
            reasoning=sum(r.get('reasoning',0) for r in steps)
            metrics.update(requests=len(steps),input_tokens_sum=sum(r.get('input',0) for r in steps),
                output_tokens_sum=visible+reasoning,visible_output_tokens_sum=visible,
                reasoning_tokens_sum=reasoning,
                cache_read_tokens_sum=sum(r.get('cache',{}).get('read',0) for r in steps))
        usage=list({r['request_id']:r['usage'] for r in transport if r['phase']=='usage'}.values())
        if usage:
            total=sum(r.get('input_tokens',r.get('prompt_tokens',0)) for r in usage)
            cached=sum(r.get('input_tokens_details',r.get('prompt_tokens_details',{})).get('cached_tokens',0) for r in usage)
            generated=sum(r.get('output_tokens',r.get('completion_tokens',0)) for r in usage)
            reasoning=sum(r.get('output_tokens_details',r.get('completion_tokens_details',{})).get('reasoning_tokens',0) for r in usage)
            metrics.update(requests=len(usage),input_tokens_sum=total-cached,cache_read_tokens_sum=cached,
                output_tokens_sum=generated,reasoning_tokens_sum=reasoning,usage_source='Gateway API usage including final tool-producing response')
    return metrics
