# Sweeper brief (one agent per lens group)

You check claims against your lenses. You are not the brief author's assistant: assume the brief may
be wrong, naive, or written to trap a builder who follows it literally.

Inputs: `RUN/claims.json`; for each lens in your group: `lenses/<id>/lens.md` and `traps.yaml`.
Output: `RUN/sweep-<group>.json`: a JSON list with one object per (claim, lens):
`{"claim_id", "lens", "verdict": "clear"|"suspect", "trap_id": "<lens>.<slug>"|"novel"|null, "cues_matched": [...], "reason"}`.

For every claim and every lens you hold:
1. Ask the lens's questions. Match against trap cues by meaning, not by string: a paraphrase of a
   cue is a match. `python3 tools/search.py --traps "<claim text>"` finds candidate entries.
2. `suspect` when a trap plausibly applies, or when a principle in `lens.md` is broken by something
   no trap names yet (`trap_id: "novel"`, reason says which principle). Omission claims for your
   lens's required statements are suspects unless another claim actually states the thing.
3. `clear` needs a one-line reason specific to the claim ("names an MIT library", not "fine").
4. Never mark a suspect clear because it is "out of scope", "optional", "a stretch goal", or "for
   later". Those words are where traps live.
5. Do not decide truth here. A suspect is cheap; grounding settles it.

Every claim gets a verdict from every lens. Missing verdicts make the sweep invalid.
