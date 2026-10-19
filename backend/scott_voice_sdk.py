"""Pinned, qualified headless SDK profile; importing it never imports Torch."""
TORCH = '2.14.1+cu126'
TORCHAUDIO = '2.11.0+cu126'  # Stable ABI: officially supports Torch >= 2.11.
QWEN = '0.1.1+scott.1'
WHEEL = 'assets/scott-voice/vendor/qwen_tts-0.1.1+scott.1-py3-none-any.whl'
WHEEL_SHA256 = '165969d1b0774f83c9a0222f493373adddb32e5504b669cc9acc600599df5b19'
REQUIREMENTS = ('qwen-tts=='+QWEN, 'transformers==5.20.1', 'accelerate==1.15.0',
                'soundfile==0.13.1', 'scipy==1.17.1', 'numpy==2.3.4',
                'huggingface-hub==2.2.0', 'idna==3.20', 'hf-xet==1.7.0',
                'setuptools==83.0.0', 'psutil==7.2.2')
VERSIONS = dict([('torch', TORCH), ('torchaudio', TORCHAUDIO),
                 *(row.split('==', 1) for row in REQUIREMENTS)])
