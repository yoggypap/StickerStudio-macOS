# Third-party notices

Sticker Studio for macOS includes or is built with third-party open-source software.

This file is provided for attribution and license notice purposes. Where a component's license requires preservation of copyright/license notices or source availability, redistributors should retain the corresponding notices and comply with the upstream license terms.

## FFmpeg

The standalone macOS application bundles:

- **FFmpeg 8.1.2**
- **Target:** macOS arm64
- **Bundled encoder:** libvpx / VP9
- **libvpx version:** 1.16.0
- **Bundled FFmpeg SHA-256:**

```text
eaf91238e104dd0e262bc6510e25061855cc99a6955a721b0ac99660d58c473d
```

Build provider:

https://ffmpeg.martin-riedl.de/

The bundled FFmpeg binary was built with `--enable-gpl`. Under FFmpeg's licensing rules, enabling GPL components makes that FFmpeg build subject to the **GNU General Public License, version 2 or later (GPL-2.0-or-later)**.

FFmpeg license information:

https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md

FFmpeg source:

https://ffmpeg.org/download.html

FFmpeg 8.1.2 release source:

https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz

Martin Riedl FFmpeg build scripts/source information:

https://ffmpeg.martin-riedl.de/

The FFmpeg build may contain additional third-party libraries enabled by the build provider. See the provider's build configuration and source/build scripts for the complete dependency set and corresponding license obligations.

### libvpx

FFmpeg uses **libvpx 1.16.0** for VP8/VP9 encoding/decoding.

Project:

https://github.com/webmproject/libvpx

libvpx is distributed under a BSD-style license, with an additional patent grant in the upstream `PATENTS` file.

License:

https://github.com/webmproject/libvpx/blob/main/LICENSE

Patent grant:

https://github.com/webmproject/libvpx/blob/main/PATENTS

## Qt for Python / PySide6

Sticker Studio's GUI is built with **Qt for Python / PySide6**.

Project:

https://doc.qt.io/qtforpython-6/

Qt for Python is offered under the **LGPLv3 / GPLv3** and Qt commercial licensing options. This project uses the open-source distribution.

License information:

https://doc.qt.io/qtforpython-6/

When redistributing the bundled application, the applicable Qt/PySide license terms must be preserved.

## Python

The standalone build includes the Python runtime.

Python is distributed under the **Python Software Foundation License Version 2** and additional historical licenses applicable to portions of CPython.

License:

https://github.com/python/cpython/blob/main/LICENSE

Python Software Foundation:

https://www.python.org/psf/

## NumPy

Sticker Studio bundles **NumPy**.

Project:

https://numpy.org/

NumPy is primarily distributed under the **BSD 3-Clause License**. Binary wheels can contain additional vendored components under their own compatible licenses.

License information:

https://numpy.org/doc/stable/license

Source:

https://github.com/numpy/numpy

## SciPy

Sticker Studio bundles **SciPy**.

Project:

https://scipy.org/

SciPy is distributed under the **BSD 3-Clause License**. Binary distributions may include additional third-party components whose license notices are included by the SciPy distribution.

Source:

https://github.com/scipy/scipy

## Pillow

Sticker Studio bundles **Pillow** for image processing.

Project:

https://python-pillow.org/

Source:

https://github.com/python-pillow/Pillow

Pillow is distributed under the PIL/Pillow **MIT-CMU-style license**.

License:

https://github.com/python-pillow/Pillow/blob/main/LICENSE

## Phosphor Icons

Sticker Studio embeds **Phosphor Icons Regular and Fill** from the official Phosphor Icons project.

Project:

https://phosphoricons.com/

Source:

https://github.com/phosphor-icons/web

Phosphor Icons is licensed under the **MIT License**.

License:

https://github.com/phosphor-icons/web/blob/master/LICENSE

Copyright © Phosphor Icons contributors.

## PyInstaller

The standalone `.app` is produced with **PyInstaller**.

PyInstaller is build tooling and is licensed primarily under **GPL-2.0-or-later with the PyInstaller Bootloader Exception**. The exception permits applications produced with the PyInstaller bootloader to be distributed under licenses determined by the application author, subject to the licenses of the application's dependencies.

Project:

https://pyinstaller.org/

License:

https://pyinstaller.org/en/stable/license.html

Source:

https://github.com/pyinstaller/pyinstaller

## OBS Studio chroma-key reference

Sticker Studio's chroma-key implementation is original project code informed by the publicly documented behavior of the OBS Studio chroma-key filter.

No OBS source files, binaries, shaders, or other OBS assets are embedded in Sticker Studio.

OBS Studio:

https://github.com/obsproject/obs-studio

OBS Studio is licensed under GPL-2.0.

## Original Sticker Studio

This macOS project is a port of:

**uxlive Sticker Studio**

https://github.com/grozovsky/StickerStudio

Original project / concept: **grozovsky / UX Live**.

macOS port: **@yoggypub**.

The macOS port is published with permission from the original project's author.

---

## Redistribution note

The application bundle includes third-party binary components. If you redistribute a modified build, you are responsible for preserving the notices and satisfying the licenses of the exact third-party binaries you ship.

In particular, because the bundled FFmpeg build is GPL-enabled, redistribution of that binary must satisfy the applicable GPL source-availability requirements. Do not remove upstream copyright or license notices from bundled components.
