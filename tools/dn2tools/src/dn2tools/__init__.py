"""On-device test harness for the Digitone II mod (docs/device-tests.md).

Drives the unit over USB MIDI (notes only), reads it back through the read-only telemetry frame
(SysEx 32 TLM, csrc/sampler/link.c) and asserts. Runs against a simulator (`--dry-run`) too.
"""
