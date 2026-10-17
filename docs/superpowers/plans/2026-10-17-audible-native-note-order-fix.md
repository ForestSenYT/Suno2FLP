# Audible native note scheduling fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the real-song candidate's missing/inaudible pitched content without changing any source occurrence, note field or time.

**Architecture:** Keep the source-order `AudioPreviewPlan.notes` audit; serialize complete FLP note records by `(start_tick, channel, source_part, source_occurrence)`. The independent verifier enforces that physical sequence. A v2 candidate profile explicitly declares the policy and separately measured gain raw5000; previous candidates stay immutable/unqualified.

**Tech Stack:** Existing Python/Pydantic, original tiny fixtures, fixed bounded FL26 background experiments; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-16-deliverable-audio-to-flp-design.zh-CN.md`.

## Global constraints

No keyboard/mouse/clicks; new private outputs only; protect original assets, baselines and all previous experiments. Do not upload real files or backend/model state. Existing MIDI fidelity and AudioClip/crop/tempo/controller blockers remain unchanged. Music quality, reference stems and final GUI are separate incomplete requirements.

## Review focus

- Arbitrary/decreasing source order preserves every duplicate occurrence and its original audit position.
- Equal ticks/channel use explicit source selectors for deterministic ties.
- Reordered, missing or altered physical notes must fail independently of their multiset/count.
- Positive peak and repeatability alone cannot qualify a render; isolate each required voice and record active signal/level/clipping.
- Raw5000 is an observed preview policy, not a linear gain or a guarantee against clipping in every future song.

## Tasks

- [x] Reproduce: old WAV is mostly silent/quiet; source FLP has 2237 backwards-time adjacent records. Only sorting full records at unchanged gain restores broad signal. Preserve failed experiment and diagnostics.
- [x] Finish isolated vocals/bass/other and gain5000 native controls, require real nonzero content and no clipping; preserve every note/tick and all nonbudgeted bytes.
- [x] Run new original tests RED; change `core/audio_flp.py` profile/policy/gain, `flp_builder/audio_preview.py` physical sorting and `validator/audio_flp.py` independent order checks. Update existing source-order expectations and docs.
- [ ] Run focused tests, locked sync, full offline regression, Ruff/format, mypy, build and installed CLI smoke. Generate a new current-source real-song candidate and repeat/native relink reopens, including isolated voice signal checks.
- [ ] Fresh-context independent review of exact head; expected public files, all current CI, current main and matched-head squash merge; verify unchanged old inputs and outputs. User listening feedback remains separate and never inferred from timeouts.
