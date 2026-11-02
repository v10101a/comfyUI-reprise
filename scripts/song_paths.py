"""Keep generated singing takes with the song that owns them."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def singing_output_root(name: str, audio: str | Path = '') -> Path:
    context = f'{name} {audio}'.lower()
    if 'playboi' in context or name.startswith('pb_') or '_pb_' in name:
        return ROOT / 'outputs/songs/playboi/singing'
    if 'so-i-die' in context or name.startswith('sid_') or '_sid_' in name:
        return ROOT / 'outputs/songs/so-i-die/singing'
    raise ValueError(f'Cannot infer the song for {name!r}; supply --out explicitly')
