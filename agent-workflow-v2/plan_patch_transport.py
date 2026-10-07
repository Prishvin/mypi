"""Decode sparse plan transport strictly, reporting positions in the original value."""
import copy
import json
from plan_transport import MAX_BYTES, unique_pairs, reject_constant


def container_hint(text, position):
    """Describe a mismatched JSON closer, ignoring punctuation inside escaped strings."""
    stack=[];quoted=False;escaped=False
    for offset,char in enumerate(text[:position+1]):
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char in '()':
            return f' Unexpected {char!r} at character {offset}; JSON containers use square brackets or braces, not parentheses.'
        elif char in '[{':stack.append((char,offset))
        elif char in ']}':
            if not stack:break
            opener,start=stack[-1];expected=']' if opener=='[' else '}'
            if char!=expected:
                return f' Container opened at character {start} needs {expected!r} before {char!r} at character {offset}.'
            stack.pop()
    return ''


def malformed(field, text, error):
    """Keep the offending field, original offset and a small excerpt; never repair data."""
    start=max(0,error.pos-80);end=min(len(text),error.pos+80)
    excerpt=json.dumps(text[start:end],ensure_ascii=False)
    return ValueError(f'{field} contains malformed JSON at character {error.pos} '
                      f'(line {error.lineno}, column {error.colno}): {error.msg}.'+
                      container_hint(text,error.pos)+f' Nearby text [{start}:{end}]: {excerpt}. '
                      'No values were repaired. Send valid arrays/objects and retain all intended edits.')


def literal(text):
    """Use JSON rules rather than permissive Python number or duplicate-key handling."""
    return json.loads(text,object_pairs_hook=unique_pairs,parse_constant=reject_constant)


def decode(patch):
    """Accept exact array encodings and legacy joined parameters without guessing syntax."""
    if not isinstance(patch,dict):raise ValueError('Sparse patch must be an object')
    result=copy.deepcopy(patch);notes=[]
    for field in ('task_updates','architecture_replacements'):
        value=result.get(field)
        if not isinstance(value,str):continue
        if len(value.encode('utf-8'))>MAX_BYTES:raise ValueError(f'Serialized {field} exceeds 1 MiB')
        try:
            parsed=literal(value)
        except json.JSONDecodeError as error:
            # Only a successfully closed value followed by extra parameters can be joined.
            if error.msg!='Extra data':raise malformed(field,value,error) from None
            prefix='{"'+field+'":'
            try:joined=literal(prefix+value+'}')
            except json.JSONDecodeError as joined_error:
                original=json.JSONDecodeError(joined_error.msg,value,
                    max(0,min(len(value),joined_error.pos-len(prefix))))
                raise malformed(field,value,original) from None
            except RecursionError:raise ValueError(f'Serialized {field} nesting is too deep') from None
            if set(joined)-{field,'architecture_replacements'}:
                raise ValueError('Ambiguous serialized patch parameters')
            if (set(joined)-{field}).intersection(result):
                raise ValueError('Conflicting serialized and outer patch fields')
            result.update(joined)
        except RecursionError:raise ValueError(f'Serialized {field} nesting is too deep') from None
        else:result[field]=parsed
        notes.append('Decoded literal JSON '+field+'; no contract data changed')
    for field in ('task_updates','architecture_replacements'):
        if field not in result:continue
        value=result[field]
        if not isinstance(value,list) or any(not isinstance(item,dict) for item in value):
            raise ValueError(f'{field} must be an array containing objects; do not double-encode individual entries')
    return result,notes
