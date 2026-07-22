# Rikus Updateall — Anleitung

**Programme prüfen und aktualisieren, die nicht aus apt kommen.**

---

## 1. Worum geht es überhaupt?

Ihr Rechner hat eine Update-Verwaltung: `apt`. Die ist wie ein Hausarzt — sie kümmert sich um
alle Programme, die in ihrer Kartei stehen. Und sie macht das gut.

Aber: **Alles, was Sie sich woanders geholt haben, steht in dieser Kartei nicht drin.**

* eine `.deb`-Datei, die Sie von einer Webseite heruntergeladen haben
* ein AppImage, das in Ihrem Download-Ordner liegt
* ein Programm, das ein Installationsskript nach `/usr/local/bin` gelegt hat
* ein Paket, das Sie mit `npm` installiert haben

Diese Programme veralten **still**. Niemand sagt Ihnen etwas. Sie können Monate alt sein, ohne
dass es auffällt — mitsamt allen Sicherheitslücken, die inzwischen bekannt geworden sind.

**Rikus Updateall zeigt genau diese Programme — und bringt sie auf Wunsch auf den neuesten Stand.**

---

## 2. Voraussetzungen

Ein Linux mit Debian-Grundlage: Debian, Ubuntu, Linux Mint, MX Linux, antiX, Devuan und
Verwandte. Das Fenster braucht GTK 3, das ist auf all diesen Systemen ohnehin vorhanden.

Es läuft **mit und ohne systemd** — also auch auf MX Linux und antiX.

---

## 3. Installieren

Laden Sie die Datei `rikus-updateall_<Fassung>_all.deb` herunter und installieren Sie sie:

```
sudo apt install ./rikus-updateall_1.4_all.deb
```

Danach steht **Rikus Updateall** im Startmenü unter *System*.

Wieder entfernen:

```
sudo apt remove rikus-updateall
```

---

## 4. Was Sie im Fenster sehen

Oben eine **Ampel** mit einem Satz im Klartext: wie viele Programme außerhalb von apt gefunden
wurden und wie viele davon veraltet sind.

Darunter eine Liste. Jede Zeile hat einen farbigen Punkt:

| Punkt | Bedeutung |
|---|---|
| 🟢 grün | aktuell — beim Hersteller nachgefragt, es gibt nichts Neueres |
| 🔴 rot | veraltet — daneben steht, welche Fassung es gäbe |
| ⚫ grau | die Herkunft ist unbekannt, deshalb **ungeprüft** |
| 🟡 gelb | der Hersteller antwortet gerade nicht |

**Wichtig:** Grau heißt *nicht* „in Ordnung". Es heißt „ich konnte es nicht prüfen". Deshalb
bleibt die Ampel oben auch dann gelb, wenn alles Geprüfte aktuell ist — solange noch etwas
ungeprüft ist.

Unter jedem Namen steht, **um welche Sorte es sich handelt und wo die Datei liegt**. Das ist
wichtig, denn dasselbe Programm kann mehrfach auf einem Rechner liegen.

---

## 5. Ein Programm aktualisieren

Klicken Sie in der Zeile auf **Aktualisieren**.

**Vorher** erscheint immer ein Fenster im Klartext: welche Datei geholt wird, von welcher
Adresse, wohin sie kommt und wo Ihre bisherige Fassung bleibt. Erst wenn Sie dort auf *OK*
klicken, passiert etwas.

### Was dabei geschieht

1. Die neue Datei wird geholt — zunächst nur heruntergeladen, nichts wird ersetzt.
2. Sie wird **geprüft**: Stimmt die Größe mit der Angabe des Herstellers überein? Ist es
   überhaupt ein Programm bzw. ein Debian-Paket?
3. Erst dann wird ersetzt.
4. **Ihre bisherige Fassung wird nicht gelöscht**, sondern nach `~/Dokumente` gelegt.
5. Danach misst das Programm **nach**, welche Fassung nun wirklich installiert ist — und sagt
   es Ihnen. Es behauptet nicht einfach, es habe geklappt.

Geht unterwegs etwas schief, wird der vorherige Zustand wiederhergestellt.

### Brauche ich mein Passwort?

Nur, wenn die Datei in einem Systemordner liegt:

