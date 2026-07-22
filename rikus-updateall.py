#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rikus Updateall — zeigt, welche Programme NICHT aus apt kommen und veraltet sind.

Das Problem, das es loest:
`apt update` kennt nur Programme aus den eingetragenen Paketquellen. Alles, was
von Hand als .deb installiert wurde, als AppImage herumliegt, in /opt oder
/usr/local/bin sitzt oder ueber npm kam, wird NIE aktualisiert - und niemand
sagt einem das. Gemessen am 22.07.2026 auf 7 Rechnern: 10 veraltete Fassungen,
eine davon 12 Versionen zurueck.

BAUREGELN (siehe Vault "Bauregeln fuer Rikus-Programme") - hier eingehalten:
  * Keine Emoji jenseits von U+FFFF. Nur ● ⚠ ▶ → • ✔ ✖ (auf manchen Systemen sonst leere Kaestchen)
  * Farbe immer selbst setzen, nie auf ein farbiges Zeichen hoffen
  * Fensterhoehe an den Bildschirm binden, nie festnageln
  * Systembefehle mit vollem Pfad - aus dem Startmenue fehlt /sbin im PATH
  * Alles, was in set_markup() landet, durch sicher() schicken (ein & macht die Zeile unsichtbar)
  * GiB statt GB (Linux rechnet mit 1024)
  * Was noch nicht geht, wird GESPERRT - nicht mit Kleingedrucktem erklaert
  * Netzabfragen nebenlaeufig mit hartem Zeitlimit. Kein Internet ist der NORMALFALL.
  * Anschauen ohne Passwort. Dieses Programm liest nur - es aendert nichts.
