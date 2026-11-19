#!/usr/bin/env python3
"""Gemeinsame Sound-Bibliothek für alle Kanäle (Goldsmith, Meisterwerk, Unterbau, Denkmuster, Nachtausgabe).

Earshot dient nur zum HÖREN (Beschreiben, Vergleichen, Prüfen) – nie als Quelle: selbst erzeugte Sounds sind
bei mehreren Kanälen verboten (Laurin 17.11.2026).

  python3 sk.py find "dark cinematic hit" --channel nachtausgabe [--top 5] [--online]
  python3 sk.py music "tense dark piano" --channel goldsmith [--online]      # nur Openverse-Funde, Kanal-Musik bleibt Standard
  python3 sk.py get ID [ID …] --to work/sfx                                  # Dateien ins Arbeitsverzeichnis kopieren
  python3 sk.py credits ID [ID …]                                             # Urheber-Zeilen (CC BY) für die Beschreibung
  python3 sk.py check FINAL.mp4 --channel goldsmith [--out qa_sound]          # fertiges Video durchhören
  python3 sk.py ingest FILE … --source "…" --license CC0 [--author A --url U] # neuen Sound aufnehmen
  python3 sk.py review --out review/                                          # Hörseite für Laurin

Lizenzen: nur CC0, CC BY, Mixkit Free, Higgsfield (eigene KI-Generierung) und Laurins eigene Sounds.
NC, ND, SA und alles Unklare wird abgelehnt. CC BY → Urheber in die Videobeschreibung (sk.py credits).
"""
import argparse, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(ROOT, 'catalog.json')
EMB = os.path.join(ROOT, 'emb.npy')
PROF = os.path.join(ROOT, 'profiles.json')
SFX = os.path.join(ROOT, 'sfx')
MUS = os.path.join(ROOT, 'music')
UA = {'User-Agent': 'sound-bibliothek/1.0 (Laurin, YouTube-Produktion)'}
GOOD_Z = 2.5  # ab hier gilt ein Treffer als passend
OK_LIC = {'CC0', 'PDM', 'CC BY', 'Mixkit Free', 'Higgsfield', 'Laurin'}
MOODS = {  # Stimmungs-Achsen (CLAP-Textanfragen) – Grundlage der Stilprofile
    'dark': 'a dark ominous tense cinematic sound',
    'epic': 'a big epic cinematic impact or trailer sound',
    'playful': 'a light playful cartoonish cute sound',
    'tech': 'a clean digital interface or technology sound',
    'mechanical': 'a heavy industrial machine or metal tool sound',
    'everyday': 'a realistic everyday recording of an object or room',
    'nature': 'a natural outdoor ambience with birds wind or water',
}


# ------------------------------------------------------------------ Hilfen
def load(p, default):
    try:
        with open(p) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save(p, obj):
    with open(p, 'w') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def audio_hash(path):
    """Hash über den dekodierten Ton (findet Duplikate auch bei anderem Format)."""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                       capture_output=True)
    return hashlib.sha1(r.stdout).hexdigest()[:16]


def norm_license(s):
    s = (s or '').lower()
    if any(x in s for x in ('-nc', ' nc', 'noncommercial', '-nd', ' nd', 'noderiv', 'by-sa', 'sharealike', 'sampling')):
        return None
    if 'cc0' in s or 'public domain' in s or s == 'pdm':
        return 'CC0'
    if s in ('by', 'cc by', 'cc-by') or 'cc by' in s or 'cc-by' in s or 'attribution' in s:
        return 'CC BY'
    if 'mixkit' in s:
        return 'Mixkit Free'
    if 'higgsfield' in s or 'elevenlabs' in s or 'mirelo' in s:
        return 'Higgsfield'
    if 'laurin' in s:
        return 'Laurin'
    return None


