# Our engines, one folder each

The fork's own synth engines live in `src/dnfw/engines/<engine>/`, one folder an engine; upstream's files stay
where upstream keeps them (`src/dnfw/mnm/`, `src/dnfw/md/`, ...), so every upstream release rebases cleanly.

| folder | what | modules |
|---|---|---|
| `engines/sophie/` | SOPHIE | `sophie.py` |
| `engines/plaits/` | PLAITS and its engines | `plaits.py`, `plaits_<name>.py` (one an engine), `plk.py` (their shared code), `tables.py` (its tables) |
| `engines/tb303/` | TB303 | `tb303.py`, `tb303_sched.py` (its scheduled sample) |
| `engines/drone/` | DRONE | `drone.py` |
| `engines/analog2/` | ANALOG 2 | `analog2.py`, `a2glide.py` (its legato glide) |
| `engines/analog2/filters/` | ANALOG 2's filters and the A2 filter machines (the pass after the voices) | `models.py`, `design.py`, `program.py`, `live.py`, `ref.py`, `pages.py`, `coldfire.py` |
| `engines/juno/` | JUNO | `juno.py`, `juno_data.py` (its data), `tables.py` (its tables, from that data) |
| `engines/drum/` | DRUM (docs/drum.md) | `drum.py` (the machine), `kick.py` (KICK), `dmath.py` (its arithmetic), `ref.py` (its reference) |
| `engines/` | our list, and what our engines' pages read | `machines.py` (our engines, their machine types and builder parts, in PERC's order), `units.py` (the value readouts), `stock_measured.json` (the stock machines' measured units) |

There is one machine framework, upstream's: PERC's voice (`dnfw.md.voice`), the DSL (`dnfw.perc.dsl`) and the
Monomachine-style adapter (`dnfw.mnm.machines`), which turns an engine written as `pitch` / `init` / `trig` / `half`
into the voice's steps. Our engines are modules of that shape; `dnfw.engines.machines` lists them (ahead of and
behind the Monomachine's own five, which `dnfw.mnm.machines` names), and `dnfw.mnm.tables` lays out the
Monomachine OS's tables, then ours from each engine's `tables.py`. Shared tooling of ours that is not an engine stays
beside the framework: the schedulers (`dnfw.mnm.sched`, `dnfw.mnm.vsched`).

To add an engine: a folder here, its module of that shape, an entry in `dnfw.engines.machines` (its tables, if any,
in `dnfw.mnm.tables`' run).

(2026-11-13: moved here from `src/dnfw/mnm/` and `src/dnfw/a2f/`, then our list and tables out of upstream's
`dnfw.mnm.machines` and our `dnfw.mnm.tables`; the generated DSP and ColdFire code byte for byte the same.)
