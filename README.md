# Rikus Updateall

**Finds the programs that do not come from apt — and keeps them current.**

`apt` only knows packages from configured sources. Everything installed by hand ages silently:
a `.deb` from a website, an AppImage in your Downloads folder, a program in `/usr/local/bin`,
an npm package. Nothing ever tells you.

Rikus Updateall lists exactly those programs, asks the vendor for the latest version, and
updates them at the press of a button.

## What it handles

| Kind | Update | Password |
|---|---|---|
| manually installed `.deb` | ✅ | yes |
| AppImage | ✅ | no |
| Flatpak | ✅ | no |
| program file in `/usr/local/bin` | ✅ | yes |
| npm package | ✅ | no |
| programs with their own updater | ✅ | no |

## How it knows where a program comes from

From the program itself wherever possible — `Homepage` and `Vcs` fields of Debian packages, the
built-in update information of AppImages. That is why it also works for programs it has never
seen. If nothing is found, you enter the project page **once**.

## Principles

* **Check automatically, change only on request.** A program that fetches from the internet and
  installs with administrator rights on its own is a master key.
* **Plain-language preview before every action** — which file, from where, to where.
* **The previous version is never deleted**, it is moved to `~/Documents`.
* **Measure, do not claim:** after every change the installed version is verified.
* **Looking needs no password.** Administrator rights only for the replacement itself.

## Install

```
sudo apt install ./rikus-updateall_1.1_all.deb
```

Then find it in the start menu under *System*.

## Documentation

[Guide (English)](GUIDE.md) · [Anleitung (deutsch)](ANLEITUNG.md)

## Runs on

Debian, Ubuntu, Linux Mint, MX Linux, antiX, Devuan — with and without systemd.
Interface in German or English, chosen automatically.

---

*Rikus Updateall — by Gilbert Rikus · GPL-3.0-or-later*