def duration(src):
    out = sh('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', src).stdout.strip()
    try:
        return float(out)
    except ValueError:  # z. B. MP3 ohne Kopf: Länge durch Dekodieren bestimmen
        r = sh('ffmpeg', '-v', 'info', '-i', src, '-f', 'null', '-')
        m = re.findall(r'time=(\d+):(\d+):([\d.]+)', r.stderr)
        return int(m[-1][0]) * 3600 + int(m[-1][1]) * 60 + float(m[-1][2]) if m else 0.0


def normalize(src, dst, ambience=False):
    """Hochpass 60 Hz, Anfangsstille weg, Lautheit angleichen (Effekte −20 LUFS, Atmo −28 LUFS), 48 kHz WAV."""
    dur = duration(src)
    lufs = -28 if ambience else -20
    chain = 'highpass=f=60,silenceremove=start_periods=1:start_threshold=-50dB'
    # kurze Klicks: Lautheitsmessung unzuverlässig → Spitze auf −3 dB
    af = f'{chain},loudnorm=I={lufs}:TP=-2:LRA=20' if dur >= 0.8 else f'{chain},alimiter=limit=0.7'
    r = sh('ffmpeg', '-v', 'error', '-y', '-i', src, '-af', af, '-ar', '48000', '-c:a', 'flac', dst)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[-300:])
    if dur < 0.8:  # Spitze sauber auf −3 dBFS
        peak = sh('ffmpeg', '-v', 'info', '-i', dst, '-af', 'volumedetect', '-f', 'null', '-').stderr
        m = re.search(r'max_volume: (-?[\d.]+) dB', peak)
        if m:
            g = -3 - float(m.group(1))
            tmp = dst + '.tmp.flac'
            sh('ffmpeg', '-v', 'error', '-y', '-i', dst, '-af', f'volume={g}dB', '-c:a', 'flac', tmp)
            os.replace(tmp, dst)


# ------------------------------------------------------------------ Earshot (Ohren)
_V = None


def ear():
    global _V
    from earshot import vocab
    if _V is None:
        _V = vocab.get()
    return vocab, _V


def embed(paths):
    import numpy as np
    vocab, _ = ear()
    return np.asarray(vocab.embed_files(paths), dtype='float32')


def moods_for(A):
    import numpy as np
    _, v = ear()
    T = v.embed_text(list(MOODS.values()))
    r = v.calibrate(A, T)
    z = np.asarray(r['z_q'])
    return [{k: round(float(z[i, j]), 2) for j, k in enumerate(MOODS)} for i in range(len(A))]


def describe(path):
    from earshot import api
    d = api.describe(path)
    tags = [t.get('term') or t.get('label') or str(t) for t in d.get('top_tags', [])][:6] \
        if isinstance(d.get('top_tags'), list) else []
    aud = d.get('audioset') or []
    aud = [(a.get('label'), round(a.get('p', 0), 2)) if isinstance(a, dict) else a for a in aud][:3]
    m = d.get('measurements', {})
    keep = {k: m.get(k) for k in ('duration', 'lufs', 'true_peak_dbtp', 'noise_floor_dbfs', 'brightness_hz',
                                  'attack_ms', 'onset_count')}
    return {'summary': d.get('summary', '')[:400], 'tags': tags, 'audioset': aud, 'm': keep}


def quality_flags(m, ambience=False):
    f = []
    if not ambience and (m.get('noise_floor_dbfs') or -99) > -35:
        f.append('rauschen')
    if (m.get('true_peak_dbtp') or -9) > -0.5:
        f.append('uebersteuert')
    if (m.get('duration') or 0) < 0.05:
        f.append('zu_kurz')
    return f


# ------------------------------------------------------------------ Katalog
def catalog():
    return load(CAT, [])


def emb_matrix(cat):
    import numpy as np
    if not os.path.exists(EMB) or not cat:
        return np.zeros((0, 512), 'float32')
    return np.load(EMB).astype('float32')


def write_catalog(cat, A):
    import numpy as np
    save(CAT, cat)
    np.save(EMB, A.astype('float16'))


