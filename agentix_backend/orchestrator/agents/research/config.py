from pathlib import Path


def load_system_prompt():
    return (Path(__file__).parent / 'prompts/system.md').read_text(encoding='utf-8')
