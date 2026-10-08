# Crewloom brand assets

The loom mark represents separate threads meeting in a checked workflow. Mint horizontal threads alternate over blue vertical threads. The assets use the existing Crewloom palette and carry accessible SVG titles and descriptions.

| Asset | Use | Canvas |
| --- | --- | --- |
| [Logo](../assets/crewloom-logo.svg) | Square avatar, icon or project identity | 256 × 256 |
| [Banner](../assets/crewloom-banner.svg) | Wide README or documentation header | 1280 × 320 |
| [Mobile banner](../assets/crewloom-banner-mobile.svg) | Narrow README header | 640 × 360 |
| [Landscape logo animation](../assets/crewloom-logo-animation-landscape.mp4) | Website, presentation or video introduction | 1920 × 1080 |
| [Portrait logo animation](../assets/crewloom-logo-animation-vertical.mp4) | Vertical video introduction | 1080 × 1920 |
| [Silent animation preview](../assets/crewloom-logo-animation.gif) | Lightweight motion preview | 800 × 450 |

Use the square logo at 24 px or larger. Preserve the aspect ratio and its internal padding; do not crop the threads. Keep the ink background so both thread colors retain their contrast on light and dark surrounding surfaces. The README uses a `picture` source at a 600 px viewport breakpoint for the mobile banner; Markdown viewers without `picture` support fall back to the wide banner.

| Color | Value | Purpose |
| --- | --- | --- |
| Ink | `#101827` | Asset background |
| Mint | `#40ddbc` | Horizontal threads and accent |
| Blue | `#8ca9ff` | Vertical threads |
| White | `#f7f9fc` | Wordmark |
| Muted | `#b8c5d8` | Tagline |

Keep changing inventory counts in README text rather than embedding them in artwork. Use the English wordmark in both language versions; provide Arabic alternative text when embedding it in Arabic documents. The SVGs contain no scripts, external image references, filters or embedded fonts. Packaging rules include them with the other `assets/*.svg` resources.

## Motion identity

Both MP4s run for eight seconds at 60 fps. Blue vertical threads draw first, mint horizontal threads follow, and alternate mint bridges resolve the weave. The mark then settles into its wordmark and tagline. The exports use H.264 High Profile, Rec.709, `yuv420p`, AAC stereo and a fast-start container. Their quiet sound is original synthesis; no third-party music is included. The GIF is silent and loops for preview.

The portrait composition keeps the primary logo and text within x=60–960 and y=220–1540. All 480 encoded frames passed a half-resolution bright-pixel boundary check; the metadata checker alone does not establish visual safe zones. Platform overlays can change, so review the target channel before publishing. These are local deliverables, not evidence of a remote release.

Use the static SVG when reduced motion is requested. Keep website sound opt-in, and provide playback controls or a static poster instead of making the animated intro mandatory.
