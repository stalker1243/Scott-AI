"""Conservative per-model capabilities. OpenRouter supplies live modalities."""
import threading
import time

_catalog = {}
_updated = 0.0
_lock = threading.RLock()


def remember_openrouter(rows):
    global _updated
    with _lock:
        _catalog.clear()
        _catalog.update({row['id']: row['capabilities'] for row in rows
                         if row.get('capabilities')})
        _updated = time.monotonic()


def capabilities(provider, model, architecture=None, refresh=False):
    result = dict(known=True, text=True, documents=True, images=False,
                  video=False, image_generation=False, source='documented')
    if architecture is not None:
        inputs = architecture.get('input_modalities', [])
        outputs = architecture.get('output_modalities', [])
        if not inputs or not outputs:
            modality = architecture.get('modality', '')
            if '->' in modality:
                left, right = modality.split('->', 1)
                inputs, outputs = left.split('+'), right.split('+')
        return dict(known=bool(inputs and outputs), text='text' in outputs,
                    documents='text' in inputs and 'text' in outputs,
                    images='image' in inputs and 'text' in outputs,
                    video='video' in inputs and 'text' in outputs,
                    image_generation='image' in outputs, source='catalog')
    name = (model or '').lower()
    if provider == 'OpenRouter':
        with _lock:
            stale = time.monotonic() - _updated > 600
        if refresh and stale:
            try:
                from .intelligent_answerer import list_openrouter_models
            except ImportError:
                from intelligent_answerer import list_openrouter_models
            list_openrouter_models()
        with _lock:
            return dict(_catalog.get(model) or dict(result, known=False, source='unknown'))
    if provider == 'OpenAI':
        if name.startswith('gpt-image-') or name == 'chatgpt-image-latest':
            return dict(result, text=False, documents=False, image_generation=True)
        result['images'] = name.startswith(('gpt-4o', 'gpt-4.1', 'gpt-5', 'gpt-6', 'o3', 'o4-mini')) or name == 'gpt-4-turbo'
        result['known'] = result['images'] or name.startswith(('gpt-3.5', 'gpt-4', 'o1'))
    elif provider == 'Anthropic':
        result['images'] = name.startswith(('claude-3', 'claude-sonnet-4', 'claude-opus-4', 'claude-haiku-4',
                                           'claude-sonnet-5', 'claude-opus-5', 'claude-haiku-5', 'claude-fable-5'))
        result['known'] = result['images']
    elif provider == 'Groq':
        result['images'] = name == 'qwen/qwen3.8-27b' or 'llama-4-scout' in name or 'llama-4-maverick' in name
        result['known'] = result['images'] or name.startswith(('llama-', 'qwen/', 'openai/gpt-oss-', 'moonshotai/')) or name in {'groq/compound', 'groq/compound-mini'}
        if name == 'qwen/qwen3.8-27b':
            result['max_images'] = 3
    elif provider == 'DeepSeek':
        result['known'] = name in {'deepseek-chat', 'deepseek-reasoner', 'deepseek-flash', 'deepseek-v4-pro'}
        result['images'] = name == 'deepseek-flash'
    else:
        result['known'] = False
    if not result['known']:
        result['source'] = 'unknown'
    return result
