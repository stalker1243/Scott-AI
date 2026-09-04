#!/usr/bin/env python
# -*- coding: utf-8 -*-
import requests
import json

tests = ['привет', 'привет!', 'Привет', 'как дела', 'привет, Scott', 'hello']

print("\n✅ Testing greeting routing:\n")
for test_input in tests:
    response = requests.post('http://localhost:8000/ask', json={'question': test_input})
    data = response.json()['data']
    response_text = data.get('answer', '')[:50]
    print(f'Input: "{test_input:20}" | Type: {data.get("type"):10} | Answer: {response_text}...')

print("\n✅ All tests completed!")
