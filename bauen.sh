#!/bin/bash
# ---------------------------------------------------------------------------
# Rikus Updateall — Paket bauen
#
# Aufruf:   ./bauen.sh          (im Wurzelverzeichnis des Projekts)
# Ergebnis: rikus-updateall_<Fassung>_all.deb + .sha256 im selben Ordner
#
# Die Fassungsnummer wird AUS paket/DEBIAN/control gelesen und gegen die im
# Programm geprueft — sie kann also nicht auseinanderlaufen.
#
# ⚠️ ZWEI DINGE, DIE HIER NICHT VERHANDELBAR SIND (Lehre aus Rikus Zram):
#
#   -Zxz              Ohne diese Vorgabe packt neueres dpkg mit »zstd«.
#                     Aeltere Systeme auf Debian-11-Basis (MX 21, antiX 21)
#                     koennen zstd-Pakete NICHT oeffnen — genau die Systeme,
#                     fuer die dieses Programm gedacht ist. Auf dem eigenen
#                     Rechner faellt der Fehler nie auf.
#
#   --root-owner-group  Wird als normaler Benutzer gebaut, gehoerten sonst alle
#                     Dateien im Paket diesem Benutzer. Auf einem fremden
#                     Rechner gehoerte das Programm dann irgendeinem dortigen
#                     Benutzer — bei einem Programm mit Systemrechten ist das
#                     eine Sicherheitsluecke.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(grep '^Version:' paket/DEBIAN/control | awk '{print $2}')
IM_PROGRAMM=$(grep -m1 "^VERSION = " rikus-updateall.py | cut -d"'" -f2)
if [ "$VERSION" != "$IM_PROGRAMM" ]; then
  echo "ABBRUCH: control sagt $VERSION, das Programm sagt $IM_PROGRAMM." >&2
  echo "Beide muessen uebereinstimmen, sonst meldet der Update-Hinweis Unsinn." >&2
  exit 1
fi
PAKET="rikus-updateall_${VERSION}_all.deb"
BAUM=$(mktemp -d)
trap 'rm -rf "$BAUM"' EXIT

echo "Baue Rikus Updateall $VERSION"

# ---------------------------------------------------------------------------
# ABHAENGIGKEITEN — automatisch, bei JEDEM Bau
#
# ⭐ WARUM DAS HIER STEHT (Gilbert, 22.07.2026: „auch die abhaengigkeiten
# kontrolliert?"): Gemessen wurden sie beim ERSTEN Bau — danach drei Fassungen
# lang nicht mehr, obwohl neuer Code dazukam. Dass nichts fehlte, war Glueck.
# Eine Pruefung, die am Erinnern haengt, ist keine Pruefung.
#
# Geprueft werden BEIDE Richtungen:
#   1. Ruft der Quelltext ein Werkzeug auf, das nirgends genannt ist?
#   2. Ist gegenueber der letzten Fassung etwas aus Depends verschwunden?
# ---------------------------------------------------------------------------
echo "--- Abhaengigkeiten (automatisch geprueft) ---"
FEHLT=0
GENANNT=$(grep -E '^(Depends|Recommends|Suggests):' paket/DEBIAN/control)

# Richtung 1: jedes aufgerufene Werkzeug muss genannt oder Essential sein
for w in $(grep -oE "_werkzeug\('[a-z0-9._-]+'\)|_lauf\('[a-z0-9._-]+'" rikus-updateall.py \
           | grep -oE "'[a-z0-9._-]+'" | tr -d "'" | sort -u); do
  pfad=""
  for d in /usr/local/bin /usr/bin /bin /usr/sbin /sbin; do
    [ -x "$d/$w" ] && { pfad=$(realpath "$d/$w"); break; }     # realpath: Symlink-Falle
  done
  if [ -z "$pfad" ]; then echo "  ?  $w hier nicht installiert - nicht pruefbar"; continue; fi
  paket=$(dpkg -S "$pfad" 2>/dev/null | cut -d: -f1 | head -1)
  if [ -z "$paket" ]; then echo "  ?  $w gehoert keinem Paket"; continue; fi
  if echo "$GENANNT" | grep -qw "$paket"; then
    echo "  ok $w -> $paket"
  elif [ "$(dpkg-query -W -f='${Essential}' "$paket" 2>/dev/null)" = "yes" ]; then
    echo "  ok $w -> $paket (Essential, darf fehlen)"
  else
    echo "  ✖  $w -> $paket FEHLT in control"; FEHLT=1
  fi
done

# Python-Bausteine: was aus einem Paket kommt, muss genannt sein
for mod in $(grep -hoE '^[[:space:]]*(import|from) [a-z_.]+' rikus-updateall.py \
             | awk '{print $2}' | cut -d. -f1 | sort -u); do
  herkunft=$(python3 -c "
import importlib.util as u, sys
s = u.find_spec('$mod')
if s is None: print('FEHLT'); raise SystemExit
p = getattr(s,'origin','') or ''
print('PAKET' if ('dist-packages' in p or 'site-packages' in p) else 'EINGEBAUT')" 2>/dev/null)
  case "$herkunft" in
    FEHLT) echo "  ✖  Python-Baustein $mod nicht vorhanden"; FEHLT=1 ;;
    PAKET) echo "$GENANNT" | grep -q 'python3-gi' && echo "  ok Python-Baustein $mod (python3-gi)" \
             || { echo "  ✖  Python-Baustein $mod kommt aus einem Paket, das nicht genannt ist"; FEHLT=1; } ;;
  esac
done
echo "  ok Python-Bausteine geprueft"