def ingest(files, source, license, author='', url='', origin='', names=None, kind='sfx', quiet=False):
    import numpy as np
    lic = norm_license(license)
    if lic not in OK_LIC:
        raise SystemExit(f'Lizenz abgelehnt: {license!r} (erlaubt: CC0, CC BY, Mixkit Free, Higgsfield, Laurin)')
    cat = catalog()
    A = emb_matrix(cat)
    seen = {e['hash']: e for e in cat}
    new, paths = [], []
    os.makedirs(SFX if kind == 'sfx' else MUS, exist_ok=True)
    for i, src in enumerate(files):
        h = audio_hash(src)
        if h in seen:
            e = seen[h]
            if origin and origin not in e['origin']:
                e['origin'].append(origin)
            if not quiet:
                print(f'= schon da: {os.path.basename(src)} → {e["id"]}')
            continue
        base = re.sub(r'[^a-z0-9_]+', '_', (names[i] if names else os.path.splitext(os.path.basename(src))[0]).lower())
        sid = base.strip('_')[:40] or h
        if any(e['id'] == sid for e in cat + new):
            sid = f'{sid}_{h[:4]}'
        amb = sid.startswith(('amb', 'ambience')) or 'ambience' in sid
        dst = os.path.join(SFX if kind == 'sfx' else MUS, sid + '.flac')
        if kind == 'sfx':
            normalize(src, dst, ambience=amb)
        else:
            sh('ffmpeg', '-v', 'error', '-y', '-i', src, '-ar', '48000', '-c:a', 'flac', dst)
        d = describe(dst)
        e = {'id': sid, 'file': os.path.relpath(dst, ROOT), 'kind': kind, 'hash': h, 'license': lic,
             'source': source, 'author': author, 'url': url, 'origin': [origin] if origin else [],
             'top_cat': (d.get('top_cat') or ''), 'ambience': amb, 'synthetisch': source.startswith('SFX Kit'), 'flags': quality_flags(d['m'], amb), **d}
        new.append(e)
        paths.append(dst)
        seen[h] = e
        if not quiet:
            print(f'+ {sid:32} {lic:11} {", ".join(d["tags"][:2])} {" ".join(e["flags"])}')
    if new:
        B = embed(paths)
        for e, mo in zip(new, moods_for(B)):
            e['mood'] = mo
        cat += new
        A = np.vstack([A, B]) if len(A) else B
    write_catalog(cat, A)
    return new


# ------------------------------------------------------------------ Profile
def profile(ch):
    P = load(PROF, {})
    if ch and ch not in P:
        raise SystemExit(f'Unbekannter Kanal {ch!r}: {", ".join(P)}')
    return P.get(ch, {})


def fits(e, prof, ch=None):
    """Passt der Sound zum Stilprofil? Eigene Sounds des Kanals und Laurins Freigaben immer; sonst Stimmung,
    verbotene Begriffe und Qualität. Laurins Sperren (Hörseite) gewinnen immer."""
    if e['id'] in prof.get('gesperrt', []):
        return False, 'von Laurin gesperrt'
    if e['id'] in prof.get('erlaubt', []) or (ch and ch in e.get('origin', [])):
        return True, ''
    if prof.get('nur_echt') and e.get('synthetisch'):
        return False, 'synthetisch (Kanal will echte Aufnahmen)'
    if e.get('flags'):
        return False, 'Qualität: ' + ','.join(e['flags'])
    text = ' '.join([e['id'], e.get('source', ''), e.get('summary', ''), ' '.join(e.get('tags', [])), ' '.join(e.get('aliases', []))]).lower()
    for w in prof.get('verboten', []):
        if w in text:
            return False, f'verboten: {w}'
    mo = e.get('mood', {})
    for k, lim in prof.get('max', {}).items():
        if mo.get(k, -9) > lim:
            return False, f'zu {k} ({mo[k]:+.1f} > {lim})'
    return True, ''


