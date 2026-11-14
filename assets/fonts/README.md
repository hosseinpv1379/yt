# Caption fonts

The Docker image installs these fonts from Debian packages and copies the bold
faces into `/app/assets/fonts` for libass. The corresponding Debian copyright
files are copied alongside the font files in the image.

| Font family | Debian package | Upstream source | License |
| --- | --- | --- | --- |
| Vazirmatn | `fonts-vazirmatn` | [Google Fonts: Vazirmatn](https://github.com/google/fonts/tree/main/ofl/vazirmatn) | SIL Open Font License 1.1 |
| Montserrat | `fonts-montserrat` | [Google Fonts: Montserrat](https://github.com/google/fonts/tree/main/ofl/montserrat) | SIL Open Font License 1.1 |
| Noto Sans Arabic | `fonts-noto-core` | [Noto Fonts: Arabic](https://github.com/notofonts/arabic) | SIL Open Font License 1.1 |
| Noto Naskh Arabic | `fonts-noto-core` | [Noto Fonts: Arabic](https://github.com/notofonts/arabic) | SIL Open Font License 1.1 |
| Noto Sans | `fonts-noto-core` | [Noto Fonts: Latin, Greek, and Cyrillic](https://github.com/notofonts/latin-greek-cyrillic) | SIL Open Font License 1.1 |
| Noto Serif | `fonts-noto-core` | [Noto Fonts: Latin, Greek, and Cyrillic](https://github.com/notofonts/latin-greek-cyrillic) | SIL Open Font License 1.1 |

The Noto package copyright and license notices are preserved as
`Noto-FONTS-COPYRIGHT`; the existing Vazirmatn and Montserrat notices are
preserved as `Vazirmatn-COPYRIGHT` and `Montserrat-COPYRIGHT`.
