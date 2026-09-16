# Credits

## Sticker Studio

Этот репозиторий содержит macOS-порт **uxlive Sticker Studio**.

### Original project

Оригинальный Sticker Studio для Windows, его концепция, основной UX и исходная реализация:

- **Author / Project:** grozovsky / UX Live
- **Repository:** https://github.com/grozovsky/StickerStudio
- **UX Live:** https://t.me/uxlive

macOS-порт опубликован с разрешения автора оригинального проекта.

### macOS port

- **Port:** @yoggypub
- **Platform:** macOS / Apple Silicon
- **Implementation:** Python / PySide6
- **Packaging:** standalone `.app`

Цель порта — сохранить поведение и основные возможности оригинального Sticker Studio в самостоятельном приложении для macOS.

## Third-party projects

Sticker Studio также использует сторонние open-source компоненты, включая:

- FFmpeg
- libvpx
- Qt for Python / PySide6
- Python
- NumPy
- SciPy
- Pillow
- Phosphor Icons
- PyInstaller (build tooling)

Chroma-key реализация проекта также была разработана с учётом публично документированного поведения chroma-key фильтра OBS Studio; исходный код OBS, шейдеры и бинарные компоненты OBS в приложение не включены.

Полный список уведомлений и лицензий: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
