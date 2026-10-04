# Reference sounds

`target/legacy-target.wav` and `out_of_range/legacy-out-of-range.wav` are copies
of the classic project's recordings. They make the new detector runnable, but
are not verified retail recordings. The originals remain in `classic/`.

Replace these copies with clean retail references following
[`../required-sounds.md`](../required-sounds.md). Every WAV matched by an enabled
event's glob in `settings.yaml` is loaded; move obsolete references out of these
folders to stop using them. Mixing in a bad reference can cause false matches.

Independent recordings for evaluation belong in `recordings/`, not here.
