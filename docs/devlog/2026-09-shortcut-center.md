# Shortcut Center: turning two shortcut dialogs into one product surface

The Windows smoke test was not a Pack loading failure. The prior Library could
load VS Code data, but treated Catalog identities as its application universe
and sampled foreground context only at construction. That made unsupported
applications disappear and made Center-like navigation feel static.

The existing USER Shortcut Manager already contained the hard parts: recorder
integration, single-step validation, profile transactions, conflict checks,
editing, deletion and built-in hide/restore. Reimplementing it in Library would
have created a second persistence path. The correction instead keeps its draft
and editor as reusable internal components, while Shortcut Center supplies the
one top-level browsing and management view.

Application discovery now remains attached to the existing foreground chain.
The candidate tracker records descriptors for valid external applications even
when Catalog has no Pack; Windows version metadata is opportunistic and has a
safe executable-name fallback. Catalog support is applied later as an optional
annotation. This avoids both a second foreground monitor and an installed-app
scanner.

Follow Current App is deliberately event-driven. The tracker signal updates an
open Center, and window activation rereads the last external candidate. Manual
selection pauses follow for only the open dialog, so comparison is possible
without accidentally creating a persistent lock state.

The Pack schema now accepts localized category definitions. VS Code categories
became stable keys, with English and Chinese display labels. Recommendation also
became a separate status cell instead of contaminating translated descriptions.

The pack remains a 41-entry pilot. No Pack expansion, Full Guide, downloader,
or global-registry editor was introduced. Automated coverage includes descriptor
fallback, recent deduplication, support separation, follow/manual behavior,
unsupported USER editing, localized categories, and independent recommendation
metadata; the complete suite remains the final regression gate.
