"""
Скрипт для установки команды 'maltruand' в систему.
"""
from setuptools import setup

setup(
    name="maltruand",
    version="0.1.0",
    description="Мальтруант - Голосовой ассистент с искусственным интеллектом",
    py_modules=["maltruand"],
    entry_points={
        "console_scripts": [
            "maltruand=maltruand:main",
        ],
    },
    python_requires=">=3.10",
)