# ------------------------------------------------------------------ Suche
_STOP = {'a', 'an', 'the', 'for', 'of', 'with', 'and', 'in', 'on', 'to', 'at', 'sound', 'soft', 'big', 'small',
         'short', 'long', 'deep', 'heavy', 'light', 'gentle', 'dark'}


def kw_bonus(query, e):
    """Hören (CLAP) plus Namen/Herkunft: Wörter der Anfrage im Dateinamen oder in der Quelle zählen mit."""
    words = {w[:4] for w in re.findall(r'[a-z]+', query.lower()) if w not in _STOP and len(w) > 2}
    text = re.findall(r'[a-z]+', (e['id'] + ' ' + e.get('source', '')).lower())
    hits = len(words & {t[:4] for t in text})
    return min(hits, 2) * 1.2
def rank_catalog(query, ch=None, kind='sfx', top=5, show_rejected=False):
    import numpy as np
    cat = catalog()
    A = emb_matrix(cat)
    if not len(A):
        return []
    _, v = ear()
    r = v.calibrate(A, v.embed_text([query]))
    z = np.asarray(r['z_q'])[:, 0] + np.array([kw_bonus(query, e) for e in cat])
    prof = profile(ch) if ch else {}
    out = []
    for i in np.argsort(-z):
        e = cat[i]
        if e['kind'] != kind or e.get('duplikat_von'):
            continue
        ok, why = fits(e, prof, ch) if ch else (not e.get('flags'), ','.join(e.get('flags', [])))
        if ok or show_rejected:
            out.append((float(z[i]), e, why))
        if len([o for o in out if not o[2]]) >= top:
            break
    return out


