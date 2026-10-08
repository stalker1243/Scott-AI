"""Current catalog and request contracts; no provider calls or real keys."""
from types import SimpleNamespace
import pytest
import intelligent_answerer as ia
import model_capabilities
import model_requests
import chat_endpoints

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('provider,model,images', [
    ('OpenAI', 'gpt-6.1-sol', True),
    ('OpenAI', 'gpt-6-astra', True),
    ('OpenAI', 'gpt-6-luna', True),
    ('Anthropic', 'claude-sonnet-5-5', True),
    ('Anthropic', 'claude-opus-5-5', True),
    ('Anthropic', 'claude-haiku-5-5', True),
    ('Anthropic', 'claude-fable-5-1', True),
    ('DeepSeek', 'deepseek-flash', True),
    ('DeepSeek', 'deepseek-v4-pro', False),
])
def test_current_models_are_selectable_with_capabilities(provider, model, images):
    assert model in {row['id'] for row in ia.STATIC_PROVIDER_MODELS[provider]}
    caps = model_capabilities.capabilities(provider, model)
    assert caps['known'] and caps['text'] and caps['documents']
    assert caps['images'] is images
    assert not caps['video'] and not caps['image_generation']


@pytest.mark.parametrize('model', ['gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-luna'])
def test_saved_chat_sends_current_openai_parameters(model):
    calls = []
    def create(**args):
        calls.append(args)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='answer'))])
    answerer = SimpleNamespace(api_provider='OpenAI', model=model, max_tokens=1000,
                               client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    assert chat_endpoints.complete(answerer, [dict(role='user', content='question')], 'instructions') == 'answer'
    request = calls[0]
    assert request['model'] == model
    assert request['max_completion_tokens'] >= 8192
    assert request['reasoning_effort'] == ('none' if model == 'gpt-6-luna' else 'low')
    assert not {'max_tokens', 'temperature', 'top_p', 'presence_penalty', 'frequency_penalty'} & request.keys()
    assert request['messages'][-1]['content'] == 'question'


def test_legacy_models_keep_their_limits_and_sampling():
    assert model_requests.openai_options('gpt-4o', 1000, 0.7)['max_tokens'] == 1000
    assert model_requests.anthropic_options('claude-sonnet-4', 1000, 0.7) == dict(max_tokens=1000, temperature=0.7)
    assert model_requests.deepseek_options('deepseek-chat', 1000, 0.7) == dict(max_tokens=1000, temperature=0.7)


@pytest.mark.parametrize('model', ['claude-sonnet-5-5', 'claude-opus-5-5', 'claude-haiku-5-5', 'claude-fable-5-1'])
def test_current_claude_omits_unsupported_temperature(model):
    options = model_requests.anthropic_options(model, 1000, 0.7)
    assert options == dict(max_tokens=8192)


@pytest.mark.parametrize('model', ['deepseek-flash', 'deepseek-v4-pro'])
def test_current_deepseek_has_budget_for_thinking(model):
    assert model_requests.deepseek_options(model, 1000, 0.7) == dict(max_tokens=8192, reasoning_effort='low')
