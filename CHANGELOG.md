# Änderungsprotokoll · Changelog

Alle nennenswerten Änderungen an Rikus Updateall.
All notable changes to Rikus Updateall.

## 1.7 — 22.07.2026

**Der vierte Weg, eine Quelle einzutragen: die feste Download-Adresse.**

* ⭐ **Programme ohne GitHub waren bisher eine Sackgasse.** Der Knopf „Quelle eintragen"
  nahm nur GitHub-, npm- und Flathub-Adressen an. Viele Hersteller — gerade Firmen —
  haben nichts davon, sondern legen unter einer **festen Adresse** immer das neueste
  Paket bereit (`https://launcher.mojang.com/download/Minecraft.deb`,
  `https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb`).
  Wer so eine Adresse eintrug, bekam „Damit kann ich nichts anfangen" — und hatte
  keine Möglichkeit mehr. Solche Adressen werden jetzt angenommen: Das Programm liest
  die Fassung aus dem Paket selbst ab und vergleicht sie mit der installierten.
* ⭐ **Dabei wird nicht das ganze Paket geladen.** Ein `.deb` ist ein Archiv, in dem
  die Paketangaben **ganz vorne** liegen. Es werden daher nur die ersten 256 KiB
  geholt (HTTP-Teilabruf). Gemessen an Google Chrome: **256 KiB statt 127 MiB — 0,2 %**,
  und die Fassung stand korrekt darin. Ohne das hätte jeder Programmstart für jede
  solche Zeile hunderte Megabyte geladen.
* 🔴 **„Das ist eine Webseite, keine Datei" statt „geht nicht".** Der häufigste Fall
  in der Praxis: Der Nutzer kopiert die Seite, auf der der Download-**Knopf** steht
  (z. B. `minecraft.net/download`) — völlig naheliegend, denn dort holt er das Programm
  ja auch selbst. Diese Adresse führt aber zu einer Seite zum Anschauen, nicht zu einer
  Datei. Statt einer Absage erklärt das Fenster jetzt den Weg zur richtigen Adresse:
  rechte Maustaste auf den Download-Knopf → „Link-Adresse kopieren".
* Sicherheitshalber wird geprüft, dass unter der Adresse wirklich ein Debian-Paket
  liegt (Archiv-Kennung), bevor irgendetwas ausgewertet wird — sonst würde eine
  HTML-Fehlerseite als Paketangabe gedeutet. Prüfsummen bietet ein Hersteller hier
  meist nicht an; das Programm sagt das ehrlich, statt zu schweigen.

---

**The fourth way to add a source: the fixed download address.**

* Programs without a GitHub project used to be a dead end — only GitHub, npm and
  Flathub addresses were accepted. Direct `.deb` addresses now work too: the version
  is read from the package itself.
* Only the first 256 KiB are fetched (HTTP range request), because a `.deb` keeps its
  package data at the very front. Measured on Google Chrome: 256 KiB instead of 127 MiB.
* Pasting a *web page* instead of a file address now explains how to get the right
  address, instead of just refusing.

## 1.6 — 22.07.2026

* 🔴 **Es wurde nach dem Passwort gefragt, wo keines noetig ist.** Der Vorschau-Dialog
  behauptete „Diese Datei liegt in einem Systemordner" — auch dann, wenn sie in
  `~/.local/bin` lag, also im eigenen Ordner des Nutzers. Gefunden am 22.07. auf pi5:
  cloudflared liegt dort als `pi:pi`, und trotzdem lief das Ersetzen ueber `pkexec`.
  Entschieden wird jetzt an der Wirklichkeit (Schreibrecht am Zielordner, `braucht_root()`),
  nicht pauschal an der Sorte. Ohne Root laeuft derselbe Befehl direkt — kein Passwort,
  kein falscher Satz.

## 1.5 — 22.07.2026

**Drei Fehler, die erst auf einem fremden Rechner (Raspberry Pi 5) sichtbar wurden.**

