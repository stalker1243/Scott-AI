"""Request limits for reasoning models, shared by voice and saved chats."""
import re


def openai_options(model, tokens, temperature=None):
    modern = bool(re.match(r'^(gpt-[56](?:[.\-]|$)|o[134](?:[\-]|$))', model))
    if modern:
        # Reasoning consumes the same limit as visible text. Legacy max_tokens
        # and sampling controls are not supported by several of these models.
        options = dict(max_completion_tokens=max(8192, tokens))
        if model.startswith('gpt-6'):
            options['reasoning_effort'] = 'none' if model.startswith('gpt-6-luna') else 'low'
        return options
    options = dict(max_tokens=tokens)
    if temperature is not None:
        options.update(temperature=temperature, top_p=0.95,
                       presence_penalty=0.0, frequency_penalty=0.0)
    return options


def anthropic_options(model, tokens, temperature=None):
    modern = bool(re.match(r'^claude-(?:(?:sonnet|opus|haiku)-5-5|fable-5-1)(?:-|$)', model))
    options = dict(max_tokens=max(8192, tokens) if modern else tokens)
    if temperature is not None and not modern:
        options['temperature'] = temperature
    return options


def deepseek_options(model, tokens, temperature=None):
    if model in {'deepseek-flash', 'deepseek-v4-pro'}:
        return dict(max_tokens=max(8192, tokens), reasoning_effort='low')
    options = dict(max_tokens=tokens)
    if temperature is not None:
        options['temperature'] = temperature
    return options