def openverse(query, category, n=12):
    """Openverse-Suche (nur CC0/CC BY). Lange Anfragen liefern oft nichts → schrittweise kürzen."""
    stop = {'a', 'an', 'the', 'for', 'of', 'with', 'and', 'in', 'on', 'to'}
    words = [w for w in re.findall(r'[\w-]+', query.lower()) if w not in stop]
    tries = [words, words[-3:], words[-2:], words[:2]]
    for ws in tries:
        if not ws:
            continue
        p = {'q': ' '.join(ws), 'license': 'cc0,by', 'page_size': n, 'mature': 'false'}
        if category:
            p['category'] = category
        try:
            req = urllib.request.Request('https://api.openverse.org/v1/audio/?' + urllib.parse.urlencode(p), headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.load(r).get('results', [])
        except Exception as ex:
            print(f'  ! Openverse: {ex}')
            res = []
        if res:
            print(f'  Openverse „{p["q"]}“: {len(res)} Treffer')
            return res
    return []


def fetch_online(query, ch, kind='sfx', keep=1):
    """Openverse (Freesound/Wikimedia für Effekte, Jamendo/ccMixter/Wikimedia für Musik) → Earshot wählt."""
    from earshot import api
    res = openverse(query, 'sound_effect' if kind == 'sfx' else 'music') or (openverse(query, None) if kind == 'sfx' else [])
    tmp = tempfile.mkdtemp(prefix='ov_')
    cands = []
    for it in res:
        lic = norm_license(it.get('license', ''))
        if lic not in ('CC0', 'CC BY'):
            continue
        if kind == 'sfx' and (it.get('duration') or 0) > 60000:
            continue
        p = os.path.join(tmp, re.sub(r'[^\w]+', '_', it['id']) + '.' + (it.get('filetype') or 'mp3'))
        try:
            with urllib.request.urlopen(urllib.request.Request(it['url'], headers=UA), timeout=60) as r, \
                    open(p, 'wb') as f:
                shutil.copyfileobj(r, f)
        except Exception as ex:
            print(f'  ! Download fehlgeschlagen ({it.get("source")}): {ex}')
            continue
        cands.append((p, it, lic))
    if not cands:
        print('  keine passenden Openverse-Treffer')
        return []
    rk = api.rank([c[0] for c in cands], query)['results']
    by = {c[0]: c for c in cands}
    added = []
    for r in rk:
        if r['verdict'] not in ('strong', 'plausible') or len(added) >= keep:
            continue
        p, it, lic = by[r['path']]
        if kind == 'music':  # Gesang/Sprache aussortieren
            aud = describe(p)['audioset']
            if any(a and a[0] and re.search(r'speech|sing|vocal|rap|choir', str(a[0]), re.I) and a[1] > 0.2
                   for a in aud):
                print(f'  − {it["title"][:40]}: Gesang/Sprache'); continue
        name = re.sub(r'[^a-z0-9]+', '_', (it.get('title') or 'ov').lower())[:30]
        new = ingest([p], f'Openverse/{it.get("source")}: {it.get("title")}', lic, author=it.get('creator') or '',
                     url=it.get('foreign_landing_url') or it['url'], origin='openverse', names=[name],
                     kind=kind, quiet=True)
        for e in new:
            ok, why = fits(e, profile(ch), ch) if ch else (True, '')
            print(f'  + neu: {e["id"]} (z {r["z"]:+.1f}, {lic}, {it.get("source")}){"" if ok else "  [passt nicht zu " + ch + ": " + why + "]"}')
            if ok:
                added.append(e)
    shutil.rmtree(tmp, ignore_errors=True)
    return added


def cmd_find(a, kind='sfx'):
    hits = rank_catalog(a.query, a.channel, kind, a.top)
    good = [h for h in hits if h[0] >= GOOD_Z]
    for z, e, _ in hits:
        print(f'{e["id"]:32} z {z:+.1f}  {e["license"]:11} {e.get("summary", "")[:70]}')
    if (len(good) < (1 if kind == 'sfx' else 2)) and a.online:
        print(f'… Bestand reicht nicht, suche bei Openverse: {a.query!r}')
        fetch_online(a.query, a.channel, kind, keep=1 if kind == 'sfx' else 3)
    elif not good:
        print('(kein guter Treffer im Bestand – mit --online bei Openverse suchen)')


def ensure_file(rel):
    """Teil-Klon (--filter=blob:none --sparse): Datei erst bei Bedarf von GitHub holen."""
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            r = subprocess.run(['git', '-C', ROOT, 'show', f'HEAD:{rel}'], stdout=f, stderr=subprocess.PIPE)
        if r.returncode or not os.path.getsize(p):
            os.remove(p)
            raise SystemExit(f'Datei nicht ladbar: {rel}: {r.stderr.decode().strip()[-200:]}')
    return p


def cmd_get(a):
    cat = {e['id']: e for e in catalog()}
    os.makedirs(a.to, exist_ok=True)
    for i in a.ids:
        if i not in cat:
            raise SystemExit(f'unbekannt: {i}')
        src = ensure_file(cat[i]['file'])
        sh('ffmpeg', '-v', 'error', '-y', '-i', src, '-c:a', 'pcm_s16le', os.path.join(a.to, i + '.wav'))
    print(f'{len(a.ids)} Datei(en) → {a.to}')


def cmd_credits(a):
    cat = {e['id']: e for e in catalog()}
    lines = []
    for i in a.ids:
        e = cat.get(i)
        if e and e['license'] == 'CC BY':
            lines.append(f'„{e["source"].split(": ", 1)[-1]}“ von {e["author"] or "unbekannt"} – CC BY – {e["url"]}')
    print('\n'.join(['Sounds:'] + lines) if lines else '(keine Namensnennung nötig)')


def cmd_check(a):
    """Fertiges Video durchhören: Lautheit, Spitzen, Effektdichte, Sync zu Schnitten, Bildbogen."""
    from earshot import api
    os.makedirs(a.out, exist_ok=True)
    wav = os.path.join(a.out, 'mix.wav')
    sh('ffmpeg', '-v', 'error', '-y', '-i', a.video, '-vn', '-ac', '2', '-ar', '48000', wav)
    t = api.timeline(wav, video=a.video, detail='normal')
    api.sheet(wav, os.path.join(a.out, 'sheet.png'), video=a.video, tl=t)
    save(os.path.join(a.out, 'timeline.json'), t)
    m = api.measure(wav)
    dur = m.get('duration') or t.get('duration') or 1
    prof = profile(a.channel) if a.channel else {}
    dens = None
    if a.cues:  # Liste der gesetzten Effekte aus der Engine: [Sekunden …] oder [{"t": …}, …]
        cues = load(a.cues, [])
        dens = len(cues) / (dur / 60)
    sync = (t.get('summary', '').split('Sync to')[1].split('.')[0] if 'Sync to' in t.get('summary', '') else '–')
    rep = [f'# Sound-Check {os.path.basename(a.video)}', '',
           f'- Lautheit: {m.get("lufs")} LUFS (Ziel −14 ±1,5), True Peak {m.get("true_peak_dbtp")} dBTP (Ziel ≤ −1)',
           f'- Effektdichte: ' + (f'{dens:.1f}/min (Profil {a.channel}: max {prof.get("dichte_max", "–")}/min)'
                                  if dens is not None else 'nur mit --cues (Effektliste der Engine)'),
           f'- Sync zu den Schnitten: {sync.strip()}',
           f'- Bildbogen: {os.path.join(a.out, "sheet.png")} (mit Read ansehen)', '',
           '## Earshot-Hörprotokoll', t.get('summary', '')[:4000]]
    open(os.path.join(a.out, 'sound_check.md'), 'w').write('\n'.join(rep))
    print('\n'.join(rep[:6]))
    bad = (m.get('lufs') is not None and abs(m['lufs'] + 14) > 1.5) or (m.get('true_peak_dbtp') or -9) > -1 \
        or (dens is not None and prof.get('dichte_max') and dens > prof['dichte_max'] * 1.3)
    sys.exit(1 if bad else 0)


def cmd_review(a):
    """Hörseite: je Kategorie eine MP3 (alle Sounds hintereinander, max. 4 s), Tippen spielt genau einen Sound.
    Zeigt Stimmung, Lizenz und für welche Kanäle der Sound laut Stilprofil erlaubt ist."""
    os.makedirs(os.path.join(a.out, 'a'), exist_ok=True)
    P = load(PROF, {})
    groups = {}
    for e in catalog():
        if e.get('duplikat_von'):
            continue
        cat_ = 'musik' if e['kind'] == 'music' else ('atmo' if e.get('ambience') else
               (e.get('top_cat') or (e.get('audioset') or [['sonstiges']])[0][0] or 'sonstiges'))
        groups.setdefault(re.sub(r'[^a-z0-9]+', '_', str(cat_).lower())[:20], []).append(e)
    # kleine Gruppen zusammenfassen
    merged = {}
    for g, es in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        key = g if len(es) >= 8 else 'sonstiges'
        merged.setdefault(key, []).extend(es)
    sections = []
    for g, es in merged.items():
        lst = os.path.join(a.out, f'{g}.txt'); t = 0.0; rows = []
        with open(lst, 'w') as f:
            for e in sorted(es, key=lambda e: e['id']):
                d = min(4.0, (e.get('m') or {}).get('duration') or 4.0)
                seg = os.path.join(a.out, 'a', e['id'] + '.wav')
                sh('ffmpeg', '-v', 'error', '-y', '-i', ensure_file(e['file']), '-t', str(d), '-af',
                   f'afade=out:st={max(0, d - 0.15)}:d=0.15,apad=pad_dur=0.4', '-ar', '44100', '-ac', '2', seg)
                f.write(f"file '{seg}'\n")
                real = duration(seg)
                chans = [c[:4] for c in P if fits(e, P[c], c)[0]]
                mood = max((e.get('mood') or {'-': 0}).items(), key=lambda kv: kv[1])[0]
                rows.append(f'<tr onclick="p(\'{g}\',{t:.3f},{d:.3f},this)"><td>▶</td><td><b>{html.escape(e["id"])}</b>'
                            f'<br><small>{html.escape(", ".join(e.get("tags", [])[:2]))}</small></td><td>{mood}</td>'
                            f'<td>{" ".join(chans) or "–"}</td><td><small>{html.escape(e["license"])}'
                            f'{" · synth." if e.get("synthetisch") else ""}{" ⚠ " + ",".join(e["flags"]) if e.get("flags") else ""}</small></td></tr>')
                t += real
        sh('ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-b:a', '96k',
           os.path.join(a.out, f'{g}.mp3'))
        os.remove(lst)
        sections.append(f'<h2>{g} ({len(es)})</h2><audio id="{g}" src="{g}.mp3" preload="none"></audio><table>{"".join(rows)}</table>')
    shutil.rmtree(os.path.join(a.out, 'a'))
    n = sum(len(v) for v in merged.values())
    page = f'''<!DOCTYPE html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sound-Bibliothek – Hörprobe</title><style>body{{font:15px system-ui;margin:12px;background:#111;color:#eee}}table{{border-collapse:collapse;width:100%}}
td{{padding:7px 5px;border-bottom:1px solid #2a2a2a}}tr{{cursor:pointer}}tr.on{{background:#243}}small{{color:#9a9a9a}}h1{{font-size:20px}}h2{{font-size:16px;margin-top:22px;color:#8cf}}</style></head><body>
<h1>Sound-Bibliothek – {n} Sounds</h1><p>Zeile antippen = Sound abspielen. „Kanäle“: wo der Sound laut Stilprofil erlaubt ist (Gold, Meis, Unte, Denk, Nach). Was nicht passt: Namen notieren und Claude schicken – er kommt auf die Sperrliste des Kanals.</p>
{"".join(sections)}
<script>let cur=null,stopAt=0;function p(id,t,d,tr){{if(cur)cur.pause();document.querySelectorAll('tr.on').forEach(x=>x.classList.remove('on'));tr.classList.add('on');
cur=document.getElementById(id);const go=()=>{{cur.currentTime=t;stopAt=t+d;cur.play();}};if(cur.readyState<1){{cur.addEventListener('loadedmetadata',go,{{once:true}});cur.load();}}else go();}}
setInterval(()=>{{if(cur&&!cur.paused&&cur.currentTime>=stopAt)cur.pause();}},40);</script></body></html>'''
    open(os.path.join(a.out, 'index.html'), 'w').write(page)
    print(f'Hörseite: {a.out}/index.html ({n} Sounds, {len(merged)} Gruppen)')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = ap.add_subparsers(dest='cmd', required=True)
    for n in ('find', 'music'):
        p = s.add_parser(n); p.add_argument('query'); p.add_argument('--channel'); p.add_argument('--top', type=int, default=5)
        p.add_argument('--online', action='store_true')
    p = s.add_parser('get'); p.add_argument('ids', nargs='+'); p.add_argument('--to', required=True)
    p = s.add_parser('credits'); p.add_argument('ids', nargs='+')
    p = s.add_parser('check'); p.add_argument('video'); p.add_argument('--channel'); p.add_argument('--cues'); p.add_argument('--out', default='qa_sound')
    p = s.add_parser('review'); p.add_argument('--out', default='review')
    p = s.add_parser('ingest'); p.add_argument('files', nargs='+'); p.add_argument('--source', required=True)
    p.add_argument('--license', required=True); p.add_argument('--author', default=''); p.add_argument('--url', default='')
    p.add_argument('--kind', default='sfx', choices=['sfx', 'music'])
    a = ap.parse_args()
    if a.cmd == 'find': cmd_find(a)
    elif a.cmd == 'music': cmd_find(a, 'music')
    elif a.cmd == 'get': cmd_get(a)
    elif a.cmd == 'credits': cmd_credits(a)
    elif a.cmd == 'check': cmd_check(a)
    elif a.cmd == 'review': cmd_review(a)
    elif a.cmd == 'ingest': ingest(a.files, a.source, a.license, a.author, a.url, kind=a.kind)


if __name__ == '__main__':
    main()
