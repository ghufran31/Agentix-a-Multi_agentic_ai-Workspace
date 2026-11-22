from pathlib import Path

PROMPT_PATH = Path(__file__).with_name('prompts') / 'system.md'

def load_system_prompt():
    return PROMPT_PATH.read_text(encoding='utf-8').strip()
