# Scott Voice runtime resources

`runtime/` contains the production worker, continuous DSP, SDK pins and helpers
used by Scott Voice. Files were moved byte for byte from the old research directory.
Retired research benches are archived in the ignored local report
`reports/release-cleanup-2026-10-23/public-before.zip` and do not ship.

The installer preserves existing asset IDs and installed SDK/model paths.
Moving repository sources does not move weights, rebuild the working SDK,
change the accepted reference or require another model download.
