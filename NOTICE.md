# Notices

## What this repository holds, and under which license

Everything in this repository is the work of José M. Requena Plens. The artwork (the SVG sources and the motifs, the exported images and their previews) and the pack's data are licensed under the GNU General Public License, version 3 or any later version (GPL-3.0-or-later), the firmware's license. The tooling, which is more useful to everyone under a permissive license, is under the MIT License, as brand's is: the code under `tools/`, the tests, the CI, the pins and the configuration files, and the commit-message gate copied from the `agents` repository (below). `REUSE.toml` states it file by file and `LICENSES/` holds both texts. Both licenses are approved by the Open Source Initiative; nothing in this repository is under any other.

## What comes from brand

The `brand/` folder is the brand repository as a git submodule: a separate project with its own licenses and notices (`brand/NOTICE.md`), not part of this one's tree. This repository reads from it and copies one file:

- The mark and the lockup in every image are brand's (`brand/logo/src/mark.svg` and the logo files drawn from it), the work of the same author, under the same license.
- The colors are brand's tokens (`brand/tokens/tokens.json`).
- `TRADEMARKS.md` is a byte copy of `brand/TRADEMARKS.md`, so the terms it states travel with these files. The additional permission it gives (the press permission) names folders of the brand repository; it does not reach the images here, which are under the GPL with its two additional terms and no added permission. The images made to be republished are brand's press kit.
- The code under `tools/` imports brand's builders (`brand/tools/kleidos_brand/`, MIT there) and runs with the stack brand pins.
- The nine boards on the YouTube banner and in the boards card's motif are brand's copies of the `boards` repository's front drawings (`brand/boards/`, MIT, the work of the same author), drawn at one scale, and each board's panel shows its own unlock screen, a real capture from `brand/press-kit/screens/`. The boards are M5Stack's and LILYGO's products; the legends printed on them, the makers' marks included, are drawn as the products show them so that each one can be recognised, and remain their owners'.

## Fonts

No font file is in this repository. Every word in an image here is glyph outlines or rasterized text of Mona Sans and Mona Sans Mono 2.0.27, read at export time from the brand submodule, where the upstream files are kept unmodified beside their license: "Copyright 2022 The Mona Sans Project Authors (https://github.com/github/mona-sans), with Reserved Font Name "Mona"", SIL Open Font License 1.1, which the Open Source Initiative also approves. The OFL leaves such documents outside itself ("The requirement for fonts to remain under this license does not apply to any document created using the fonts or their derivatives"), so the images are the project's own work, under GPL-3.0-or-later. The credit is kept as a courtesy.

## The name and the mark

Kleidos is not a registered trademark. Under section 7(e) of the GNU GPL version 3, the license of this repository grants no rights under trademark law in the name "Kleidos" or in the Kleidos mark. Under section 7(c), a modified version of a file under the GPL here must be marked in reasonable ways as different from the original, and must not misrepresent the origin of the material; a file passed on unchanged needs no mark. [`TRADEMARKS.md`](TRADEMARKS.md) holds both terms and what the project asks of those who use its name. Each PNG file carries the same facts in its own metadata (its creator, its copyright line, GPL-3.0-or-later with the license's address, the credits, the trademark notes and the address of `TRADEMARKS.md`), so they travel with the file; this notice and `TRADEMARKS.md` remain the full statement.

## The commit-message gate

`.github/commit-check/` and the two `commit-check` workflows are this repository's copy of the gate kept in the project's `agents` repository, the work of the same author, under that repository's license, the MIT License (`LICENSES/MIT.txt`).

## What is not here

- No drawing, front, icon or model of a board in this tree: the fronts the images show are read from the brand submodule when they are drawn.
- No photograph or render of a device, and no capture of a screen in this tree: the captures on the boards' panels are read from the brand submodule too.
- No vendor file of any kind.

## Other people's trademarks

YouTube, MakerTube, PeerTube and GitHub are named here to say where each image goes; M5Stack, LILYGO and Espressif to say which boards the firmware runs on. They are trademarks of their respective owners. Kleidos is an independent project, not affiliated with, sponsored or endorsed by any of them, and the license of this repository grants no right to use any of those marks.
