# Bundled backend source snapshot

Upstream: https://github.com/Hommy-master/capcut-mate

This is the local modified source used to build the bundled desktop backend, preserved on 2026-11-25. It is not represented as an unmodified upstream commit. The upstream Apache-2.0 LICENSE and NOTICE are retained.

Only source, templates and public resource catalogs are included. User drafts, downloaded media, database, logs, virtual environments and credentials are excluded. `config/sticker.json.gz` is a lossless compressed copy of the original large resource catalog; the build script restores it before packaging.
