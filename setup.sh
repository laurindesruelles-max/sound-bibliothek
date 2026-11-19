#!/bin/sh
# Einrichten in jedem Lauf (~4 min beim ersten Mal): Earshot (Ohren) + Modelle. Aufruf: sh setup.sh
set -e
V=/home/claude/es-venv
if [ ! -x "$V/bin/earshot" ]; then
  python3 -m venv "$V"
  [ -d /home/claude/ext/earshot ] || git clone -q --depth 1 https://github.com/Leonxlnx/earshot /home/claude/ext/earshot
  "$V/bin/pip" install -q /home/claude/ext/earshot
fi
# Hugging-Face-Xet-Server ist gesperrt → klassischer Download
HF_HUB_DISABLE_XET=1 "$V/bin/earshot" doctor --fetch >/tmp/earshot_doctor.log 2>&1 || true
grep -q '"problems": \[\]' /tmp/earshot_doctor.log && echo "earshot bereit" || { tail -5 /tmp/earshot_doctor.log; exit 1; }
echo "Benutzen: $V/bin/python $(dirname "$0")/sk.py --help"