# Richtung 2: seit der letzten Fassung etwas verloren?
if git rev-parse HEAD >/dev/null 2>&1; then
  git show HEAD:paket/DEBIAN/control 2>/dev/null | grep -E '^Depends:' \
    | sed 's/^Depends://' | tr ',' '\n' | tr -d ' ' | grep -v '^$' | sort -u > /tmp/dep_alt.$$
  grep -E '^Depends:' paket/DEBIAN/control \
    | sed 's/^Depends://' | tr ',' '\n' | tr -d ' ' | grep -v '^$' | sort -u > /tmp/dep_neu.$$
  VERLOREN=$(comm -23 /tmp/dep_alt.$$ /tmp/dep_neu.$$)
  rm -f /tmp/dep_alt.$$ /tmp/dep_neu.$$
  if [ -n "$VERLOREN" ]; then
    echo "  ✖  seit der letzten Fassung VERLOREN: $(echo $VERLOREN)"; FEHLT=1
  else
    echo "  ok nichts gegenueber der letzten Fassung verloren"
  fi
fi

if [ "$FEHLT" != "0" ]; then
  echo >&2
  echo "ABBRUCH: Die Abhaengigkeiten stimmen nicht (siehe oben)." >&2
  exit 1
fi
echo

# --- Baum IMMER frisch aus dem Projekt zusammenstellen ---------------------
# So koennen Paket und Projekt nicht auseinanderlaufen (Mintshot lieferte
# einmal veraltete Anleitungen aus, weil das Paket eine alte Kopie enthielt).
mkdir -p "$BAUM/opt/rikus-updateall" "$BAUM/usr/share/doc/rikus-updateall"
cp -r paket/DEBIAN "$BAUM/DEBIAN"
cp -r paket/usr "$BAUM/"
cp rikus-updateall.py ANLEITUNG.md GUIDE.md README.md README.de.md \
   CHANGELOG.md LICENSE "$BAUM/opt/rikus-updateall/"
cp -r daten "$BAUM/opt/rikus-updateall/"
chmod 755 "$BAUM/opt/rikus-updateall/rikus-updateall.py"

# --- Symbol ins System einhaengen, damit das Menue es findet ---------------
for g in 16 22 24 32 48 64 128 256; do
  ziel="$BAUM/usr/share/icons/hicolor/${g}x${g}/apps"
  mkdir -p "$ziel"
  cp "daten/icon-$g.png" "$ziel/rikus-updateall.png"
done

# --- Pflichtteile jedes Debian-Pakets --------------------------------------
cat > "$BAUM/usr/share/doc/rikus-updateall/copyright" <<'ENDE'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Rikus Updateall
Source: https://github.com/Zahnschmerz/rikus-updateall

Files: *
Copyright: 2026 Gilbert Rikus <gilbert@rikus.info>
License: GPL-3.0+
 This program is free software: you can redistribute it and/or modify it
 under the terms of the GNU General Public License as published by the Free
 Software Foundation, either version 3 of the License, or (at your option)
 any later version.
 .
 This program is distributed in the hope that it will be useful, but WITHOUT
 ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 more details.
 .
 On Debian systems, the full text of the GNU General Public License version 3
 can be found in the file /usr/share/common-licenses/GPL-3.
ENDE

cat > "$BAUM/DEBIAN/postinst" <<'ENDE'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    # Symbolverzeichnis auffrischen, sonst zeigt das Menue kein Bild
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications 2>/dev/null || true
    fi
fi
exit 0
ENDE

cat > "$BAUM/DEBIAN/postrm" <<'ENDE'
#!/bin/sh
set -e
# Die Einstellungen des Nutzers (~/.config/rikus-updateall) bleiben absichtlich
# stehen - und ebenso seine gesicherten alten Programmfassungen in ~/Dokumente.
# Ein Deinstallieren darf niemals Dateien des Nutzers wegraeumen.
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor 2>/dev/null || true
    fi
fi
exit 0
ENDE
chmod 755 "$BAUM/DEBIAN/postinst" "$BAUM/DEBIAN/postrm"

# --- Bauen -----------------------------------------------------------------
rm -f "$PAKET" "$PAKET.sha256"
dpkg-deb -Zxz --root-owner-group --build "$BAUM" "$PAKET" >/dev/null
sha256sum "$PAKET" > "$PAKET.sha256"

echo
echo "Fertig: $PAKET  ($(du -h "$PAKET" | cut -f1))"
echo "Pruefsumme: $(cut -c1-16 < "$PAKET.sha256")…"
echo
echo "--- Selbstkontrolle ---"
echo -n "  kein systemd in Depends:  "; grep '^Depends:' paket/DEBIAN/control | grep -q systemd && echo "✖ DOCH!" || echo "✔"
echo -n "  kein __pycache__ im Paket: "; dpkg-deb -c "$PAKET" | grep -q __pycache__ && echo "✖ DOCH!" || echo "✔"
echo -n "  alles gehoert root:        "; dpkg-deb -c "$PAKET" | grep -qv 'root/root' && echo "✖ nicht alles" || echo "✔"
echo -n "  Anleitungen aktuell:       "
for f in ANLEITUNG.md GUIDE.md README.md README.de.md CHANGELOG.md; do
  a=$(sha256sum "$f" | cut -d' ' -f1)
  b=$(dpkg-deb --fsys-tarfile "$PAKET" | tar -xO "./opt/rikus-updateall/$f" 2>/dev/null | sha256sum | cut -d' ' -f1)
  [ "$a" = "$b" ] || { echo "✖ $f weicht ab"; exit 1; }
done
echo "✔ (per Pruefsumme verglichen)"
echo -n "  Symbol in allen Groessen:  "
n=$(dpkg-deb -c "$PAKET" | grep -c 'icons/hicolor/.*/rikus-updateall.png')
[ "$n" = "8" ] && echo "✔ 8 Groessen" || echo "✖ nur $n"