| Sorte | Passwort nötig? |
|---|---|
| AppImage | nein |
| Flatpak | nein |
| npm-Paket | nein |
| Programme mit eigenem Aktualisierer | nein |
| Programmdatei in `/usr/local/bin` | **ja** |
| `.deb`-Paket | **ja** |

Auch dann wird nur das Ersetzen selbst mit Administratorrechten ausgeführt. Herunterladen und
Auspacken passiert vorher in Ihrem eigenen Ordner.

> ⚠️ **Ausnahme bei `.deb`-Paketen:** Ein Debian-Paket ersetzt die alte Fassung; es kann keine
> Sicherungsdatei danebengelegt werden. Der Rückweg wäre, das ältere Paket beim Hersteller
> erneut zu holen. Im Vorschaufenster steht das ausdrücklich.

---

## 6. „Quelle unbekannt" — was tun?

Bei manchen Programmen steht in der Zeile *Quelle unbekannt* und daneben der Knopf
**Quelle eintragen**.

Das bedeutet: Das Programm konnte nicht herausfinden, wo die neueste Fassung liegt. Bei vielen
Programmen steht diese Angabe im Paket selbst — bei manchen aber nicht.

**Lösung:** Klicken Sie auf *Quelle eintragen*. Öffnen Sie die Projektseite des Programms im
Browser, kopieren Sie die Adresse aus der Adresszeile und fügen Sie sie in das Feld ein.

Alle diese Schreibweisen werden verstanden:

```
https://github.com/besitzer/projekt
github.com/besitzer/projekt
https://github.com/besitzer/projekt/releases/latest
besitzer/projekt
https://www.npmjs.com/package/paketname
https://flathub.org/apps/programm.kennung
```

Danach wird dieses Programm für immer mitgeprüft.

---

## 7. Häufige Fragen

**Warum bleibt die Ampel gelb, obwohl alles grün ist?**
Weil noch etwas ungeprüft ist. Eine Ampel, die grün zeigt, während etwas ungeprüft blieb, wäre
gefährlich: Wer grün liest, sucht nicht weiter.

**Warum steht mein Programm zweimal in der Liste?**
Weil es zweimal auf dem Rechner liegt — meist einmal systemweit und einmal in Ihrem
Benutzerordner. Das ist keine Anzeigefehler, sondern ein Fund. Häufig ist eine der beiden
Fassungen uralt und niemand hat es gemerkt.

**Warum taucht mein eigenes Skript nicht auf?**
Absicht. Das Programm fasst nur echte Programmdateien an, keine selbstgeschriebenen Skripte.
Es soll Ihre Werkzeuge weder prüfen noch versehentlich starten.

**Es sagt „GitHub antwortet nicht" — ist etwas kaputt?**
Nein. GitHub erlaubt ohne Anmeldung 60 Abfragen pro Stunde. Wird das erreicht, steht in der
Meldung, ab wann es weitergeht. Die Ergebnisse werden sechs Stunden lang gemerkt, damit das
selten passiert.

**Verändert das Programm etwas von allein?**
Nein. Es liest, vergleicht und wartet. Verändert wird ausschließlich, was Sie anklicken und
im Vorschaufenster bestätigen.

**Kann ich den Hinweis auf neue Fassungen des Programms selbst abschalten?**
Ja:
```
touch ~/.config/rikus-updateall/kein-update-hinweis
```
Danach wird gar nicht mehr danach gefragt.

**Wo werden meine Einstellungen gespeichert?**
In `~/.config/rikus-updateall/` — die eingetragenen Quellen in `quellen.json`, die gemerkten
Abfragen in `zwischenspeicher.json`. Beides sind einfache Textdateien.

---

## 8. Wenn etwas schiefgeht

Das Programm bricht bei einem Fehler ab, **bevor** es etwas anfasst, und sagt Ihnen das in
einem Fenster. Ihre Dateien bleiben, wie sie waren.

Ihre vorherigen Fassungen liegen in `~/Dokumente` und behalten ihren ursprünglichen Namen —
die Versionsnummer steht meist darin. Zurück kommen Sie, indem Sie die Datei wieder an ihren
alten Platz legen.

---

*Rikus Updateall — von Gilbert Rikus*
