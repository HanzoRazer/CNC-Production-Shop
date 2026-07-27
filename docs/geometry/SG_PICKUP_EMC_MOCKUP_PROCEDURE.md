# Pickup EMC mock-up — measurement procedure

**Status:** procedure only. No measurement has been taken.
**Answers:** `CONF-SINGLE-PICKUP-EMC` — whether a single coil is viable 71.6 mm
from a Raspberry Pi 5.
**Applies to:** `PRODUCT-KHAYA-SOLIDBODY-V1` (the harder case) and, by
inference, `PRODUCT-SMART-GUITAR-V1`.

## Why this is not a desk exercise

The layout has already been moved once on account of this question. As first
solved, the Khaya put the Pi 11.6 mm from the pickup and 10.75 mm from the
analog front-end board — the packing search that produced it asked only whether
the set fit, never how much room was left. Re-solving for clearance
(`CONF-POD-EMC-CLEARANCE`) reached:

```text
                              was      now
POD_PI to pickup route      11.6 mm   71.6 mm
POD_PI to POD_HAT           10.8 mm   35.8 mm
```

**That is close to the ceiling this outline allows.** POD_PI is now bound by
the upper bass-side ergonomic void and by the GPIO ribbon's reach, not by the
pickup — pushing it further means a longer ribbon or a different body, not a
different layout. The cheap geometric mitigation has been spent, so if the
measurement goes badly the next moves are cavity shielding, then a
hum-cancelling pickup.

One thing the relocation does not fix: the Pi's radio and switching supplies
are still inside the same cavity set as a pickup with no common-mode rejection.
Distance helps. It does not establish a pass.

## The comparison that matters

**Not against silence — against a conventional single-coil guitar.**

A single coil in an ordinary instrument already picks up mains hum, dimmers,
transformers and monitors. If the Pi adds less than that ambient floor, this is
a non-issue regardless of how close it sits. If it adds materially more, it is
a product problem no board can fix.

That framing decides the pass criterion, and it makes configuration A0 below as
important as the loaded ones.

## Equipment

- Mock-up cavity in representative timber, pockets at the governed positions.
  A routed offcut is sufficient; it does not need to be a finished body.
- The pickup actually under consideration, wired as it would be.
- Raspberry Pi 5 with the intended image, JACK and Guitarix installed.
- Audio interface with a **1 MΩ instrument input**, 24-bit / 48 kHz.
- Copper foil or shielding paint, and a ground connection for it.
- FFT analysis to 20 kHz with A-weighting.

**On using the tap_tone_pi rig:** its ADC, calibration loop and documented
noise-floor verification are directly reusable, but its OPA1612 front end is a
**balanced low-impedance mic preamp**. Feeding a guitar pickup into it loads
the coil and changes what you are measuring. Insert a Hi-Z DI ahead of it, or
use a separate instrument-input interface.

## Configurations

Record each identically. Strings damped throughout — you are measuring the
noise floor, not the instrument.

| # | Configuration |
|---|---|
| **A0** | Pi absent or unpowered. Mains ambient only. **The baseline.** |
| **A1** | As A0, instrument rotated 90°. Single coils null to mains hum in one orientation; this brackets the ambient range. |
| **B** | Pi powered, idle, WiFi and Bluetooth **off**. |
| **C** | Pi powered, idle, WiFi **on**. |
| **D** | Pi under DSP load — JACK and Guitarix running. WiFi on. **Worst realistic.** |
| **E** | As D, with the cavity shielded and the shield grounded. |
| **F** | As E, with the pickup temporarily at the pre-relocation distance (11.6 mm). |

Configuration F is deliberately backwards. The layout has already been moved
to its geometric limit, so there is no further-away case left to test — but a
close case still tells you how much the 60 mm bought. If F and E measure the
same, distance was never the mechanism and shielding is the whole answer.

Run A0 and D at minimum. B and C separate the radio from the switching
supplies, which decides which mitigation is worth paying for.

## Method

1. Set interface gain so a hard strum peaks at −6 dBFS. **Do not change it
   again** — every configuration must share one reference.
2. Damp the strings. Record 30 s per configuration.
3. Report A-weighted noise floor in dBFS, and an FFT to 20 kHz.
4. Record in playing position as well as on the bench for A0 and D. A body and
   hands change the coupling, sometimes substantially.

## Pass criteria

**Broadband**, measured as Δ from A0:

| Δ A-weighted | Verdict |
|---|---|
| ≤ 3 dB | Pass — below the pickup's own ambient variation |
| 3–6 dB | Marginal — mitigation required, retest at E |
| > 6 dB | Fail as configured |

**Discrete tones** — this criterion matters more than the broadband one:

> No discrete tone more than **10 dB above the local noise floor** anywhere
> from 20 Hz to 20 kHz.

Broadband hiss is forgivable and mostly inaudible under playing. Switching
harmonics and CPU-load artifacts are tonal, they track what the processor is
doing, and players find them intolerable at levels far below where hiss would
register. A configuration can pass the broadband test and still be unshippable.

## Recording the result

The outcome resolves `CONF-SINGLE-PICKUP-EMC` and should be captured as a
governed record — configuration, measured deltas, tone list, and the verdict —
with `source: measured_trial`. It is the first `measured_trial` in this program;
everything else so far is `engineering_estimate`.

If the answer forces a hum-cancelling pickup — a stacked noiseless single coil
or a splittable humbucker — the pickup route dimensions change, and the packing
that made the Khaya layout possible must be re-tested. Re-run
`scripts/solve_khaya_pocket_layout.py` with the new route; that re-test is
cheap, and discovering it after a body is cut is not.

## What this procedure does not cover

- Formal FCC / CE emissions testing. That is compliance of the finished
  assembly and belongs with an accredited lab.
- Conducted noise on the audio output. Separate test, separate method.
- Thermal behaviour of the sealed cavity.
