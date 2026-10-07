"""Provider-specific planning budgets; these do not enlarge local coding contracts."""
CLOUD_MODEL_CONTEXT=1050000
CLOUD_MODEL_OUTPUT=128000
CLOUD_WINDOW=272000 # Conservative installed Pi catalog window, not a claim about account entitlement.
CLOUD_INPUT=196608
CLOUD_OUTPUT=32768


def limits(provider,stage='review'):
    """Keep request packets smaller than admission caps, reserving schema and tool history."""
    if provider=='chatgpt':
        return {'context':CLOUD_WINDOW,'input':CLOUD_INPUT,'output':CLOUD_OUTPUT,
                'packet':120000,'shadow':131072,'reasoning':'xhigh'}
    # 32k packet leaves room for the tool/system envelope inside the 57k admission
    # budget. Even recovery's 32k output plus 8k reserve fits the 96k model window.
    return {'context':98304,'input':57344,'output':32768 if stage=='recovery' else 16384,'packet':32768,
            'shadow':32768,'reasoning':'medium'}


def arguments(provider,stage='review'):
    """Apply the same capacity/input/output settings to each isolated planning phase."""
    budget=limits(provider,stage)
    result=['--context',str(budget['context']),'--input-tokens',str(budget['input']),
            '--output-tokens',str(budget['output']),'--reasoning',budget['reasoning']]
    return result+(['--reasoning-budget','1024'] if provider=='qwen' else [])
