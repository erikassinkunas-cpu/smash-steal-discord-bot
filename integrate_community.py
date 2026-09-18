"""Deterministic build integration. Only insert the extension before Client.run.

The legacy bot.py remains the upstream source. Railway runs this during its
build, followed by tests. No secrets, Discord calls or database writes occur.
"""
import ast
from pathlib import Path

ANCHOR = 'bot.run(TOKEN, log_handler=None)'
REPLACEMENT = '''# SAS extensions integration
from community import install_community
from moderation_v2 import install_moderation
install_community(globals())
install_moderation(globals())
bot.run(TOKEN)
'''


def integrate(source):
    if REPLACEMENT.strip() in source:
        return source
    if source.count(ANCHOR) != 1:
        raise ValueError('Expected exactly one legacy startup call; refusing to patch.')
    parsed = ast.parse(source)
    last = parsed.body[-1]
    if not (isinstance(last, ast.Expr) and isinstance(last.value, ast.Call)
            and isinstance(last.value.func, ast.Attribute)
            and isinstance(last.value.func.value, ast.Name)
            and last.value.func.value.id == 'bot' and last.value.func.attr == 'run'):
        raise ValueError('The legacy startup call is not the final statement.')
    result = source.replace(ANCHOR, REPLACEMENT)
    ast.parse(result)
    return result


if __name__ == '__main__':
    path = Path(__file__).with_name('bot.py')
    path.write_text(integrate(path.read_text(encoding='utf-8')), encoding='utf-8')
    print('SAS EXTENSIONS BUILD INTEGRATION OK', flush=True)
