import os
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
try:
    from groq import Groq
except ImportError:
    Groq = None
try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None

class AIRouter:
    def __init__(self):
        self.groq_key = os.getenv('GROQ_API_KEY')
        self.hf_token = os.getenv('HF_TOKEN')
        self.groq_client = Groq(api_key=self.groq_key) if self.groq_key and Groq else None
        self.hf_client = InferenceClient(token=self.hf_token) if self.hf_token and InferenceClient else None
        self.ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        # Ollama models available locally (zero cost, no API key needed)
        self.routes = {
                            'classify': {'provider': 'ollama', 'model': 'qwen3:4b', 'fallback': {'provider': 'groq', 'model': 'mixtral-8x7b-32768'}},
                            'reason': {'provider': 'ollama', 'model': 'qwen3:4b', 'fallback': {'provider': 'groq', 'model': 'mixtral-8x7b-32768'}},
                            'code': {'provider': 'ollama', 'model': 'qwen3:4b', 'fallback': {'provider': 'groq', 'model': 'mixtral-8x7b-32768'}},
                            'vision': {'provider': 'ollama', 'model': 'qwen3-vl:4b-instruct-q4_K_M', 'fallback': {'provider': 'groq', 'model': 'mixtral-8x7b-32768'}},
                            'embedding': {'provider': 'hf', 'model': 'sentence-transformers/all-MiniLM-L6-v2'},
                        }
    def call(self, task_type: str, prompt: str, system: str = '', max_tokens: int = 2000, temperature: float = 0.3) -> str:
        route = self.routes.get(task_type, self.routes['reason'])
        provider = route['provider']
        model = route['model']
        messages = []
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': prompt})
        # Try primary provider
        result = self._call_provider(provider, model, messages, max_tokens, temperature)
        if result.startswith('ERROR:') and 'fallback' in route:
            # Try fallback
            fb = route['fallback']
            result = self._call_provider(fb['provider'], fb['model'], messages, max_tokens, temperature)
        return result
    def _call_provider(self, provider: str, model: str, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        if provider == 'groq' and self.groq_client:
            return self._call_groq(model, messages, max_tokens, temperature)
        elif provider == 'hf' and self.hf_client:
            return self._call_hf(model, messages, max_tokens, temperature)
        elif provider == 'ollama':
            return self._call_ollama(model, messages, max_tokens, temperature)
        return f'ERROR: Provider {provider} not available'
    def _call_groq(self, model: str, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        resp = self.groq_client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        return resp.choices[0].message.content
    def _call_hf(self, model: str, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        prompt = '\n'.join([f"{m['role']}: {m['content']}" for m in messages])
        resp = self.hf_client.text_generation(
            prompt, model=model, max_new_tokens=max_tokens, temperature=temperature
        )
        return resp
    def _call_ollama(self, model: str, messages: List[Dict], max_tokens: int, temperature: float) -> str:
        import requests
        # Use /api/chat for proper chat format
        try:
            resp = requests.post(f'{self.ollama_url}/api/chat', json={
                'model': model,
                'messages': messages,
                'stream': False,
                'options': {'num_predict': max_tokens, 'temperature': temperature}
            }, timeout=60)
            data = resp.json()
            if 'message' in data:
                return data['message'].get('content', 'ERROR: No content')
            return data.get('response', 'ERROR: Unexpected response')
        except requests.exceptions.ConnectionError:
            return 'ERROR: Ollama not running (connection refused)'
        except Exception as e:
            return f'ERROR: {e}'

_router = None
def get_router() -> AIRouter:
    global _router
    if _router is None:
        _router = AIRouter()
    return _router

def ai_classify(prompt: str) -> str:
    return get_router().call('classify', prompt, 'Classify the input. Return only the category.')

def ai_reason(prompt: str, system: str = '') -> str:
    return get_router().call('reason', prompt, system or 'Think step by step. Be concise.')

def ai_code(prompt: str) -> str:
    return get_router().call('code', prompt, 'Write clean, production-ready Python. No markdown.')