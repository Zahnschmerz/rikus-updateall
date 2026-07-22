# Rikus Updateall — Guide

**Check and update the programs that do not come from apt.**

---

## 1. What is this about?

Your machine has an update manager: `apt`. Think of it as a family doctor — it looks after every
program in its own files, and it does that well.

But: **anything you obtained elsewhere is not in those files.**

* a `.deb` downloaded from a website
* an AppImage sitting in your Downloads folder
* a program an installer script dropped into `/usr/local/bin`
* a package installed with `npm`

Those programs age **silently**. Nothing ever tells you. They can be months out of date without
anyone noticing — including every security hole found in the meantime.

**Rikus Updateall lists exactly those programs — and brings them up to date on request.**

---

## 2. Requirements

Any Debian-based Linux: Debian, Ubuntu, Linux Mint, MX Linux, antiX, Devuan and relatives.
The window needs GTK 3, which those systems have anyway.

It works **with and without systemd**, so also on MX Linux and antiX.

---

## 3. Installing

```
sudo apt install ./rikus-updateall_1.0_all.deb
```

Afterwards **Rikus Updateall** appears in the start menu under *System*.

To remove it again:

```
sudo apt remove rikus-updateall
```

---

## 4. What you see

At the top a **traffic light** with one plain sentence: how many programs outside apt were found
and how many of them are out of date.

Below that a list. Every row has a coloured dot:

| Dot | Meaning |
|---|---|
| 🟢 green | up to date — the vendor was asked, there is nothing newer |
| 🔴 red | out of date — the available version is shown next to it |
| ⚫ grey | the origin is unknown, therefore **unchecked** |
| 🟡 yellow | the vendor is not answering right now |

**Important:** grey does *not* mean "fine". It means "I could not check this". That is why the
traffic light stays yellow even when everything checked is current — as long as something
remains unchecked.

Under each name you see **which kind it is and where the file lives**. That matters, because the
same program can exist several times on one machine.

---

## 5. Updating a program

Click **Update** in the row.

A window always appears **first**, in plain language: which file will be fetched, from which
address, where it will go, and where your current version will be kept. Nothing happens until
you confirm.

### What happens then

1. The new file is fetched — only downloaded, nothing replaced yet.
2. It is **verified**: does the size match what the vendor states? Is it actually a program,
   respectively a Debian package?
3. Only then is anything replaced.
4. **Your previous version is not deleted** but moved to `~/Documents`.
5. Afterwards the program **measures** which version is really installed now — and tells you.
   It does not simply claim success.

If anything fails along the way, the previous state is restored.

### Do I need my password?

Only when the file lives in a system folder:

| Kind | Password needed? |
|---|---|
| AppImage | no |
| Flatpak | no |
| npm package | no |
| Programs with their own updater | no |
| Program file in `/usr/local/bin` | **yes** |
| `.deb` package | **yes** |

Even then only the replacement itself runs with administrator rights. Downloading and unpacking
happen in your own folder beforehand.

> ⚠️ **Exception for `.deb` packages:** a Debian package replaces the old version; no backup file
> can be kept beside it. The way back would be fetching the older package from the vendor again.
> The preview window says so explicitly.

---

## 6. "Source unknown" — what now?

Some rows say *source unknown* and offer a button **Add source**.

That means the program could not work out where the newest version lives. Many packages carry
that information; some do not.

**Solution:** click *Add source*, open the project page in your browser, copy the address from
the address bar and paste it into the field.

All of these are understood:

```
https://github.com/owner/project
github.com/owner/project
https://github.com/owner/project/releases/latest
owner/project
https://www.npmjs.com/package/packagename
https://flathub.org/apps/program.id
```

From then on that program is checked automatically.

---

## 7. Frequently asked questions

**Why is the traffic light yellow although everything is green?**
Because something is still unchecked. A light showing green while something was never checked
would be dangerous: whoever reads green stops looking.

**Why does my program appear twice?**
Because it exists twice on the machine — usually once system-wide and once in your user folder.
That is not a display glitch, it is a finding. Often one of the two is ancient and nobody noticed.

**Why is my own script not listed?**
On purpose. The program only touches real program files, never hand-written scripts. It should
neither check nor accidentally run your own tools.

**It says "GitHub not answering" — is something broken?**
No. Without an account GitHub allows 60 requests per hour. When that is reached, the message
says from when it will work again. Results are remembered for six hours so this stays rare.

**Does the program change anything on its own?**
No. It reads, compares and waits. Only what you click and confirm in the preview is ever changed.

**Can I switch off the notice about new versions of this program itself?**
Yes:
```
touch ~/.config/rikus-updateall/kein-update-hinweis
```

**Where are my settings kept?**
In `~/.config/rikus-updateall/` — entered sources in `quellen.json`, remembered lookups in
`zwischenspeicher.json`. Both are plain text files.

---

## 8. If something goes wrong

The program aborts **before** touching anything and tells you so in a window. Your files stay
exactly as they were.

Your previous versions are in `~/Documents` under their original names — the version number is
usually part of the name. To go back, move the file to its old place.

---

*Rikus Updateall — by Gilbert Rikus*
