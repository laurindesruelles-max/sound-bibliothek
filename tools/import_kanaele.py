#!/usr/bin/env python3
"""Einmaliger Import der Effekte aus den Kanal-Repos (19.11.2026). Lizenz je Datei aus der SOUNDS.md des Repos.
Die Originale bleiben in den Kanal-Repos (dort laufen die Engines weiter); hier liegt die gemeinsame Kopie.

  python3 tools/import_kanaele.py /home/claude   # Ordner, in dem die Kanal-Repos liegen
"""
import glob, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sk

REPOS = {  # Repo-Ordner, Unterordner, Standardlizenz laut Kopf der SOUNDS.md
    'goldsmith': ('goldsmith-pipeline', 'assets/sfx', 'CC0'),
    'goldsmith-laurin': ('goldsmith-pipeline', 'sound-library', None),
    'meisterwerk': ('meisterwerk-', 'assets/sfx', 'CC0'),
    'unterbau': ('unterbau-pipeline', 'assets/sfx', None),
    'denkmuster': ('denkmuster-pipeline', 'assets/sfx', 'CC0'),
    'nachtausgabe': ('nachtausgabe-pipeline', 'assets/sfx', 'CC0'),
}


def table(md):
    rows = {}
    for line in open(md, encoding='utf-8'):
        c = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(c) >= 2 and c[0] and not set(c[0]) <= set('-: ') and c[0].lower() not in ('name',):
            rows[c[0].strip('`')] = ' | '.join(c[1:])
    return rows


def lic_for(name, row, default):
    r = (row or '').lower()
    if 'youtube' in r or 'no copyright' in r:
        return None, 'YouTube/„No Copyright“ – Lizenz nicht belegbar'
    if 'higgsfield' in r or 'mirelo' in r or 'elevenlabs' in r:
        return 'Higgsfield', ''
    if 'mixkit' in r:
        return 'Mixkit Free', ''
    if 'cc0' in r or 'sfxmint' in r or 'sfx kit' in r or 'hugging face' in r:
        return 'CC0', ''
    if default:
        return default, ''
    if 'laurin' in r or 'sammlung' in r or 'geschickt' in r:
        return 'Laurin', ''
    return None, 'keine Herkunft in SOUNDS.md'


def main(base):
    skipped = []
    for origin, (repo, sub, default) in REPOS.items():
        d = os.path.join(base, repo, sub)
        md = next((p for p in (os.path.join(d, 'SOUNDS.md'), os.path.join(d, 'README.md')) if os.path.exists(p)), None)
        rows = table(md) if md else {}
        files = sorted(f for f in glob.glob(os.path.join(d, '*')) if f.lower().endswith(('.wav', '.mp3', '.ogg')))
        print(f'== {origin}: {len(files)} Dateien')
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            lic, why = lic_for(name, rows.get(name), default)
            if not lic:
                skipped.append(f'{origin}/{name}: {why}')
                continue
            src = rows.get(name, f'{repo}/{sub} (Standard laut SOUNDS.md)')
            try:
                sk.ingest([f], f'{repo}: {src[:160]}', lic, origin=origin.split('-')[0], names=[name])
            except Exception as ex:
                skipped.append(f'{origin}/{name}: Datei defekt ({str(ex)[-60:]})')
                for leftover in glob.glob(os.path.join(sk.SFX, re.sub(r'[^a-z0-9_]+', '_', name.lower()) + '*.wav')):
                    if not any(e['file'].endswith(os.path.basename(leftover)) for e in sk.catalog()):
                        os.remove(leftover)
    print('\nNicht übernommen:\n' + '\n'.join(skipped))
    open(os.path.join(sk.ROOT, 'NICHT_UEBERNOMMEN.md'), 'w').write(
        '# Nicht in die gemeinsame Bibliothek übernommen\n\n' + '\n'.join(f'- {s}' for s in skipped) + '\n')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/home/claude')
