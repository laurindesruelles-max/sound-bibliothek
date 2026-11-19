# Sound-Bibliothek (alle Kanäle)

Gemeinsame Effekt-Bibliothek für Goldsmith, Meisterwerk, Unterbau, Denkmuster und Nachtausgabe (Laurin, 19.11.2026).
Ersetzt die Regel vom 17.11.2026 „jeder Kanal nur eigene Effekte“: **alle Kanäle greifen auf alle Effekte zu,
aber jeder nur auf das, was zu seinem Stilprofil passt.** Musik bleibt pro Kanal (assets/music im Kanal-Repo).

## Laden (in jedem Video-Lauf)
```
git clone --depth 1 --filter=blob:none --sparse https://github.com/laurindesruelles-max/sound-bibliothek /home/claude/sound-bibliothek   # lädt Sounds erst bei Bedarf
sh /home/claude/sound-bibliothek/setup.sh          # Earshot + Modelle (~4 min, nur beim ersten Mal)
SK="/home/claude/es-venv/bin/python /home/claude/sound-bibliothek/sk.py"
```

## Ablauf pro Video
1. **Stellen festlegen** (aus Skript und Schnittliste): Schnitt/Übergang, Enthüllung, Ortswechsel, sichtbare Dinge.
2. **Suchen:** `$SK find "<wie es KLINGT, englisch>" --channel <kanal>` – beschreiben, was man hört
   („a short magical sparkle shimmer“), nicht was es bedeutet („idea moment“). Kein Treffer ab z +2,5 →
   `--online` (Openverse: Wikimedia/Freesound, nur CC0/CC BY; Freesound blockt derzeit Downloads).
3. **Holen:** `$SK get ID … --to work/sfx` und wie bisher in der Engine des Kanals einsetzen.
4. **Erkennungssounds** des Kanals (profiles.json → `erkennung`) bleiben fest und kommen aus dem Kanal-Repo.
5. **Nach dem Rendern:** `$SK check FINAL.mp4 --channel <kanal> --out videos/NNN/qa_sound` → Lautheit (−14 LUFS),
   True Peak, Effektdichte gegen das Profil, Earshot-Hörprotokoll + Bildbogen `sheet.png` (mit Read ansehen:
   Sitzen Hits auf den Schnitten? Ist die Stimme über der Musik?). Exit 1 → beheben.
6. **Lizenzen:** `$SK credits ID …` → Zeilen für die Beschreibung (nur bei CC BY nötig).
7. **Neue gute Funde** bleiben im Katalog → committen und pushen (catalog.json, emb.npy, sfx/).

## Regeln
- Earshot ist nur das **Gehör** (beschreiben, vergleichen, prüfen). Seine eingebaute Sound-Bank wird **nie** benutzt
  (selbst erzeugte Sounds sind verboten).
- Lizenzen: nur CC0, CC BY, Mixkit Free, Higgsfield (eigene Generierung), Laurin. NC/ND/SA/Unklares → abgelehnt.
- `synthetisch: true` = SFX Kit (per Code erzeugt) → Meisterwerk nimmt nur echte Aufnahmen (`nur_echt`).
- Laurins Hörseiten-Urteile: in profiles.json je Kanal `gesperrt` (nie) bzw. `erlaubt` (immer) eintragen.
- Sounds aus dem eigenen Kanal-Repo sind für diesen Kanal immer erlaubt.

## Inhalt (19.11.2026)
753 Dateien, 712 ohne Duplikate: Kanal-Sounds aus allen 5 Repos, SFXMint CC0 (Hugging Face, 294),
SFX Kit CC0 (320, synthetisch). Nicht übernommen (Lizenz unklar/defekt): NICHT_UEBERNOMMEN.md.
Hörseite für Laurin: `$SK review --out review/` (als Artifact veröffentlicht).

| Datei | Inhalt |
|---|---|
| sk.py | Suche, Holen, Online-Nachladen, Prüfen, Hörseite |
| catalog.json | je Sound: Lizenz, Herkunft, Earshot-Beschreibung, Stimmungswerte, Qualitäts-Flags |
| emb.npy | Earshot-Klangabdrücke (CLAP) für die Suche |
| profiles.json | Stilprofile der 5 Kanäle |
| tools/import_kanaele.py | einmaliger Import aus den Kanal-Repos |
