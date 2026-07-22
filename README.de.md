# Rikus Updateall

**Findet die Programme, die nicht aus apt kommen — und hält sie aktuell.**

`apt` kennt nur Pakete aus den eingetragenen Quellen. Alles von Hand Installierte veraltet
still: eine `.deb` von einer Webseite, ein AppImage im Download-Ordner, ein Programm in
`/usr/local/bin`, ein npm-Paket. Niemand sagt einem etwas.

Rikus Updateall zeigt genau diese Programme, fragt beim Hersteller nach der neuesten Fassung
und aktualisiert sie auf Knopfdruck.

## Was es kann

| Sorte | Aktualisieren | Passwort |
|---|---|---|
| `.deb` von Hand installiert | ✅ | ja |
| AppImage | ✅ | nein |
| Flatpak | ✅ | nein |
| Programmdatei in `/usr/local/bin` | ✅ | ja |
| npm-Paket | ✅ | nein |
| Programme mit eigenem Aktualisierer | ✅ | nein |

## Woher es die Herkunft kennt

Aus dem Programm selbst, wo immer das geht — `Homepage`- und `Vcs`-Felder bei Debian-Paketen,
die eingebaute Update-Angabe bei AppImages. Deshalb funktioniert es auch bei Programmen, die
es noch nie gesehen hat. Findet sich nichts, trägt man die Projektseite **einmal** ein.

## Grundsätze

* **Prüfen automatisch, ändern nur auf Knopfdruck.** Ein Programm, das selbsttätig aus dem
  Internet lädt und mit Administratorrechten installiert, ist ein Generalschlüssel.
* **Vorschau in Klartext vor jedem Zugriff** — welche Datei, von wo, wohin.
* **Die alte Fassung wird nie gelöscht**, sondern nach `~/Dokumente` gelegt.
* **Nachmessen statt behaupten:** Nach jeder Änderung wird geprüft, was wirklich installiert ist.
* **Anschauen ohne Passwort.** Administratorrechte nur fürs Ersetzen selbst.

## Installieren

```
sudo apt install ./rikus-updateall_1.2_all.deb
```

Danach im Startmenü unter *System*.

## Anleitungen

[Ausführliche Anleitung (deutsch)](ANLEITUNG.md) · [Guide (English)](GUIDE.md)

## Läuft auf

Debian, Ubuntu, Linux Mint, MX Linux, antiX, Devuan — mit und ohne systemd.
Oberfläche deutsch oder englisch, je nach Systemeinstellung.

---

*Rikus Updateall — von Gilbert Rikus · GPL-3.0-or-later*