* 🔴 **Der Knopf „Aktualisieren" tat gar nichts — in 1.3 und 1.4.** Beim Einbau des
  Rückgängig-Knopfes in 1.3 war der Rumpf von `_vorschau_und_start` hinter das
  `return False` von `_zurueck_fertig` gerutscht: 67 Zeilen unerreichbarer Code.
  Übrig blieb `knopf.set_sensitive(False)` — der Knopf wurde grau, sonst passierte
  nichts. Das betraf **jede** Sorte (.deb, AppImage, Flatpak, npm, Programmdatei),
  nicht nur einen Sonderfall. Gefunden, weil Gilbert am 22.07. auf pi5 klickte und
  nichts geschah. Nicht früher gefunden, weil die Update-Wege einzeln aufgerufen
  statt über den Knopf geklickt wurden.
* 🔴 **Blanke Programmdateien wurden nie gefunden.** `passendes_archiv` verlangte
  `.tar.gz`/`.tgz`/`.tar.xz`. cloudflared bietet aber gar kein Archiv an, sondern
  die nackte Datei `cloudflared-linux-arm64` bzw. `-amd64`. Ergebnis auf **jedem**
  Rechner: „Keine passende Datei beim Hersteller gefunden." Jetzt werden Archive
  **und** blanke Dateien bedient; blanke werden vor dem Hinlegen auf die
  ELF-Kennung geprüft, damit keine Textdatei an die Stelle des Programms gerät.
  `binaer_erneuern` packt nur noch aus, wenn wirklich ein Archiv vorliegt.
* 🔴 **Die Installationsanleitung war falsch — an fünf Stellen.** Sie sagte
  `sudo apt install ./rikus-updateall_…deb`. Der Punkt-Schrägstrich heißt „in
  diesem Ordner"; wer ein Terminal öffnet, sitzt aber im Home-Ordner, nicht in
  `Downloads`. Ergebnis: `E: Nicht unterstützte Datei`. Jetzt steht überall der
  Doppelklick-Weg zuerst (wie bei Rikus Zram und Snapshot) und der Terminal-Befehl
  mit vollem Pfad. Ausgebessert in README.md, README.de.md, ANLEITUNG.md, GUIDE.md
  und auf updateall.rikus.info.

## 1.4 — 22.07.2026

### Deutsch
- 🔴 **Behoben: `.deb`-Pakete ohne Architektur im Namen wurden nicht gefunden.** Programme, die
  auf jedem Rechner laufen, heißen `…_all.deb` (manche Projekte schreiben `noarch`). Die Suche
  achtete nur auf die Architektur des Rechners (`amd64`) und fand deshalb gar nichts — das
  Programm konnte **nicht einmal sein eigenes Update holen**. Aufgefallen, als der `.deb`-Weg zum
  ersten Mal wirklich ausgelöst wurde.
- Gleichzeitig werden Pakete für fremde Architekturen jetzt ausdrücklich ausgeschlossen.

### English
- 🔴 **Fixed: `.deb` packages without an architecture in the name were never found.** Programs
  that run anywhere are named `…_all.deb` (some projects use `noarch`). The search only looked for
  the machine's architecture and therefore found nothing — the program could **not even fetch its
  own update**. Found when the `.deb` path was first actually exercised.
- Packages for foreign architectures are now explicitly excluded.

## 1.3 — 22.07.2026

### Deutsch
- **Rückgängig-Knopf.** Nach einer Aktualisierung steht in der Zeile ein Knopf *Rückgängig*, der
  die vorherige Fassung wieder an ihren Platz legt. Bisher lag sie zwar sicher in `~/Dokumente`,
  musste aber von Hand zurückgetragen werden.
- **Echtheitsprüfung.** Bietet der Hersteller eine Prüfsumme an (`.sha256` neben der Datei oder
  eine Sammeldatei wie `SHA256SUMS`), wird sie geholt und verglichen. Stimmt sie nicht, bricht
  das Programm ab, **bevor** irgendetwas ersetzt wird. Bisher wurden nur Dateigröße und Dateityp
  geprüft — das sagt nur, dass etwas ankam, nicht dass es das Richtige ist.
- Bietet ein Hersteller keine Prüfsumme an, steht das ehrlich im Ergebnis statt zu schweigen.

