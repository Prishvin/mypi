"""Request-local thinking caps for the privately launched, pinned MTPLX server."""
from dataclasses import replace
from functools import wraps

FIELD = 'pi_thinking_cap'
VERSION = 1


def install(module):
    """Wrap native policy resolution without modifying shared args or environment."""
    original_observe = module._request_observability
    original_guard = module._thinking_guard_config_for_request
    original_app = module.create_app

    @wraps(original_observe)
    def observe(request, **kwargs):
        metadata = kwargs.get('metadata', {})
        result = original_observe(request, **kwargs)
        if FIELD not in metadata:
            return result
        cap = metadata[FIELD]
        output = module._request_max_tokens(request)
        if (metadata.get('client') != 'pi' or type(cap) is not int or
                not 0 <= cap <= 30720 or type(output) is not int or cap > output - 2048):
            raise module.HTTPException(status_code=400, detail='Invalid Pi thinking cap or insufficient output reserve')
        result[FIELD] = cap
        return result

    @wraps(original_guard)
    def guard(state, *, prompt_ids, request_observability):
        config = original_guard(state, prompt_ids=prompt_ids, request_observability=request_observability)
        obs = request_observability or {}
        if FIELD not in obs or not obs.get('request_enable_thinking'):
            return config
        if obs[FIELD] == 0:
            return None  # Uncapped reasoning; the total response cap still applies.
        if config is None or not config.enabled:
            raise RuntimeError('Pi thinking cap requires an enabled native Qwen thinking guard')
        return replace(config, budget_tokens=obs[FIELD])

    @wraps(original_app)
    def create_app(state):
        app = original_app(state)

        @app.get('/pi-workflow/capabilities')
        def capabilities():
            return {'version': VERSION, 'thinking_cap': 'request-local',
                    'field': FIELD, 'maximum': 30720, 'zero': 'uncapped'}

        return app

    module._request_observability = observe
    module._thinking_guard_config_for_request = guard
    module.create_app = create_app