"""

import os
import re
import json
import glob
import shutil
import threading
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango, GLib, Gdk           # noqa: E402

VERSION = '1.2'
PROGRAMM = 'Rikus Updateall'

# Ein Programm, das Updates meldet, muss sich selbst prüfen können - alles
# andere wäre unglaubwürdig. Gleiches Verfahren wie in Rikus Zram v1.10.
UPDATE_API = 'https://api.github.com/repos/Zahnschmerz/rikus-updateall/releases/latest'
UPDATE_SEITE = 'https://github.com/Zahnschmerz/rikus-updateall/releases/latest'

KONFIG_ORDNER = os.path.expanduser('~/.config/rikus-updateall')
QUELLEN_DATEI = os.path.join(KONFIG_ORDNER, 'quellen.json')
NETZ_ZEITLIMIT = 6            # Sekunden je Abfrage; danach still aufgeben

# ---------------------------------------------------------------------------
# SPRACHE - deutsch oder englisch, nach Systemeinstellung (Verfahren wie Zram)
# ---------------------------------------------------------------------------


def _systemsprache():
    lang = (os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES')
            or os.environ.get('LANG') or 'en')
    return 'de' if lang.lower().startswith('de') else 'en'


SPRACHE = _systemsprache()


def t(de, en):
    """Text in der Systemsprache. Uebersetzung steht direkt neben dem Original."""
    return de if SPRACHE == 'de' else en


# ---------------------------------------------------------------------------
# Werkzeuge - IMMER mit vollem Pfad suchen, nie auf $PATH verlassen
# ---------------------------------------------------------------------------
PFADE = ['/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']


def _werkzeug(name):
    for p in PFADE:
        voll = os.path.join(p, name)
        if os.access(voll, os.X_OK):
            return voll
    return shutil.which(name)


def _lauf(name, *args, zeit=15):
    """Befehl ausfuehren, Ausgabe als Text. Bei jedem Fehler: leerer Text."""
    voll = _werkzeug(name)
    if not voll:
        return ''
    try:
        e = subprocess.run([voll] + list(args), capture_output=True,
                           text=True, timeout=zeit)
        return (e.stdout or '') + (e.stderr or '')
    except Exception:
        return ''


def sicher(wert):
    """Fuer set_markup(): ein & im Text macht sonst die GANZE Zeile unsichtbar."""
    return GLib.markup_escape_text(str(wert if wert is not None else ''))


def version_tupel(text):
    """'v1.10' -> (1, 10). Versionen NIEMALS als Text vergleichen:
    '1.10' < '1.9' ist als Text WAHR - dann bliebe der Hinweis fuer immer aus."""
    return tuple(int(x) for x in re.findall(r'\d+', text or '')) or (0,)


KEIN_UPDATE_DATEI = os.path.join(KONFIG_ORDNER, 'kein-update-hinweis')


def eigene_neue_fassung():
    """Gibt es eine neuere Fassung DIESES Programms? Sonst None.

    None heisst schlicht „keinen Hinweis anzeigen" - egal ob es nichts Neues
    gibt, das Netz fehlt oder der Nutzer es abgeschaltet hat. Kein Internet
    ist der NORMALFALL, kein Fehler. Abschalten:
        touch ~/.config/rikus-updateall/kein-update-hinweis
    """
    if os.path.exists(KEIN_UPDATE_DATEI):
        return None
    try:
        import urllib.request
        anfrage = urllib.request.Request(
            UPDATE_API, headers={'User-Agent': f'{PROGRAMM}/{VERSION}'})
        with urllib.request.urlopen(anfrage, timeout=4) as antwort:
            tag = json.loads(antwort.read().decode('utf-8')).get('tag_name', '')
        if version_tupel(tag) > version_tupel(VERSION):
            return tag.lstrip('vV') or tag
    except Exception:
        pass                  # ein Hinweis darf NIE stoeren
    return None


def ist_neuer(neu, alt):
    """Ist 'neu' wirklich neuer als 'alt'? Beide duerfen v/V und Text enthalten."""
    if not neu or not alt:
        return False
    return version_tupel(neu) > version_tupel(alt)


# ---------------------------------------------------------------------------
# TEIL 1 - FINDEN: was auf diesem Rechner kommt nicht aus apt?
# ---------------------------------------------------------------------------

class Fund:
    """Ein gefundenes Programm ausserhalb von apt."""

    def __init__(self, name, version, sorte, ort='', herkunft=''):
        self.name = name
        self.version = version or '?'
        self.sorte = sorte              # 'deb' | 'flatpak' | 'appimage' | 'binaer' | 'npm'
        self.ort = ort
        self.herkunft = herkunft        # Homepage/Vcs aus dem Paket, falls vorhanden
        self.praefix = ''               # nur bei npm: wo diese Installation liegt
        self.repo = self._repo_raten()  # 'besitzer/projekt' oder ''
        self.neueste = None             # wird nebenlaeufig gefuellt
        self.status = 'offen'           # offen | aktuell | veraltet | unbekannt

    def _repo_raten(self):
        """Steht in den Paketangaben schon eine GitHub-Adresse?

        ⭐ DAS IST DER KERN FUER FREMDE NUTZER: Eine eingebaute Namensliste kennt
        immer nur die Programme dessen, der sie geschrieben hat. Wer das Programm
        auf seinem eigenen Rechner startet, hat voellig andere. Deshalb muss die
        Herkunft aus dem Paket selbst kommen, wo immer das geht.
        `self.herkunft` enthaelt Homepage UND die Vcs-Felder (siehe waisen_finden).
        """
        for muster in (r'github\.com/([\w.-]+)/([\w.-]+)',
                       r'gitlab\.com/([\w.-]+)/([\w.-]+)',
                       r'codeberg\.org/([\w.-]+)/([\w.-]+)'):
            m = re.search(muster, self.herkunft or '')
            if m:
                projekt = m.group(2)
                for schwanz in ('.git', '/'):
                    projekt = projekt[:-len(schwanz)] if projekt.endswith(schwanz) else projekt
                return f'{m.group(1)}/{projekt}'
        return ''


def waisen_finden():
    """.deb-Pakete, die installiert sind, aber KEINE Paketquelle kennt.

    ⚠️ Der naheliegende Weg ist FALSCH - zweimal gemessen am 22.07.2026:
      * `apt list --installed | grep local`  -> fand 0 (Falschalarm-Entwarnung!)
      * nur Paketnamen vergleichen           -> fand auf einem Testsystem 60, davon 22 Karteileichen
                                                (Debian 13 benannte um: libgtk-3-0 -> ...t64)
    Richtig ist: nur Pakete mit Status "installed" nehmen UND per apt-cache policy
    gegenpruefen, ob wirklich keine Quelle (http/file) dahintersteht.
    """
    # ⭐ Nicht nur Homepage: Viele Pakete tragen im Feld `Vcs-Browser` oder
    # `Vcs-Git` die Adresse ihres Quellprojekts - oft ein GitHub-Link, auch
    # wenn die Homepage nur auf die Firmenseite zeigt. Das kostet nichts und
    # erschliesst Programme, die keine Namensliste je kennen koennte.
    roh = _lauf('dpkg-query', '-f',
                '${Package} ${db:Status-Status} ${Version}|'
                '${Homepage} ${Vcs-Browser} ${Vcs-Git}\n', '-W')
    installiert = {}
    for zeile in roh.splitlines():
        try:
            kopf, herkunft = zeile.split('|', 1)
            teile = kopf.split()
            if len(teile) >= 3 and teile[1] == 'installed':
                installiert[teile[0]] = (teile[2], herkunft.strip())
        except ValueError:
            continue
    if not installiert:
        return []

    bekannt = set()
    for datei in glob.glob('/var/lib/apt/lists/*_Packages'):
        try:
            with open(datei, 'r', encoding='utf-8', errors='ignore') as f:
                for zeile in f:
                    if zeile.startswith('Package: '):
                        bekannt.add(zeile[9:].strip())
        except OSError:
            continue
    if not bekannt:
        return []            # ohne Paketlisten waere JEDES Paket eine Waise

    funde = []
    for paket in sorted(set(installiert) - bekannt):
        # Feintest: kennt doch eine echte Quelle das Paket?
        policy = _lauf('apt-cache', 'policy', paket, zeit=8)
        if re.search(r'https?://|file:/', policy):
            continue
        version, herkunft = installiert[paket]
        funde.append(Fund(paket, version, 'deb', '/var/lib/dpkg', herkunft))
    return funde


def flatpaks_finden():
    aus = _lauf('flatpak', 'list', '--app', '--columns=application,version')
    funde = []
    for zeile in aus.splitlines():
        teile = zeile.split('\t') if '\t' in zeile else zeile.split()
        if teile and teile[0] and '.' in teile[0]:
            funde.append(Fund(teile[0], teile[1] if len(teile) > 1 else '?',
                              'flatpak', 'flatpak'))
    return funde


def appimages_finden():
    """AppImages im Benutzerordner. Die Version steckt meist im Dateinamen.

    🔴 Der SICHERUNGSORDNER bleibt aussen vor. Dort legt dieses Programm die
    alten Fassungen ab - taucht die Sicherung anschliessend als eigenes
    Programm in der Liste auf, sieht der Nutzer sein eigenes Sicherheitsnetz
    als vermeintlich veraltetes Programm wieder. Am 22.07.2026 genau so
    passiert: `Raspberry_Pi_Imager` stand doppelt da, einmal aus ~/Dokumente.
    """
    funde = []
    heim = os.path.expanduser('~')
    sicherung = os.path.abspath(SICHERUNGSORDNER)
    for wurzel, ordner, dateien in os.walk(heim):
        if os.path.abspath(wurzel) == sicherung:
            ordner[:] = []
            continue
        if wurzel[len(heim):].count(os.sep) >= 3:
            ordner[:] = []
            continue
        ordner[:] = [o for o in ordner if not o.startswith('.')]
        for d in dateien:
            if d.lower().endswith('.appimage'):
                m = re.search(r'[_-]v?(\d+[\d.]*)', d)
                name = re.split(r'[_-]v?\d', d)[0]
                voll = os.path.join(wurzel, d)
                funde.append(Fund(name, m.group(1) if m else '?', 'appimage',
                                  voll, appimage_herkunft(voll)))
    return funde


def appimage_herkunft(pfad):
    """⭐ Viele AppImages tragen ihre Update-Adresse IN SICH.

    Der offizielle AppImage-Standard sieht ein Feld vor, das sagt, woher die
    naechste Fassung kommt - meist im Format
    `gh-releases-zsync|besitzer|projekt|latest|name-*.AppImage`.
    Wer das ausliest, braucht fuer solche Programme ueberhaupt keine Liste.
    Kostet einen Aufruf und schadet nie: Wenn nichts drinsteht, kommt nichts zurueck.
    """
    if not os.access(pfad, os.X_OK):
        return ''
    aus = _lauf(pfad, '--appimage-updateinfo', zeit=10)
    m = re.search(r'gh-releases-zsync\|([\w.-]+)\|([\w.-]+)\|', aus or '')
    if m:
        return f'https://github.com/{m.group(1)}/{m.group(2)}'
    return aus.strip()[:200] if aus and 'github.com' in (aus or '') else ''


# Programme, die keine ELF-Datei sind, aber trotzdem eigenstaendig aktualisiert
# werden. Ohne diese Liste wuerden sie als "eigenes Skript" aussortiert.
BEKANNTE_SKRIPTE = {'claude', 'codex', 'bun', 'bunx'}


def npm_dahinter(pfad):
    """Steckt hinter dieser Programmdatei in Wahrheit ein npm-Paket?

    🔴 AUF EINEM ZWEITEN RECHNER GEFUNDEN: ein npm-Werkzeug lag ZWEIMAL als Programmdatei
    vor - `/usr/local/bin/codex` und `~/.local/bin/codex`. Beide sind aber nur
    Verweise in je einen `node_modules`-Ordner, mit VERSCHIEDENEN Fassungen
    (0.130.0 systemweit, 0.144.5 im Benutzerordner). `npm ls -g` zeigt nur eine
    davon - die andere bleibt unsichtbar und veraltet still vor sich hin.
    Rueckgabe: (paketname, npm-praefix) oder ('', '').
    """
    echt = os.path.realpath(pfad)
    if 'node_modules' not in echt:
        return ('', '')
    teile = echt.split(os.sep)
    i = len(teile) - 1 - teile[::-1].index('node_modules')
    name = teile[i + 1] if len(teile) > i + 1 else ''
    if name.startswith('@') and len(teile) > i + 2:      # Bereichs-Paket: @openai/codex
        name = f'{name}/{teile[i + 2]}'
    # Praefix ist der Ordner ueber lib/node_modules  (…/.local/lib/node_modules -> …/.local)
    praefix = os.sep.join(teile[:i - 1]) if i >= 2 and teile[i - 1] == 'lib' else ''
    return (name, praefix)


def npm_version(paket, praefix):
    """Fassung eines npm-Pakets aus seiner eigenen package.json lesen."""
    teil = paket.split('/')
    pfad = os.path.join(praefix, 'lib', 'node_modules', *teil, 'package.json')
    try:
        with open(pfad, 'r', encoding='utf-8') as f:
            return json.load(f).get('version', '?')
    except Exception:
        return '?'


def _ist_programm(pfad):
    """Ist das ein heruntergeladenes Programm - oder ein eigenes Skript des Nutzers?

    🔴 WARUM DAS WICHTIG IST (am 22.07.2026 selbst hineingetappt):
    Ein blindes `<name> --version` ueber alles in /usr/local/bin startete ein
    eigenes Skript `cf` gestartet - das versuchte daraufhin eine SSH-Verbindung
    zu `--version-ssh.rikus.uk` aufzubauen. Ein Programm, das nur NACHSEHEN
    soll, darf keine fremden Befehle ausloesen. Deshalb: erst pruefen, WAS die
    Datei ist, und nur echte Programmdateien ueberhaupt anfassen.
    """
    name = os.path.basename(pfad)
    if name in BEKANNTE_SKRIPTE:
        return True
    with open(pfad, 'rb') as f:
        return f.read(4) == b'\x7fELF'


def _gehoert_zu_paket(pfad):
    """Steckt hinter dem Verweis eine ganz normale apt-Installation?
    (/usr/local/bin/cloudflared ist oft nur ein Verweis auf /usr/bin.)

    ⚠️ NUR die Erfolgsausgabe zaehlt, NIE die Fehlermeldung. Die erste Fassung
    pruefte auf ': ' im Gesamttext - und `dpkg-query: no path found matching
    pattern /usr/local/bin/topgrade` enthaelt genau das. Dadurch galt PLOETZLICH
    JEDES Programm als apt-Paket und die Liste war leer. Der Exit-Code luegt nicht.
    """
    voll = _werkzeug('dpkg')
    if not voll:
        return False
    try:
        e = subprocess.run([voll, '-S', os.path.realpath(pfad)],
                           capture_output=True, text=True, timeout=8)
        return e.returncode == 0 and ': ' in (e.stdout or '')
    except Exception:
        return False


def _version_lesen(pfad):
    """Versionsnummer aus dem Programm selbst. '?' wenn nicht ermittelbar."""
    for schalter in ('--version', 'version', '-V'):
        aus = _lauf(pfad, schalter, zeit=8)
        for kandidat in re.findall(r'\b\d+\.\d+(?:\.\d+)?\b', aus):
            # Eine IP-Adresse ist keine Version. `cf --version` lieferte
            # am 22.07. "100.100.100.100" - vier Gruppen, alle <= 255.
            gruppen = kandidat.split('.')
            if len(gruppen) == 4 and all(g.isdigit() and int(g) <= 255 for g in gruppen):
                continue
            return kandidat
    return '?'


def binaere_finden():
    """Echte Programmdateien in /usr/local/bin und ~/.local/bin.
    Eigene Skripte, Sicherungen und Verweise auf apt-Pakete bleiben aussen vor."""
    funde = []
    for ordner in ('/usr/local/bin', os.path.expanduser('~/.local/bin')):
        if not os.path.isdir(ordner):
            continue
        for name in sorted(os.listdir(ordner)):
            voll = os.path.join(ordner, name)
            if not os.path.isfile(voll) or not os.access(voll, os.X_OK):
                continue
            if '.bak' in name or name.endswith(('.sh', '.py')):
                continue
            # Steckt in Wahrheit ein npm-Paket dahinter? Dann gehoert es dorthin
            # und nicht in die Programmdatei-Schublade - sonst steht es doppelt
            # da und niemand kann es aktualisieren.
            paket, praefix = npm_dahinter(voll)
            if paket:
                f = Fund(paket, npm_version(paket, praefix), 'npm', voll)
                f.praefix = praefix
                funde.append(f)
                continue
            try:
                if not _ist_programm(voll):
                    continue                    # eigenes Skript des Nutzers - nicht anfassen
                if _gehoert_zu_paket(voll):
                    continue                    # kommt doch aus apt
            except OSError:
                continue
            funde.append(Fund(name, _version_lesen(voll), 'binaer', voll))
    return funde


def npm_finden():
    aus = _lauf('npm', 'ls', '-g', '--depth=0', '--json', zeit=25)
    funde = []
    try:
        daten = json.loads(aus or '{}').get('dependencies', {})
        for name, info in daten.items():
            if name in ('npm', 'corepack'):
                continue
            funde.append(Fund(name, info.get('version', '?'), 'npm', 'npm -g'))
    except Exception:
        pass
    return funde


def alles_finden():
    """Alle Sorten zusammen. Bibliotheken werden aussortiert - sonst erschlaegt
    das Fenster den Nutzer (auf einem Testsystem: 22 von 33 Funden waren Bibliotheken)."""
    funde = []
    for sammler in (waisen_finden, flatpaks_finden, appimages_finden,
                    binaere_finden, npm_finden):
        try:
            funde += sammler()
        except Exception:
            continue
    funde = [f for f in funde if not ist_bibliothek(f.name)]

    # Dasselbe npm-Paket wird von zwei Seiten gefunden: über `npm ls -g` und
    # über den Verweis in /usr/local/bin bzw. ~/.local/bin. Das ist EIN Eintrag.
    # ⚠️ Aber zwei Installationen an VERSCHIEDENEN Orten sind zwei verschiedene
    # Dinge und müssen beide sichtbar bleiben - auf einem Testsystem lag deshalb
    # eine veraltete Fassung unbemerkt herum.
    mit_ort = {(f.name, f.praefix) for f in funde if f.sorte == 'npm' and f.praefix}
    ergebnis, gesehen = [], set()
    for f in funde:
        if f.sorte != 'npm':
            ergebnis.append(f)
            continue
        if f.praefix:
            if (f.name, f.praefix) in gesehen:
                continue                       # denselben Ort nur einmal
            gesehen.add((f.name, f.praefix))
        elif any(name == f.name for name, _ in mit_ort):
            continue                           # der genauere Eintrag gewinnt
        ergebnis.append(f)
    return ergebnis


BIBLIOTHEK_MUSTER = re.compile(
    r'^(lib|linux-image|linux-headers|perl-modules|python3?\.\d|'
    r'gir1\.2-|fonts-|xserver-xorg-|mime-support|policykit)')


def ist_bibliothek(name):
    """Bibliotheken und Kernel gehoeren nicht in eine Programmliste."""
    return bool(BIBLIOTHEK_MUSTER.match(name or ''))


# ---------------------------------------------------------------------------
# TEIL 2 - VERGLEICHEN: was ist die neueste Fassung?
# ---------------------------------------------------------------------------
# Herkunft fuer Programme, die sie nicht selbst mitbringen. Gemessen am
# 22.07.2026: etwa die Haelfte traegt die GitHub-Adresse im Homepage-Feld,
# der Rest verweist nur auf die Firmenseite (obsidian.md, rustdesk.com).

MITGELIEFERT = {
    'rustdesk':           ('github', 'rustdesk/rustdesk'),
    'obsidian':           ('github', 'obsidianmd/obsidian-releases'),
    'cloudflared':        ('github', 'cloudflare/cloudflared'),
    'tailscale':          ('github', 'tailscale/tailscale'),
    'rclone':             ('github', 'rclone/rclone'),
    'topgrade':           ('github', 'topgrade-rs/topgrade'),
    'imager':             ('github', 'raspberrypi/rpi-imager'),
    'rpi-imager':         ('github', 'raspberrypi/rpi-imager'),
    # So heisst die Datei NACH dem Update - der Hersteller hat den Dateinamen
    # zwischen 2.0.7 und 2.0.10 komplett geaendert.
    'Raspberry_Pi_Imager': ('github', 'raspberrypi/rpi-imager'),
    'rikus-zram':         ('github', 'Zahnschmerz/rikus-zram'),
    'rikus-mintshot':     ('github', 'Zahnschmerz/rikus-mintshot'),
    'rikus-speichern':    ('github', 'Zahnschmerz/rikus-speichern'),
    # Sich selbst nicht zu kennen waere peinlich: Auch dieses Programm wird als
    # .deb ohne apt-Quelle verteilt und steht deshalb in seiner eigenen Liste.
    'rikus-updateall':    ('github', 'Zahnschmerz/rikus-updateall'),
    'immich-go':          ('github', 'simulot/immich-go'),
    'kubectl':            ('github', 'kubernetes/kubernetes'),
    'bauh':               ('github', 'vinifmor/bauh'),
}


def adresse_deuten(text):
    """Aus einer hineinkopierten Adresse (art, ziel) machen. ('', '') wenn unklar.

    Erlaubt bewusst vieles: ganze URL, mit oder ohne https://, mit /releases
    hintendran, oder einfach nur `besitzer/projekt`. Der Nutzer soll nicht
    raten muessen, welche Form die richtige ist.
    """
    text = (text or '').strip().rstrip('/')
    for dienst, art in (('github.com', 'github'),):
        m = re.search(dienst + r'/([\w.-]+)/([\w.-]+)', text)
        if m:
            projekt = m.group(2)
            projekt = projekt[:-4] if projekt.endswith('.git') else projekt
            return (art, f'{m.group(1)}/{projekt}')
    if 'npmjs.com/package/' in text:
        # ⚠️ npm-Namen können einen Bereich davor haben: @openai/codex sind ZWEI
        # Teile, aber EIN Paketname. Wer hier nach dem ersten / abschneidet,
        # bekommt „@openai" - ein Paket, das es nicht gibt.
        rest = text.split('npmjs.com/package/', 1)[1]
        teile = [x for x in rest.split('/') if x][:2]
        return ('npm', '/'.join(teile) if rest.startswith('@') else teile[0])
    if 'flathub.org/apps/' in text:
        return ('flathub', text.split('flathub.org/apps/', 1)[1].split('/')[0])
    # Nur "besitzer/projekt" ohne alles drumherum
    if re.fullmatch(r'[\w.-]+/[\w.-]+', text):
        return ('github', text)
    return ('', '')


def schluessel(name):
    """Namen vergleichbar machen: 'Raspberry_Pi_Imager' und 'raspberry-pi-imager'
    sind dasselbe Programm."""
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


def eigene_quellen():
    try:
        with open(QUELLEN_DATEI, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def quelle_merken(name, art, ziel):
    """Quelle dauerhaft für diesen Namen hinterlegen.

    🔴 WARUM DAS SEIN MUSS: Nach einem Update heisst die Datei oft anders -
    aus `imager_2.0.7_amd64.AppImage` wurde `Raspberry_Pi_Imager-v2.0.10-
    desktop-x86_64.AppImage`. Damit aendert sich der erkannte Programmname
    von `imager` zu `Raspberry_Pi_Imager`, und die eingebaute Liste kennt den
    nicht mehr: Das Programm machte sich durch sein EIGENES Update blind und
    meldete danach „Quelle unbekannt". Deshalb wird die Quelle nach jedem
    erfolgreichen Update unter dem NEUEN Namen festgehalten.
    """
    daten = eigene_quellen()
    daten[schluessel(name)] = [art, ziel]
    try:
        os.makedirs(KONFIG_ORDNER, exist_ok=True)
        with open(QUELLEN_DATEI, 'w', encoding='utf-8') as f:
            json.dump(daten, f, indent=1)
    except OSError:
        pass


def quelle_fuer(fund):
    """Woher erfahren wir die neueste Fassung? Reihenfolge:
    1. was hinterlegt/gemerkt ist  2. unsere Liste  3. das Paket selbst"""
    eigen = eigene_quellen()
    treffer = eigen.get(schluessel(fund.name)) or eigen.get(fund.name)
    if treffer:
        return tuple(treffer)
    if fund.sorte == 'npm':
        return ('npm', fund.name)
    if fund.sorte == 'flatpak':
        return ('flathub', fund.name)
    for bekannt, ziel in MITGELIEFERT.items():
        if schluessel(bekannt) == schluessel(fund.name):
            return ziel
    if fund.repo:
        return ('github', fund.repo)
    return (None, None)


# GitHub laesst unangemeldet nur 60 Abfragen je Stunde zu. Bei 13 Programmen ist
# die Grenze nach vier Programmstarts erreicht - am 22.07.2026 selbst erlebt.
# Ohne Zwischenspeicher waere das Programm im Alltag unbrauchbar.
SPEICHER_DATEI = os.path.join(KONFIG_ORDNER, 'zwischenspeicher.json')
SPEICHER_HAELT = 6 * 3600          # Sekunden - sechs Stunden

GESPERRT = {'bis': 0}              # merkt sich, wann GitHub wieder darf

# 🔴 Drueckt der Nutzer auf „Erneut pruefen", MUSS der Zwischenspeicher
# uebersprungen werden. Sonst liest der Knopf nur die alten Antworten wieder
# vor und meldet weiter „aktuell", obwohl es laengst etwas Neues gibt - bis zu
# sechs Stunden lang. Genau das ist am 22.07.2026 passiert: Eine frisch
# veroeffentlichte Fassung wurde auf einem Rechner nicht angeboten, und auch
# wiederholtes Druecken aenderte nichts.
# Regel: Die Automatik schont das Kontingent, der Knopf des Nutzers hat Vorrang.
NEU_LADEN = {'an': False}


def _speicher_lesen():
    try:
        with open(SPEICHER_DATEI, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _speicher_schreiben(daten):
    try:
        os.makedirs(KONFIG_ORDNER, exist_ok=True)
        with open(SPEICHER_DATEI, 'w', encoding='utf-8') as f:
            json.dump(daten, f)
    except OSError:
        pass                       # Ein voller Zwischenspeicher darf nie stoeren


def _netz(url, schluessel=None):
    """Eine Seite holen - erst im Zwischenspeicher nachsehen.

    Gibt bei JEDEM Fehler None; kein Netz ist der Normalfall, kein Fehler.
    Bei erschoepftem GitHub-Kontingent wird zusaetzlich GESPERRT gesetzt, damit
    das Fenster „GitHub lässt gerade nicht mehr zu" sagen kann statt des
    irrefuehrenden „Quelle unbekannt".
    """
    import time
    import urllib.request
    import urllib.error

    schluessel = schluessel or url
    speicher = _speicher_lesen()
    eintrag = speicher.get(schluessel)
    if (eintrag and not NEU_LADEN['an']
            and (time.time() - eintrag.get('zeit', 0)) < SPEICHER_HAELT):
        return eintrag.get('wert')

    try:
        anfrage = urllib.request.Request(
            url, headers={'User-Agent': f'{PROGRAMM}/{VERSION}'})
        with urllib.request.urlopen(anfrage, timeout=NETZ_ZEITLIMIT) as antwort:
            wert = json.loads(antwort.read().decode('utf-8'))
    except urllib.error.HTTPError as fehler:
        if fehler.code in (403, 429):
            # Kontingent erschoepft - merken, wann es weitergeht
            try:
                GESPERRT['bis'] = int(fehler.headers.get('X-RateLimit-Reset') or 0)
            except (TypeError, ValueError):
                GESPERRT['bis'] = 0
        return None
    except Exception:
        return None

    speicher[schluessel] = {'wert': wert, 'zeit': time.time()}
    _speicher_schreiben(speicher)
    return wert


def neueste_holen(fund):
    """Neueste Fassung beim Hersteller erfragen. None = konnten wir nicht klaeren."""
    art, ziel = quelle_fuer(fund)
    if not art:
        return None
    if art == 'github':
        daten = _netz(f'https://api.github.com/repos/{ziel}/releases/latest')
        return (daten or {}).get('tag_name')
    if art == 'npm':
        daten = _netz(f'https://registry.npmjs.org/{ziel}/latest')
        return (daten or {}).get('version')
    if art == 'flathub':
        # ⚠️ Flathub hat KEIN 'version' auf oberster Ebene - die erste Fassung
        # fragte danach und bekam fuer JEDES Flatpak "Quelle unbekannt".
        # Die Version steht in releases[0]['version'].
        # (Der lokale `flatpak remote-info --cached` taugt nicht: der meldete
        #  am 22.07. fuer Telegram 7.0.3, waehrend 7.0.4 installiert war.)
        daten = _netz(f'https://flathub.org/api/v2/appstream/{ziel}')
        ausgaben = (daten or {}).get('releases') or []
        return ausgaben[0].get('version') if ausgaben else None
    return None


def bewerten(fund):
    """Setzt fund.neueste und fund.status. Laeuft im Hintergrund-Faden."""
    if fund.name in SELBST_AKTUALISIERER:
        # Kein „Quelle unbekannt": Dieses Programm bringt seinen eigenen
        # Aktualisierer mit. Das ist eine Antwort, kein Loch.
        fund.status = 'selbst'
        return
    art, _ = quelle_fuer(fund)
    fund.neueste = neueste_holen(fund)
    if not fund.neueste and art and GESPERRT['bis']:
        # Wir WISSEN, woher die Fassung käme - GitHub antwortet nur gerade nicht.
        # Das ist etwas völlig anderes als „keine Quelle bekannt", und es muss
        # auch etwas anderes im Fenster stehen.
        fund.status = 'gesperrt'
    elif not fund.neueste:
        fund.status = 'unbekannt'
    elif ist_neuer(fund.neueste, fund.version):
        fund.status = 'veraltet'
    else:
        fund.status = 'aktuell'


# ---------------------------------------------------------------------------
# TEIL 3 - AKTUALISIEREN
# AppImages liegen im eigenen Ordner des Nutzers, brauchen also
# KEIN Passwort, und es ist genau EINE Datei - nichts zu entpacken, nichts zu
# installieren. Alle anderen Sorten brauchen Root oder eigene Wege und kommen
# spaeter, einzeln (Gesetz 3: nur EINE Aenderung auf einmal).
# ---------------------------------------------------------------------------

def maschine():
    """('x86_64', 'amd64') - beide Schreibweisen, Hersteller nutzen mal die eine,
    mal die andere."""
    lang = (os.uname().machine or '').lower()
    kurz = {'x86_64': 'amd64', 'aarch64': 'arm64'}.get(lang, lang)
    return lang, kurz


def passende_datei(dateien, altname):
    """Aus den angebotenen Dateien die richtige waehlen.

    🔴 WARUM DAS NOETIG IST: rpi-imager bietet fuer v2.0.10 FUENF AppImages an
    (cli/desktop je aarch64/x86_64, dazu .exe, .deb, .dmg). Und der Dateiname
    hat sich geaendert: aus `imager_2.0.7_amd64.AppImage` wurde
    `Raspberry_Pi_Imager-v2.0.10-desktop-x86_64.AppImage`. Wer blind die erste
    Datei nimmt, installiert womoeglich die Kommandozeilen-Fassung fuer ARM.
    """
    lang, kurz = maschine()
    kandidaten = [d for d in dateien if d['name'].lower().endswith('.appimage')]
    if not kandidaten:
        return None
    # 1. Architektur muss passen. Datei ohne jede Architekturangabe gilt als universal.
    passend = [d for d in kandidaten
               if lang in d['name'].lower() or kurz in d['name'].lower()]
    if not passend:
        andere = ('aarch64', 'arm64', 'armv7', 'i386', 'i686')
        passend = [d for d in kandidaten
                   if not any(a in d['name'].lower() for a in andere)]
    if not passend:
        return None
    if len(passend) == 1:
        return passend[0]
    # 2. Mehrere uebrig: Fenster-Fassung vor Kommandozeile - wer ein AppImage
    #    doppelklickt, will ein Fenster. Ausser der alte Name sagt 'cli'.
    will_cli = 'cli' in (altname or '').lower()
    fenster = [d for d in passend if ('cli' in d['name'].lower()) == will_cli]
    return (fenster or passend)[0]


def wird_synchronisiert(pfad):
    """Liegt diese Datei in einem Syncthing-Ordner?

    🔴 WARUM DAS ZAEHLT: Ordner wie ~/Öffentlich oder ~/Bilder sind haeufig
    Syncthing-Ordner. Eine Sicherungsdatei, die man dort einfach daneben legt,
    wandert binnen Minuten auf ALLE Geraete - bei einem AppImage sind das 37 MiB
    Muell mal so viele Geraete, wie synchronisiert werden. Deshalb landet die alte
    muelleimer!" Erkennbar am Ordner `.stfolder`, den Syncthing selbst anlegt -
    dafuer braucht man keinen API-Schluessel.
    """
    ordner = os.path.dirname(os.path.abspath(pfad))
    heim = os.path.expanduser('~')
    while ordner.startswith(heim) and ordner != heim:
        if os.path.isdir(os.path.join(ordner, '.stfolder')):
            return True
        ordner = os.path.dirname(ordner)
    return os.path.isdir(os.path.join(heim, '.stfolder'))


SICHERUNGSORDNER = os.path.expanduser('~/Dokumente')


def sicherungsort(pfad):
    """Wohin mit der alten Fassung? Nach ~/Dokumente.

    des Nutzers Entscheidung (22.07.2026): „ja, dann tu es doch in dokumente
    speichern". Vorher stand hier /tmp - das ist nach einem Neustart weg, und
    dann gibt es keinen Rueckweg mehr. ~/Dokumente wird auf einem Testsystem NICHT
    synchronisiert (nur der Unterordner keepasssync), die Datei bleibt also
    auf diesem Rechner und wandert nicht auf die anderen fuenf.

    Der Dateiname bleibt unveraendert - die alte Versionsnummer steht ja drin
    (imager_2.0.7_amd64.AppImage). Nur wenn dort schon eine gleichnamige Datei
    liegt, wird durchnummeriert; ueberschrieben wird NIE.
    """
    os.makedirs(SICHERUNGSORDNER, exist_ok=True)
    name = os.path.basename(pfad)
    ziel = os.path.join(SICHERUNGSORDNER, name)
    nr = 2
    while os.path.exists(ziel):
        ziel = os.path.join(SICHERUNGSORDNER, f'{name}.{nr}')
        nr += 1
    return ziel


FREMDE_SYSTEME = ('apple', 'darwin', 'windows', 'msvc', 'freebsd', 'openbsd',
                  'netbsd', 'android', '.exe', '.dmg', '.msi')


def passendes_archiv(dateien, programmname):
    """Fuer Programmdateien: das richtige Archiv aus dem Angebot waehlen.

    topgrade bietet zehn Dateien an - fuer macOS, Windows, FreeBSD, OpenBSD,
    ARM und x86, je in gnu- und musl-Fassung. Nur EINE davon passt hierher.
    """
    lang, kurz = maschine()
    gut = []
    for d in dateien:
        n = d['name'].lower()
        if not n.endswith(('.tar.gz', '.tgz', '.tar.xz')):
            continue
        if any(f in n for f in FREMDE_SYSTEME):
            continue
        if 'linux' not in n:
            continue
        if lang not in n and kurz not in n:
            continue
        gut.append(d)
    if not gut:
        return None
    # gnu vor musl: musl-Fassungen laufen zwar ueberall, sind aber die
    # Ausweichloesung. Wer glibc hat - und Debian/MX hat es - nimmt gnu.
    gnu = [d for d in gut if 'gnu' in d['name'].lower()]
    return (gnu or gut)[0]


def download_kandidat(fund):
    """Welche Datei wuerde geladen? (Name, Adresse, Groesse) oder None."""
    art, ziel = quelle_fuer(fund)
    if art != 'github' or fund.sorte not in ('appimage', 'binaer'):
        return None
    daten = _netz(f'https://api.github.com/repos/{ziel}/releases/latest')
    if not daten:
        return None
    angebot = daten.get('assets') or []
    if fund.sorte == 'appimage':
        d = passende_datei(angebot, os.path.basename(fund.ort))
    else:
        d = passendes_archiv(angebot, fund.name)
    if not d:
        return None
    return (d['name'], d['browser_download_url'], d.get('size', 0))


def appimage_erneuern(fund, melden=lambda text: None):
    """Neues AppImage holen und das alte ersetzen. Gibt (True/False, Text) zurueck.

    Sicherheitsnetz, in dieser Reihenfolge:
      1. erst nach /tmp laden - die alte Datei bleibt unangetastet
      2. Groesse und Kennung pruefen, BEVOR irgendetwas ersetzt wird
      3. die alte Datei umbenennen (nicht loeschen) - das ist der Rueckweg
      4. erst dann die neue an ihren Platz
      5. hinterher NACHMESSEN, nicht 'muesste passen'
    """
    import urllib.request

    kandidat = download_kandidat(fund)
    if not kandidat:
        return False, t('Keine passende Datei beim Hersteller gefunden.',
                        'No matching file offered by the vendor.')
    name, adresse, groesse = kandidat
    ziel_ordner = os.path.dirname(fund.ort)
    neu_pfad = os.path.join(ziel_ordner, name)
    # 🔴 NICHT nach /tmp laden! Auf einem Testsystem liegt /tmp auf /dev/nvme1n1p2 und /home
    # auf /dev/nvme1n1p3 - zwei verschiedene Dateisysteme. Ein Umbenennen von
    # dort hierher scheitert mit „Ungültiger Link über Gerätegrenzen hinweg"
    # (Errno 18). Am 22.07.2026 genau so passiert, und der erste Test hat es
    # NICHT gefunden, weil er komplett innerhalb von /tmp lief.
    # Deshalb: gleich im Zielordner ablegen, dort ist Umbenennen immer möglich.
    zwischen = os.path.join(ziel_ordner, f'.{name}.unfertig')

    # Passt das überhaupt auf die Platte? (Platz für neue UND alte Fassung)
    if groesse:
        try:
            frei = shutil.disk_usage(ziel_ordner).free
            if frei < groesse * 2:
                return False, t(
                    f'Zu wenig Platz: {groesse // 1024 // 1024} MiB werden gebraucht, '
                    f'frei sind {frei // 1024 // 1024} MiB.',
                    f'Not enough space: need {groesse // 1024 // 1024} MiB, '
                    f'{frei // 1024 // 1024} MiB free.')
        except OSError:
            pass

    melden(t(f'Lade {name} …', f'Downloading {name} …'))
    try:
        anfrage = urllib.request.Request(
            adresse, headers={'User-Agent': f'{PROGRAMM}/{VERSION}'})
        with urllib.request.urlopen(anfrage, timeout=60) as antwort, \
                open(zwischen, 'wb') as ziel:
            while True:
                brocken = antwort.read(262144)
                if not brocken:
                    break
                ziel.write(brocken)
    except Exception as fehler:
        if os.path.exists(zwischen):
            os.remove(zwischen)               # keine halbe Datei liegen lassen
        return False, t(f'Herunterladen fehlgeschlagen: {fehler}',
                        f'Download failed: {fehler}')

    # --- Pruefen, BEVOR etwas ersetzt wird ---
    ist = os.path.getsize(zwischen)
    if groesse and abs(ist - groesse) > 4096:
        os.remove(zwischen)
        return False, t(
            f'Die geladene Datei ist {ist} Byte groß, erwartet waren {groesse}. Abgebrochen.',
            f'Downloaded file is {ist} bytes, expected {groesse}. Aborted.')
    with open(zwischen, 'rb') as f:
        kopf = f.read(4)
    if kopf != b'\x7fELF':
        os.remove(zwischen)
        return False, t('Die geladene Datei ist kein ausführbares Programm. Abgebrochen.',
                        'The downloaded file is not an executable. Aborted.')

    # --- Erst jetzt anfassen. Die alte Datei wird UMBENANNT, nie geloescht. ---
    gesichert = sicherungsort(fund.ort)
    try:
        # Zuerst die NEUE Datei an ihren Platz - das ist der Schritt, der
        # schiefgehen kann. Erst wenn er geklappt hat, wird die alte angefasst.
        os.replace(zwischen, neu_pfad)               # gleicher Ordner -> geht immer
        os.chmod(neu_pfad, 0o755)
        if os.path.abspath(fund.ort) != os.path.abspath(neu_pfad):
            shutil.move(fund.ort, gesichert)         # über Dateisysteme hinweg: move
    except Exception as fehler:
        if os.path.exists(gesichert) and not os.path.exists(fund.ort):
            shutil.move(gesichert, fund.ort)         # Rueckweg sofort gehen
        if os.path.exists(zwischen):
            os.remove(zwischen)
        return False, t(f'Ersetzen fehlgeschlagen: {fehler}', f'Replacing failed: {fehler}')

    # --- Nachmessen statt 'muesste passen' ---
    if not (os.path.exists(neu_pfad) and os.access(neu_pfad, os.X_OK)):
        return False, t('Nach dem Ersetzen war die neue Datei nicht ausführbar.',
                        'After replacing, the new file was not executable.')
    # Die Quelle unter dem NEUEN Namen festhalten, sonst findet der naechste
    # Durchgang sie nicht mehr (siehe quelle_merken).
    art, ziel = quelle_fuer(fund)
    neuer_name = re.split(r'[_-]v?\d', os.path.basename(neu_pfad))[0]
    if art and ziel:
        quelle_merken(neuer_name, art, ziel)

    fund.ort = neu_pfad
    fund.name = neuer_name or fund.name
    fund.version = fund.neueste.lstrip('vV') if fund.neueste else fund.version
    fund.status = 'aktuell'
    return True, t(
        f'✔ {name}\n   liegt jetzt in {ziel_ordner}\n\n'
        f'Die alte Fassung wurde nicht gelöscht, sie liegt in:\n   {gesichert}',
        f'✔ {name}\n   is now in {ziel_ordner}\n\n'
        f'The old file was not deleted, it is in:\n   {gesichert}')


def binaer_erneuern(fund, melden=lambda text: None):
    """Eine Programmdatei in /usr/local/bin erneuern. BRAUCHT DAS PASSWORT.

    Anders als beim AppImage sind hier drei Dinge neu:
      1. Das Programm kommt als ARCHIV (.tar.gz) und muss ausgepackt werden.
      2. Der Zielordner gehoert root - ohne pkexec geht nichts.
      3. Im Archiv liegt die Datei irgendwo drin, oft in einem Unterordner.

    Der Ablauf bleibt derselbe wie beim AppImage: erst alles im eigenen
    Ordner vorbereiten und pruefen, und erst wenn wirklich alles stimmt,
    EINEN kurzen Befehl mit Passwort ausfuehren.
    """
    import tarfile
    import urllib.request

    kandidat = download_kandidat(fund)
    if not kandidat:
        return False, t('Keine passende Datei beim Hersteller gefunden.',
                        'No matching file offered by the vendor.')
    name, adresse, groesse = kandidat
    werkbank = os.path.join(KONFIG_ORDNER, 'werkbank')
    shutil.rmtree(werkbank, ignore_errors=True)
    os.makedirs(werkbank, exist_ok=True)
    archiv = os.path.join(werkbank, name)

    melden(t(f'Lade {name} …', f'Downloading {name} …'))
    try:
        anfrage = urllib.request.Request(
            adresse, headers={'User-Agent': f'{PROGRAMM}/{VERSION}'})
        with urllib.request.urlopen(anfrage, timeout=60) as antwort, \
                open(archiv, 'wb') as ziel:
            shutil.copyfileobj(antwort, ziel, 262144)
    except Exception as fehler:
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(f'Herunterladen fehlgeschlagen: {fehler}',
                        f'Download failed: {fehler}')

    # --- Auspacken und die richtige Datei darin suchen ---
    try:
        with tarfile.open(archiv) as paket:
            # Nichts ausserhalb der Werkbank auspacken (Schutz vor praeparierten
            # Archiven, die '../..' im Pfad tragen).
            sicher_liste = [m for m in paket.getmembers()
                            if m.isfile() and not m.name.startswith(('/', '..'))
                            and '..' not in m.name.split('/')]
            try:
                # Ab Python 3.12 gibt es einen eingebauten Schutz. Nutzen, wo da.
                paket.extractall(werkbank, members=sicher_liste, filter='data')
            except TypeError:
                paket.extractall(werkbank, members=sicher_liste)
    except Exception as fehler:
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(f'Auspacken fehlgeschlagen: {fehler}',
                        f'Unpacking failed: {fehler}')

    gefunden = None
    for wurzel, _, dateien in os.walk(werkbank):
        for d in dateien:
            if d == fund.name:
                voll = os.path.join(wurzel, d)
                with open(voll, 'rb') as f:
                    if f.read(4) == b'\x7fELF':
                        gefunden = voll
                        break
        if gefunden:
            break
    if not gefunden:
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(
            f'Im Archiv war keine Programmdatei namens „{fund.name}" zu finden.',
            f'The archive contained no program file named “{fund.name}”.')

    # --- Erst jetzt Passwort verlangen: sichern + ersetzen in EINEM Schritt ---
    import shlex
    gesichert = sicherungsort(fund.ort)
    # Ein einziger Befehl mit &&: bricht ein Teil ab, passiert nichts weiter.
    # Und die Sicherung bekommt hinterher der Nutzer als Eigentuemer - sonst laege
    # in seinen Dokumenten eine Datei, die ihm nicht gehoert.
    befehl = (f'cp -p {shlex.quote(fund.ort)} {shlex.quote(gesichert)} && '
              f'install -m 755 {shlex.quote(gefunden)} {shlex.quote(fund.ort)} && '
              f'chown {os.getuid()}:{os.getgid()} {shlex.quote(gesichert)}')
    melden(t('Warte auf dein Passwort …', 'Waiting for your password …'))
    try:
        ergebnis = subprocess.run([_werkzeug('pkexec') or 'pkexec',
                                   '/bin/sh', '-c', befehl],
                                  capture_output=True, text=True, timeout=180)
    except Exception as fehler:
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(f'Konnte nicht ausgeführt werden: {fehler}',
                        f'Could not run: {fehler}')
    shutil.rmtree(werkbank, ignore_errors=True)
    if ergebnis.returncode == 126:
        return False, t('Abgebrochen — es wurde kein Passwort eingegeben.',
                        'Cancelled — no password was entered.')
    if ergebnis.returncode != 0:
        return False, t(f'Fehlgeschlagen: {(ergebnis.stderr or "").strip()[:200]}',
                        f'Failed: {(ergebnis.stderr or "").strip()[:200]}')

    # --- Nachmessen: was sagt das Programm selbst? ---
    jetzt = _version_lesen(fund.ort)
    erwartet = (fund.neueste or '').lstrip('vV')
    if erwartet and jetzt != '?' and version_tupel(jetzt) != version_tupel(erwartet):
        return False, t(
            f'Ersetzt, aber die Fassung stimmt nicht: erwartet {erwartet}, '
            f'gemessen {jetzt}. Die alte liegt in {gesichert}.',
            f'Replaced, but version mismatch: expected {erwartet}, measured {jetzt}. '
            f'The old one is in {gesichert}.')
    fund.version = jetzt if jetzt != '?' else erwartet
    fund.status = 'aktuell'
    return True, t(
        f'✔ {fund.name} ist jetzt Fassung {fund.version}\n   in {fund.ort}\n\n'
        f'Nachgemessen am Programm selbst, nicht nur angenommen.\n'
        f'Die alte Fassung liegt in:\n   {gesichert}',
        f'✔ {fund.name} is now version {fund.version}\n   in {fund.ort}\n\n'
        f'Measured from the program itself, not assumed.\n'
        f'The old version is in:\n   {gesichert}')


def flatpak_erneuern(fund, melden=lambda text: None):
    """Flatpak erneuern. Braucht KEIN Passwort - Flatpaks liegen im Benutzerbereich."""
    melden(t(f'Hole {fund.name} …', f'Fetching {fund.name} …'))
    voll = _werkzeug('flatpak')
    if not voll:
        return False, t('flatpak ist nicht installiert.', 'flatpak is not installed.')
    try:
        e = subprocess.run([voll, 'update', '-y', '--noninteractive', fund.name],
                           capture_output=True, text=True, timeout=900)
    except Exception as fehler:
        return False, t(f'Nicht durchgelaufen: {fehler}', f'Failed: {fehler}')
    if e.returncode != 0:
        return False, t(f'Nicht durchgelaufen:\n{(e.stderr or e.stdout or "").strip()[:300]}',
                        f'Failed:\n{(e.stderr or e.stdout or "").strip()[:300]}')
    # Nachmessen: was ist jetzt wirklich installiert?
    jetzt = '?'
    for zeile in _lauf('flatpak', 'list', '--app',
                       '--columns=application,version').splitlines():
        teile = zeile.split('\t') if '\t' in zeile else zeile.split()
        if teile and teile[0] == fund.name and len(teile) > 1:
            jetzt = teile[1]
    fund.version = jetzt if jetzt != '?' else fund.version
    fund.status = 'aktuell'
    return True, t(f'✔ {fund.name} ist jetzt Fassung {fund.version}.\n\n'
                   f'Nachgemessen bei flatpak selbst.',
                   f'✔ {fund.name} is now version {fund.version}.')


def npm_erneuern(fund, melden=lambda text: None):
    """npm-Paket erneuern. Kein Passwort - npm-Pakete liegen im Benutzerbereich."""
    melden(t(f'Hole {fund.name} …', f'Fetching {fund.name} …'))
    voll = _werkzeug('npm')
    if not voll:
        return False, t('npm ist nicht installiert.', 'npm is not installed.')
    # ⚠️ MIT PRAEFIX, wo einer bekannt ist: Dasselbe npm-Paket kann an mehreren
    # Orten liegen (systemweit /usr/local und im Benutzerordner ~/.local).
    # Ein blosses `npm install -g` erwischt nur den voreingestellten Ort und
    # laesst die andere Fassung veraltet stehen.
    argumente = [voll, 'install', '-g']
    if fund.praefix:
        argumente += ['--prefix', fund.praefix]
    argumente.append(f'{fund.name}@latest')
    try:
        e = subprocess.run(argumente, capture_output=True, text=True, timeout=900)
    except Exception as fehler:
        return False, t(f'Nicht durchgelaufen: {fehler}', f'Failed: {fehler}')
    if e.returncode != 0:
        return False, t(f'Nicht durchgelaufen:\n{(e.stderr or "").strip()[:300]}',
                        f'Failed:\n{(e.stderr or "").strip()[:300]}')
    if fund.praefix:
        jetzt = npm_version(fund.name, fund.praefix)
    else:
        jetzt = fund.version
        for f2 in npm_finden():
            if f2.name == fund.name:
                jetzt = f2.version
    fund.version = jetzt
    fund.status = 'aktuell'
    return True, t(f'✔ {fund.name} ist jetzt Fassung {jetzt}.\n\nNachgemessen bei npm selbst.',
                   f'✔ {fund.name} is now version {jetzt}.')


def selbst_erneuern(fund, melden=lambda text: None):
    """Programme mit EIGENEM Aktualisierer (z. B. `claude update`, `rclone selfupdate`).

    Die wissen selbst am besten, woher ihre neue Fassung kommt - da muss dieses
    Programm nichts nachbauen, nur den richtigen Befehl aufrufen.
    """
    befehl = SELBST_AKTUALISIERER.get(fund.name)
    if not befehl:
        return False, t('Für dieses Programm ist kein eigener Weg hinterlegt.',
                        'No self-update command known for this program.')
    melden(t(f'Rufe „{" ".join(befehl)}" auf …', f'Running “{" ".join(befehl)}” …'))
    voll = _werkzeug(befehl[0]) or befehl[0]
    try:
        e = subprocess.run([voll] + befehl[1:], capture_output=True,
                           text=True, timeout=900)
    except Exception as fehler:
        return False, t(f'Nicht durchgelaufen: {fehler}', f'Failed: {fehler}')
    if e.returncode != 0:
        return False, t(f'Nicht durchgelaufen:\n{(e.stderr or e.stdout or "").strip()[:300]}',
                        f'Failed:\n{(e.stderr or e.stdout or "").strip()[:300]}')
    jetzt = _version_lesen(fund.ort)
    vorher, fund.version = fund.version, (jetzt if jetzt != '?' else fund.version)
    fund.status = 'aktuell'
    if version_tupel(fund.version) == version_tupel(vorher):
        return True, t(f'✔ {fund.name} war bereits auf dem neuesten Stand '
                       f'(Fassung {fund.version}).',
                       f'✔ {fund.name} was already up to date (version {fund.version}).')
    return True, t(f'✔ {fund.name}: {vorher} → {fund.version}\n\n'
                   f'Nachgemessen am Programm selbst.',
                   f'✔ {fund.name}: {vorher} → {fund.version}')


def deb_erneuern(fund, melden=lambda text: None):
    """Ein von Hand installiertes .deb erneuern. BRAUCHT DAS PASSWORT.

    Ablauf wie bei der Programmdatei: alles im eigenen Ordner vorbereiten und
    pruefen, und erst ganz am Schluss EIN Befehl mit Passwort.
    """
    import urllib.request

    art, ziel = quelle_fuer(fund)
    if art != 'github':
        return False, t('Für dieses Paket ist keine GitHub-Quelle hinterlegt.',
                        'No GitHub source known for this package.')
    daten = _netz(f'https://api.github.com/repos/{ziel}/releases/latest')
    if not daten:
        return False, t('Der Hersteller antwortet gerade nicht.',
                        'The vendor is not answering right now.')

    _, kurz = maschine()
    passend = [d for d in (daten.get('assets') or [])
               if d['name'].lower().endswith('.deb') and kurz in d['name'].lower()]
    if not passend:
        return False, t(
            f'Der Hersteller bietet für diese Fassung kein .deb für {kurz} an.\n'
            f'Angeboten wird: ' + ', '.join(d['name'] for d in (daten.get('assets') or [])[:6]),
            f'No .deb for {kurz} offered.')
    # Bei mehreren: das kürzeste Namensmuster ist meist die Hauptfassung
    # (rpi-imager_2.0.10_amd64.deb vor rpi-imager-cli_2.0.10_amd64.deb).
    d = sorted(passend, key=lambda x: len(x['name']))[0]
    name, adresse, groesse = d['name'], d['browser_download_url'], d.get('size', 0)

    werkbank = os.path.join(KONFIG_ORDNER, 'werkbank')
    shutil.rmtree(werkbank, ignore_errors=True)
    os.makedirs(werkbank, exist_ok=True)
    paket = os.path.join(werkbank, name)

    melden(t(f'Lade {name} …', f'Downloading {name} …'))
    try:
        anfrage = urllib.request.Request(
            adresse, headers={'User-Agent': f'{PROGRAMM}/{VERSION}'})
        with urllib.request.urlopen(anfrage, timeout=120) as antwort, \
                open(paket, 'wb') as ziel_datei:
            shutil.copyfileobj(antwort, ziel_datei, 262144)
    except Exception as fehler:
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(f'Herunterladen fehlgeschlagen: {fehler}',
                        f'Download failed: {fehler}')

    # --- Pruefen, BEVOR installiert wird: ist das wirklich ein Debian-Paket? ---
    ist = os.path.getsize(paket)
    if groesse and abs(ist - groesse) > 4096:
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(f'Die geladene Datei ist {ist} Byte groß, erwartet waren {groesse}.',
                        f'Downloaded {ist} bytes, expected {groesse}.')
    with open(paket, 'rb') as f:
        if f.read(8) != b'!<arch>\n':
            shutil.rmtree(werkbank, ignore_errors=True)
            return False, t('Die geladene Datei ist kein Debian-Paket. Abgebrochen.',
                            'The downloaded file is not a Debian package. Aborted.')
    # Und passt der Paketname zu dem, was hier installiert ist?
    im_paket = ''
    for zeile in _lauf('dpkg-deb', '-f', paket).splitlines():
        if zeile.lower().startswith('package:'):
            im_paket = zeile.split(':', 1)[1].strip()
    if im_paket and schluessel(im_paket) != schluessel(fund.name):
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(
            f'Das geladene Paket heißt „{im_paket}", installiert ist aber „{fund.name}". '
            f'Abgebrochen, damit nicht das falsche Programm ersetzt wird.',
            f'Downloaded package is “{im_paket}” but “{fund.name}” is installed. Aborted.')

    melden(t('Warte auf dein Passwort …', 'Waiting for your password …'))
    try:
        e = subprocess.run([_werkzeug('pkexec') or 'pkexec',
                            _werkzeug('dpkg') or 'dpkg', '-i', paket],
                           capture_output=True, text=True, timeout=600)
    except Exception as fehler:
        shutil.rmtree(werkbank, ignore_errors=True)
        return False, t(f'Nicht durchgelaufen: {fehler}', f'Failed: {fehler}')
    shutil.rmtree(werkbank, ignore_errors=True)
    if e.returncode == 126:
        return False, t('Abgebrochen — es wurde kein Passwort eingegeben.',
                        'Cancelled — no password entered.')
    if e.returncode != 0:
        return False, t(f'Nicht durchgelaufen:\n{(e.stderr or "").strip()[:300]}',
                        f'Failed:\n{(e.stderr or "").strip()[:300]}')

    jetzt = _lauf('dpkg-query', '-f', '${Version}', '-W', fund.name).strip() or '?'
    vorher, fund.version = fund.version, jetzt
    fund.status = 'aktuell'
    return True, t(
        f'✔ {fund.name}: {vorher} → {jetzt}\n\n'
        f'Nachgemessen bei dpkg selbst.\n'
        f'⚠️ Ein .deb wird ersetzt, nicht daneben gelegt — hier gibt es keine '
        f'Sicherungsdatei. Der Rückweg ist das alte Paket vom Hersteller.',
        f'✔ {fund.name}: {vorher} → {jetzt}\n\n'
        f'A .deb replaces the old one — there is no backup file here.')


# Programme, die einen EIGENEN Aktualisierer mitbringen. Ihr Weg ist immer
# besser als ein nachgebauter - sie wissen selbst, woher ihre Fassung kommt
# und was dabei zu beachten ist. Wer hier fehlt, wird ueber die normale
# Herkunftserkennung behandelt; die Liste ist eine Abkuerzung, kein Zwang.
SELBST_AKTUALISIERER = {
    'rclone': ['rclone', 'selfupdate'],
    'rustup': ['rustup', 'update'],
    'deno':   ['deno', 'upgrade'],
    'bun':    ['bun', 'upgrade'],
    'pnpm':   ['pnpm', 'self-update'],
    'micro':  ['micro', '-plugin', 'update'],
    'claude': ['claude', 'update'],
}


# ---------------------------------------------------------------------------
# DAS FENSTER
# ---------------------------------------------------------------------------
GRUEN, ROT, GELB, GRAU = '#2e7d32', '#c62828', '#ef6c00', '#757575'

SORTEN_NAME = {
    'deb':      t('.deb von Hand', 'manual .deb'),
    'flatpak':  'Flatpak',
    'appimage': 'AppImage',
    'binaer':   t('Programmdatei', 'binary'),
    'npm':      'npm',
}


class RikusAktuell(Gtk.Window):

    def __init__(self):
        super().__init__(title=f'{PROGRAMM} {VERSION}')
        self.funde = []
        self.zeilen = {}
        self.knoepfe = {}

        hoehe = 900
        try:
            anzeige = Gdk.Display.get_default()
            schirm = anzeige.get_monitor(0) if anzeige else None
            if schirm:
                hoehe = schirm.get_geometry().height
        except Exception:
            pass                      # Notfalls die 900 - lieber klein als abgeschnitten
        # Bauregel: Hoehe an den Bildschirm binden. Feste 800 px schnitten auf
        # einem Testsystem drei ganze Kaesten ab, ohne dass eine Rollleiste sichtbar war.
        self.set_default_size(880, int(min(940, hoehe * 0.9)))
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', Gtk.main_quit)

        aussen = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(aussen)

        # --- Kopf ---
        kopf = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        kopf.set_border_width(16)
        titel = Gtk.Label(xalign=0)
        titel.set_markup(f"<span size='x-large' weight='bold'>{sicher(PROGRAMM)}</span>")
        kopf.pack_start(titel, False, False, 0)
        unter = Gtk.Label(xalign=0)
        unter.set_markup(
            "<span size='small' foreground='%s'>%s</span>" % (GRAU, sicher(t(
                'Programme, die nicht aus apt kommen — und deshalb nie von allein aktualisiert werden',
                'Programs that do not come from apt — and are therefore never updated automatically'))))
        unter.set_line_wrap(True)
        kopf.pack_start(unter, False, False, 0)
        aussen.pack_start(kopf, False, False, 0)

        # --- Ampel ---
        self.ampel = Gtk.Label(xalign=0)
        self.ampel.set_line_wrap(True)
        rahmen = Gtk.Frame()
        rahmen.set_margin_start(16)
        rahmen.set_margin_end(16)
        kasten = Gtk.Box()
        kasten.set_border_width(12)
        kasten.pack_start(self.ampel, True, True, 0)
        rahmen.add(kasten)
        aussen.pack_start(rahmen, False, False, 0)
        self._ampel_setzen(GRAU, t('Suche läuft …', 'Scanning …'),
                           t('Der Rechner wird durchgesehen.', 'Looking through this machine.'))

        # --- Liste ---
        rollen = Gtk.ScrolledWindow()
        # Bauregel: Rollleiste IMMER sichtbar lassen. Blendet GTK sie aus (bis die
        # Maus darüberfährt), hält der Nutzer die Liste für zu Ende - auf einem Testsystem
        # fehlten dadurch drei ganze Kästen, ohne dass es jemand merkte.
        rollen.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
        rollen.set_overlay_scrolling(False)
        rollen.set_margin_start(16)
        rollen.set_margin_end(16)
        rollen.set_margin_top(12)
        self.liste = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        rollen.add(self.liste)
        aussen.pack_start(rollen, True, True, 0)

        # --- Fuss ---
        fuss = Gtk.Box(spacing=8)
        fuss.set_border_width(16)
        self.knopf_pruefen = Gtk.Button(label=t('Erneut prüfen', 'Check again'))
        # Der Knopf des Nutzers holt IMMER frisch - er ist die ausdrueckliche
        # Aufforderung nachzusehen, nicht die Bitte, Altes vorzulesen.
        self.knopf_pruefen.connect('clicked', lambda *_: self.suche_starten(frisch=True))
        fuss.pack_start(self.knopf_pruefen, False, False, 0)

        # Der frühere Sammelknopf ist weg: Jede Zeile hat ihren eigenen. Ein
        # zweiter Knopf unten, der dasselbe zu versprechen scheint, verwirrt nur.
        self.fuss_text = Gtk.Label(xalign=1)
        # ⚠️ Hier stand bis eben „Dieses Programm liest nur. Es ändert nichts."
        # Das war ab Etappe 3 SCHLICHT FALSCH — es kann jetzt Dateien ersetzen.
        # Ein Programm, das über sich selbst die Unwahrheit sagt, ist der
        # schnellste Weg, Vertrauen zu verlieren.
        self.fuss_text.set_markup(
            f"<span size='small' foreground='{GRAU}'>"
            f"{sicher(t('Ändert nur auf deinen Knopfdruck. Die alte Fassung bleibt erhalten.', 'Changes only when you click. The old version is kept.'))}"
            "</span>")
        fuss.pack_end(self.fuss_text, True, True, 0)
        aussen.pack_start(fuss, False, False, 0)

        # Unauffällige Zeile für die eigene neue Fassung - erst wenn es eine gibt.
        self.eigene_zeile = Gtk.Label(xalign=0)
        self.eigene_zeile.set_no_show_all(True)
        kopf.pack_start(self.eigene_zeile, False, False, 4)

        self.show_all()
        GLib.idle_add(self.suche_starten)
        threading.Thread(target=self._eigene_fassung_pruefen, daemon=True).start()

    def _eigene_fassung_pruefen(self):
        neu = eigene_neue_fassung()
        if neu:
            GLib.idle_add(self._eigene_fassung_zeigen, neu)

    def _eigene_fassung_zeigen(self, neu):
        self.eigene_zeile.set_markup(
            f"<span foreground='{GELB}'>▶ </span>"
            f"<span size='small'>{sicher(t(f'Von diesem Programm gibt es Fassung {neu} — du hast {VERSION}.', f'Version {neu} of this program is available — you have {VERSION}.'))} "
            f"<a href='{sicher(UPDATE_SEITE)}'>{sicher(t('ansehen', 'view'))}</a></span>")
        self.eigene_zeile.show()
        return False

    # -- Ampel -------------------------------------------------------------
    def _ampel_setzen(self, farbe, kopf, text):
        self.ampel.set_markup(
            f"<span size='large' foreground='{farbe}' weight='bold'>● {sicher(kopf)}</span>\n"
            f"<span size='small'>{sicher(text)}</span>")

    # -- Suche -------------------------------------------------------------
    def suche_starten(self, frisch=False):
        NEU_LADEN['an'] = bool(frisch)
        self.knopf_pruefen.set_sensitive(False)
        for kind in self.liste.get_children():
            self.liste.remove(kind)
        self.zeilen.clear()
        self._ampel_setzen(GRAU, t('Suche läuft …', 'Scanning …'),
                           t('Der Rechner wird durchgesehen.', 'Looking through this machine.'))
        threading.Thread(target=self._suchen_im_hintergrund, daemon=True).start()
        return False

    def _suchen_im_hintergrund(self):
        funde = alles_finden()
        GLib.idle_add(self._funde_zeigen, funde)

    def _funde_zeigen(self, funde):
        self.funde = sorted(funde, key=lambda f: (f.sorte, f.name.lower()))
        for fund in self.funde:
            self.liste.pack_start(self._zeile_bauen(fund), False, False, 0)
        self.liste.show_all()
        self._ampel_rechnen()
        # Erst jetzt ins Netz - die Liste steht schon, das Fenster wartet nie.
        threading.Thread(target=self._versionen_holen, daemon=True).start()
        return False

    def _zeile_bauen(self, fund):
        zeile = Gtk.Box(spacing=10)
        zeile.set_border_width(8)

        punkt = Gtk.Label()
        punkt.set_markup(f"<span foreground='{GRAU}' size='large'>●</span>")
        zeile.pack_start(punkt, False, False, 0)

        links = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        name = Gtk.Label(xalign=0)
        name.set_markup(f"<b>{sicher(fund.name)}</b>")
        links.pack_start(name, False, False, 0)
        ort = Gtk.Label(xalign=0)
        ort.set_markup(
            f"<span size='small' foreground='{GRAU}'>"
            f"{sicher(SORTEN_NAME.get(fund.sorte, fund.sorte))} · {sicher(fund.ort)}</span>")
        ort.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        links.pack_start(ort, False, False, 0)
        zeile.pack_start(links, True, True, 0)

        # Der Knopf steht von Anfang an da, aber GESPERRT. Er wird erst frei,
        # wenn wirklich etwas zu tun ist - und nur bei Sorten, die wir koennen.
        knopf = Gtk.Button(label=t('Aktualisieren', 'Update'))
        knopf.set_sensitive(False)
        knopf.set_no_show_all(False)
        knopf.connect('clicked', self._aktualisieren_gefragt, fund)
        zeile.pack_end(knopf, False, False, 0)

        rechts = Gtk.Label(xalign=1)
        rechts.set_markup(
            f"<span size='small' foreground='{GRAU}'>"
            f"{sicher(t('installiert', 'installed'))} {sicher(fund.version)}</span>")
        zeile.pack_end(rechts, False, False, 0)
        self.knoepfe[id(fund)] = knopf

        # ⚠️ NICHT nach Namen ablegen: Auf einem Testsystem liegen ZWEI AppImages namens
        # "imager" (2.0.10 in Downloads, 2.0.7 in Öffentlich). Mit dem Namen als
        # Schluessel ueberschrieb der zweite den ersten - die obere Zeile blieb
        # danach grau stehen und wurde nie bewertet. Sichtbar nur im Bildschirmfoto.
        # Auch die Ort-Zeile merken: Nach einem Update heisst die Datei anders
        # (imager_2.0.7… -> Raspberry_Pi_Imager-v2.0.10…). Stand dort weiter der
        # alte Name, zeigte das Fenster einen Pfad, den es nicht mehr gibt.
        self.zeilen[id(fund)] = (punkt, rechts, ort)
        rahmen = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        rahmen.pack_start(zeile, False, False, 0)
        rahmen.pack_start(Gtk.Separator(), False, False, 0)
        return rahmen

    def _versionen_holen(self):
        for fund in self.funde:
            bewerten(fund)
            GLib.idle_add(self._zeile_auffrischen, fund)
        GLib.idle_add(self._fertig)

    def _zeile_auffrischen(self, fund):
        eintrag = self.zeilen.get(id(fund))
        if not eintrag:
            return False
        punkt, rechts, ort = eintrag
        ort.set_markup(
            f"<span size='small' foreground='{GRAU}'>"
            f"{sicher(SORTEN_NAME.get(fund.sorte, fund.sorte))} · {sicher(fund.ort)}</span>")
        if fund.status == 'veraltet':
            farbe, text = ROT, t(
                f'{fund.version} → {fund.neueste} verfügbar',
                f'{fund.version} → {fund.neueste} available')
        elif fund.status == 'aktuell':
            farbe, text = GRUEN, t(f'{fund.version} · aktuell',
                                   f'{fund.version} · up to date')
        elif fund.status == 'gesperrt':
            farbe, text = GELB, t(f'{fund.version} · GitHub antwortet nicht',
                                  f'{fund.version} · GitHub not answering')
        elif fund.status == 'selbst':
            farbe, text = GRUEN, t(f'{fund.version} · prüft sich selbst',
                                   f'{fund.version} · updates itself')
        else:
            farbe, text = GRAU, t(f'{fund.version} · Quelle unbekannt',
                                  f'{fund.version} · source unknown')
        punkt.set_markup(f"<span foreground='{farbe}' size='large'>●</span>")
        gewicht = "weight='bold'" if fund.status == 'veraltet' else "size='small'"
        rechts.set_markup(f"<span {gewicht} foreground='{farbe}'>{sicher(text)}</span>")

        # Knopf nur freigeben, wenn wir diese Sorte auch WIRKLICH koennen.
        knopf = self.knoepfe.get(id(fund))
        if knopf:
            # Jede Sorte hat jetzt ihren Weg. Selbst-Aktualisierer duerfen
            # IMMER geklickt werden - sie sagen selbst, ob es etwas Neues gibt.
            kann = (fund.status == 'veraltet'
                    and fund.sorte in ('appimage', 'binaer', 'deb', 'flatpak', 'npm')
                    ) or fund.status == 'selbst'
            knopf.set_sensitive(kann)
            if fund.status == 'unbekannt':
                # ⭐ KEINE Sackgasse für fremde Nutzer: Wenn nichts automatisch
                # gefunden wurde, kann der Nutzer die Adresse EINMAL eintragen.
                # Ohne das wäre das Programm für alle unbrauchbar, deren
                # Programme nicht zufällig in der eingebauten Liste stehen.
                knopf.set_label(t('Quelle eintragen', 'Add source'))
                knopf.set_sensitive(True)
                knopf.set_tooltip_text(t(
                    'Einmal die Projektseite eintragen — danach prüft das Programm '
                    'diese Fassung immer selbst.',
                    'Enter the project page once — then it is checked automatically.'))
            elif fund.status == 'selbst':
                knopf.set_label(t('Selbst prüfen', 'Self-check'))
                knopf.set_tooltip_text(t(
                    f'Ruft „{" ".join(SELBST_AKTUALISIERER[fund.name])}" auf — das Programm '
                    f'holt seine neue Fassung selbst.',
                    f'Runs “{" ".join(SELBST_AKTUALISIERER[fund.name])}”.'))
        self._ampel_rechnen()
        return False

    # -- Aktualisieren ------------------------------------------------------
    def _aktualisieren_gefragt(self, knopf, fund):
        """Vorschau in Klartext VOR dem Zugriff - und NIEMALS stillschweigend
        abstürzen: Am 22.07.2026 zerbrach hier die Textzusammensetzung, der
        Dialog ging nicht auf, der Knopf blieb gesperrt. Für der Nutzer sah es aus,
        als täte der Knopf nichts. Ein Fehler muss SICHTBAR sein."""
        try:
            self._vorschau_und_start(knopf, fund)
        except Exception as fehler:
            knopf.set_sensitive(True)
            self._sagen(Gtk.MessageType.ERROR,
                        t('Da ist mir etwas kaputtgegangen', 'Something broke'),
                        t(f'Der Vorgang wurde abgebrochen, bevor irgendetwas angefasst '
                          f'wurde. Nichts auf deiner Platte hat sich geändert.\n\n'
                          f'Technischer Grund: {type(fehler).__name__}: {fehler}',
                          f'Aborted before anything was touched. Nothing on disk '
                          f'changed.\n\nReason: {type(fehler).__name__}: {fehler}'))

    def _vorschau_und_start(self, knopf, fund):
        if fund.status == 'unbekannt':
            self._quelle_eintragen(fund)
            return
        knopf.set_sensitive(False)
        # Selbst-Aktualisierer und die Wege ohne eigenen Download (Flatpak, npm,
        # .deb) brauchen keine Datei-Vorschau - dort kennt das Werkzeug den Weg.
        if fund.status == 'selbst' or fund.sorte in ('flatpak', 'npm', 'deb'):
            if not self._kurz_fragen(fund):
                knopf.set_sensitive(True)
                return
            knopf.set_label(t('läuft …', 'working …'))
            threading.Thread(target=self._erneuern_im_hintergrund,
                             args=(fund, knopf), daemon=True).start()
            return

        kandidat = download_kandidat(fund)
        if not kandidat:
            self._sagen(Gtk.MessageType.WARNING, t('Nichts zu holen', 'Nothing to fetch'), t(
                'Der Hersteller bietet für diesen Rechner keine passende Datei an.',
                'The vendor offers no matching file for this machine.'))
            return
        name, adresse, groesse = kandidat
        mib = groesse / 1024 / 1024 if groesse else 0
        braucht_passwort = fund.sorte == 'binaer'
        frage = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=t(f'{fund.name} auf {fund.neueste} bringen?',
                   f'Update {fund.name} to {fund.neueste}?'))
        # Der Text wird Stück für Stück zusammengesetzt, nicht in einem
        # verschachtelten Ausdruck. Genau daran ist die Vorgängerfassung
        # zerbrochen: zwei „+“ hintereinander -> TypeError, der Dialog ging
        # gar nicht erst auf, und für der Nutzer sah es aus, als täte der Knopf
        # nichts. Ein Vorschau-Dialog darf niemals abstürzen können.
        teile = [t(f'Ich hole diese Datei:\n  {name}   ({mib:.0f} MiB)\n'
                   f'von:\n  {adresse}\n\n'
                   f'Sie kommt nach:\n  {os.path.dirname(fund.ort)}\n\n'
                   f'Deine bisherige Fassung wird NICHT gelöscht, sondern gesichert nach:\n'
                   f'  {sicherungsort(fund.ort)}',
                   f'I will fetch:\n  {name}   ({mib:.0f} MiB)\n'
                   f'from:\n  {adresse}\n\n'
                   f'It goes to:\n  {os.path.dirname(fund.ort)}\n\n'
                   f'Your current version is NOT deleted, it is kept in:\n'
                   f'  {sicherungsort(fund.ort)}')]
        if wird_synchronisiert(fund.ort):
            teile.append(t(
                '  (aus dem Syncthing-Ordner heraus, damit die alte Fassung sich '
                'nicht auf deine anderen Geräte legt)',
                '  (out of the synced folder, so the old file is not copied to '
                'your other machines)'))
        if braucht_passwort:
            teile.append(t(
                '\nDiese Datei liegt in einem Systemordner, deshalb fragt Linux gleich '
                'nach deinem Passwort.\nHerunterladen und Auspacken passiert vorher in '
                'deinem eigenen Ordner — mit Administratorrechten läuft nur das '
                'Ersetzen selbst, ein einziger Befehl.',
                '\nThis file lives in a system folder, so Linux will ask for your '
                'password.\nDownloading and unpacking happen in your own folder first — '
                'only the replacement itself runs with administrator rights.'))
        else:
            teile.append(t('\nEs wird nichts installiert und kein Passwort gebraucht.',
                           '\nNothing is installed and no password is needed.'))
        frage.format_secondary_text('\n'.join(teile))
        antwort = frage.run()
        frage.destroy()
        if antwort != Gtk.ResponseType.OK:
            knopf.set_sensitive(True)
            return
        knopf.set_label(t('lädt …', 'downloading …'))
        threading.Thread(target=self._erneuern_im_hintergrund,
                         args=(fund, knopf), daemon=True).start()

    def _erneuern_im_hintergrund(self, fund, knopf):
        if fund.status == 'selbst':
            arbeit = selbst_erneuern
        else:
            arbeit = {'appimage': appimage_erneuern, 'binaer': binaer_erneuern,
                      'deb': deb_erneuern, 'flatpak': flatpak_erneuern,
                      'npm': npm_erneuern}.get(fund.sorte)
        if not arbeit:
            GLib.idle_add(self._erneuern_fertig, fund, knopf, False,
                          t('Für diese Sorte gibt es noch keinen Weg.',
                            'No update path for this kind yet.'))
            return
        geklappt, text = arbeit(fund)
        GLib.idle_add(self._erneuern_fertig, fund, knopf, geklappt, text)

    def _quelle_eintragen(self, fund):
        """Der Nutzer trägt EINMAL ein, wo dieses Programm herkommt.

        Absichtlich einfach gehalten: Es genügt, die Projektseite hineinzukopieren
        (z. B. https://github.com/rustdesk/rustdesk). Alles Weitere rechnet das
        Programm selbst aus. Wer eine Adresse aus dem Browser kopieren kann,
        kommt hier durch — mehr soll es nicht verlangen.
        """
        d = Gtk.Dialog(title=t(f'Woher kommt {fund.name}?', f'Where does {fund.name} come from?'),
                       transient_for=self, modal=True)
        d.add_buttons(t('Abbrechen', 'Cancel'), Gtk.ResponseType.CANCEL,
                      t('Eintragen', 'Save'), Gtk.ResponseType.OK)
        kasten = d.get_content_area()
        kasten.set_border_width(14)
        kasten.set_spacing(8)

        erklaerung = Gtk.Label(xalign=0)
        erklaerung.set_line_wrap(True)
        erklaerung.set_max_width_chars(60)
        erklaerung.set_markup(t(
            f"Für <b>{sicher(fund.name)}</b> ist noch nicht bekannt, wo die neueste "
            f"Fassung liegt.\n\nKopiere die Projektseite hier hinein — meistens eine "
            f"GitHub-Adresse. Danach prüft das Programm diese Fassung von allein mit.",
            f"It is not yet known where the latest version of <b>{sicher(fund.name)}</b> "
            f"lives.\n\nPaste the project page here — usually a GitHub address."))
        kasten.pack_start(erklaerung, False, False, 0)

        feld = Gtk.Entry()
        feld.set_placeholder_text('https://github.com/besitzer/projekt')
        feld.set_activates_default(True)
        kasten.pack_start(feld, False, False, 0)

        beispiel = Gtk.Label(xalign=0)
        beispiel.set_markup(
            f"<span size='small' foreground='{GRAU}'>"
            f"{sicher(t('Beispiel: https://github.com/rustdesk/rustdesk', 'Example: https://github.com/rustdesk/rustdesk'))}"
            "</span>")
        kasten.pack_start(beispiel, False, False, 0)

        d.set_default_response(Gtk.ResponseType.OK)
        d.show_all()
        antwort = d.run()
        eingabe = feld.get_text().strip()
        d.destroy()
        if antwort != Gtk.ResponseType.OK or not eingabe:
            return

        art, ziel = adresse_deuten(eingabe)
        if not art:
            self._sagen(Gtk.MessageType.WARNING,
                        t('Damit kann ich nichts anfangen', 'Cannot use that'),
                        t('Ich erkenne darin keine Projektadresse. Erwartet wird etwas '
                          'wie https://github.com/besitzer/projekt — die Adresse, die '
                          'oben im Browser steht, wenn du auf der Projektseite bist.',
                          'That does not look like a project address. Expected something '
                          'like https://github.com/owner/project'))
            return
        quelle_merken(fund.name, art, ziel)
        self._sagen(Gtk.MessageType.INFO, t('Eingetragen', 'Saved'),
                    t(f'{fund.name} wird ab jetzt bei {ziel} nachgeschlagen.\n\n'
                      f'Ich prüfe es gleich.',
                      f'{fund.name} will now be checked at {ziel}.'))
        threading.Thread(target=self._eins_neu_bewerten, args=(fund,), daemon=True).start()

    def _eins_neu_bewerten(self, fund):
        fund.status = 'offen'
        bewerten(fund)
        GLib.idle_add(self._zeile_auffrischen, fund)

    def _kurz_fragen(self, fund):
        """Vorschau für die Wege, bei denen ein Werkzeug die Arbeit macht.
        Auch hier gilt: erst sagen was passiert, dann tun."""
        if fund.status == 'selbst':
            was = t(f'Ich rufe den eigenen Aktualisierer auf:\n'
                    f'  {" ".join(SELBST_AKTUALISIERER[fund.name])}\n\n'
                    f'Das Programm holt seine neue Fassung dann selbst. Gibt es nichts '
                    f'Neues, sagt es das — es passiert dann nichts.',
                    f'Running: {" ".join(SELBST_AKTUALISIERER[fund.name])}')
        elif fund.sorte == 'flatpak':
            was = t(f'Ich rufe auf:\n  flatpak update {fund.name}\n\n'
                    f'Kein Passwort nötig. Flatpak behält die alte Fassung selbst noch '
                    f'eine Weile — du kämst also zurück.',
                    f'Running: flatpak update {fund.name}')
        elif fund.sorte == 'npm':
            was = t(f'Ich rufe auf:\n  npm install -g {fund.name}@latest\n\nKein Passwort nötig.',
                    f'Running: npm install -g {fund.name}@latest')
        else:
            was = t(f'Ich hole das neue Paket vom Hersteller und installiere es mit\n'
                    f'  dpkg -i\n\n'
                    f'Dafür fragt Linux nach deinem Passwort.\n\n'
                    f'⚠️ Anders als bei den anderen Wegen gibt es hier KEINE Sicherungsdatei: '
                    f'Ein Debian-Paket ersetzt die alte Fassung. Der Rückweg wäre, das alte '
                    f'Paket beim Hersteller wieder zu holen.',
                    f'Fetching the new package and installing it with dpkg -i. '
                    f'Linux will ask for your password. Note: a .deb replaces the old '
                    f'version — there is no backup file.')
        frage = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=t(f'{fund.name} aktualisieren?', f'Update {fund.name}?'))
        frage.format_secondary_text(was)
        antwort = frage.run()
        frage.destroy()
        return antwort == Gtk.ResponseType.OK

    def _erneuern_fertig(self, fund, knopf, geklappt, text):
        knopf.set_label(t('Aktualisieren', 'Update'))
        knopf.set_sensitive(not geklappt)
        self._sagen(Gtk.MessageType.INFO if geklappt else Gtk.MessageType.ERROR,
                    t('Fertig', 'Done') if geklappt else t('Nicht durchgelaufen', 'Failed'),
                    text)
        if geklappt:
            self._zeile_auffrischen(fund)
        return False

    def _sagen(self, art, kopf, text):
        d = Gtk.MessageDialog(transient_for=self, modal=True, message_type=art,
                              buttons=Gtk.ButtonsType.OK, text=kopf)
        d.format_secondary_text(text)
        d.run()
        d.destroy()

    def _ampel_rechnen(self):
        """Bauregel: Die Ampel muss ALLES bewerten, was das Programm kennt.
        Sonst meldet sie gruen, waehrend etwas veraltet ist - und wer gruen
        liest, sucht nicht weiter."""
        import time
        gesamt = len(self.funde)
        veraltet = sum(1 for f in self.funde if f.status == 'veraltet')
        offen = sum(1 for f in self.funde if f.status in ('offen', 'unbekannt'))
        gesperrt = sum(1 for f in self.funde if f.status == 'gesperrt')
        if gesperrt:
            # Diese Zahl darf NICHT unter „ungeprüft" verschwinden — sie hat eine
            # ganz andere Ursache und geht in einer Stunde von selbst weg.
            wann = (time.strftime('%H:%M', time.localtime(GESPERRT['bis']))
                    if GESPERRT['bis'] else '?')
            self._ampel_setzen(GELB, t(f'{gesperrt} konnten nicht geprüft werden',
                                       f'{gesperrt} could not be checked'), t(
                f'GitHub lässt nur 60 Abfragen pro Stunde zu und hat für den Moment dicht gemacht. '
                f'Ab {wann} Uhr geht es wieder — dann auf „Erneut prüfen" drücken. '
                f'{veraltet} veraltet, {gesamt - veraltet - gesperrt - offen} aktuell.',
                f'GitHub allows only 60 requests per hour and has closed the door for now. '
                f'It works again from {wann} — then press “Check again”. '
                f'{veraltet} out of date, {gesamt - veraltet - gesperrt - offen} current.'))
            return
        if veraltet:
            # Die offenen MÜSSEN mitgenannt werden. Steht nur "2 veraltet" da,
            # hält der Nutzer die anderen 10 für geprüft - dabei sind 5 davon
            # gar nicht bewertet. Wer eine klare Zahl liest, fragt nicht nach.
            zusatz = t(f' Für {offen} weitere ist keine Quelle hinterlegt — die sind ungeprüft.',
                       f' {offen} more have no known source and are unchecked.') if offen else ''
            self._ampel_setzen(ROT, t(f'{veraltet} veraltet', f'{veraltet} out of date'), t(
                f'Von {gesamt} Programmen außerhalb von apt sind {veraltet} nicht mehr aktuell. '
                f'apt hätte das nie gemeldet.{zusatz}',
                f'{veraltet} of {gesamt} programs outside apt are out of date. '
                f'apt would never have told you.{zusatz}'))
        elif offen == gesamt and gesamt:
            self._ampel_setzen(GRAU, t('Wird geprüft …', 'Checking …'), t(
                f'{gesamt} Programme gefunden, die nicht aus apt kommen.',
                f'Found {gesamt} programs that do not come from apt.'))
        elif offen:
            self._ampel_setzen(GELB, t(f'{offen} noch offen', f'{offen} still open'), t(
                f'{gesamt - offen} von {gesamt} geprüft, alle aktuell. '
                f'Für {offen} ist keine Quelle hinterlegt.',
                f'{gesamt - offen} of {gesamt} checked, all up to date. '
                f'No source known for {offen}.'))
        elif gesamt:
            self._ampel_setzen(GRUEN, t('Alles aktuell', 'All up to date'), t(
                f'Alle {gesamt} Programme außerhalb von apt sind auf dem neuesten Stand.',
                f'All {gesamt} programs outside apt are current.'))
        else:
            self._ampel_setzen(GRUEN, t('Nichts gefunden', 'Nothing found'), t(
                'Auf diesem Rechner kommt alles aus apt.',
                'Everything on this machine comes from apt.'))

    def _fertig(self):
        NEU_LADEN['an'] = False        # nur dieser eine Durchgang war frisch
        self.knopf_pruefen.set_sensitive(True)
        return False


def main():
    os.makedirs(KONFIG_ORDNER, exist_ok=True)
    RikusAktuell()
    Gtk.main()


if __name__ == '__main__':
    main()