### English
- **Undo button.** After an update the row offers *Undo*, putting the previous version back.
- **Authenticity check.** If the vendor offers a checksum (`.sha256` beside the file or a
  collective file such as `SHA256SUMS`), it is fetched and compared. On mismatch the program
  aborts **before** replacing anything. Previously only size and file type were verified.
- If no checksum is offered, the result says so instead of staying silent.

## 1.2 — 22.07.2026

### Deutsch
- 🔴 **Behoben: „Erneut prüfen" holte nichts Neues.** Um GitHubs Abfragegrenze zu schonen, merkt
  sich das Programm Antworten sechs Stunden lang. Dieser Zwischenspeicher galt auch beim Druck auf
  *Erneut prüfen* — der Knopf las also nur die alten Antworten wieder vor und meldete weiter
  „aktuell", obwohl es längst eine neue Fassung gab. Jetzt gilt: **die Automatik schont das
  Kontingent, der Knopf des Nutzers holt immer frisch.**

### English
- 🔴 **Fixed: "Check again" fetched nothing new.** To respect GitHub's rate limit the program
  remembers answers for six hours. That cache also applied when the user pressed *Check again*,
  so the button merely re-read old answers and kept reporting "up to date" although a new version
  existed. Now: **the automatic check spares the quota, the user's button always fetches fresh.**

## 1.1 — 22.07.2026

### Deutsch
- Mehr Programme mit eigenem Aktualisierer erkannt: `rustup`, `deno`, `bun`, `pnpm`, `micro`
  (bisher nur `rclone` und `claude`). Diese Programme wissen selbst am besten, woher ihre neue
  Fassung kommt — ihr Weg ist immer besser als ein nachgebauter.
- Kommentare im Quelltext verallgemeinert, damit sie auf jedem Rechner gelten und nicht auf
  die Geräte des Entwicklers verweisen.

### English
- More programs with their own updater recognised: `rustup`, `deno`, `bun`, `pnpm`, `micro`
  (previously only `rclone` and `claude`). Those programs know best where their new version
  comes from — their own path always beats a rebuilt one.
- Source comments generalised so they apply on any machine.

## 1.0 — 22.07.2026

**Erste Fassung. / First release.**

### Deutsch
- Findet Programme außerhalb von apt: von Hand installierte `.deb`, AppImages, Flatpaks,
  Programmdateien in `/usr/local/bin` und `~/.local/bin`, npm-Pakete.
- Vergleicht jede Fassung mit der des Herstellers (GitHub, npm, Flathub).
- Aktualisiert alle sechs Sorten — mit Vorschau in Klartext, Prüfung vor dem Ersetzen,
  Aufbewahrung der alten Fassung und Nachmessung des Ergebnisses.
- Liest die Herkunft aus dem Programm selbst (Homepage- und Vcs-Felder, AppImage-Update-Angabe).
- Fehlt sie, kann sie einmalig eingetragen werden.
- Erkennt Programme mit eigenem Aktualisierer und ruft deren Weg auf.
- Sortiert aus, was nicht dazugehört: eigene Skripte des Nutzers, Bibliotheken, Karteileichen,
  den eigenen Sicherungsordner.
- Merkt Abfragen sechs Stunden lang und unterscheidet „keine Quelle bekannt" von
  „der Hersteller antwortet gerade nicht".
- Oberfläche deutsch und englisch, automatisch nach Systemeinstellung.

### English
- Finds programs outside apt: manually installed `.deb` files, AppImages, Flatpaks, program
  files in `/usr/local/bin` and `~/.local/bin`, npm packages.
- Compares each version against the vendor (GitHub, npm, Flathub).
- Updates all six kinds — with a plain-language preview, verification before replacing,
  the previous version kept, and the result measured afterwards.
- Reads a program's origin from the program itself (Homepage and Vcs fields, AppImage update
  information); if absent, the source can be entered once.
- Detects programs with their own updater and uses it.
- Filters out what does not belong: the user's own scripts, libraries, stale entries, and its
  own backup folder.
- Caches lookups for six hours and distinguishes "no source known" from "vendor not answering".
- Interface in German and English, chosen automatically.
