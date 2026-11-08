# Evaluation summary

eval/held_out.jsonl: 50 questions (40 answerable), 3 runs, model claude-sonnet-5-5, revisions per rejected answer: at most 1.

| Arm | correct | wrong | correct refusal | false refusal | unplaced | error |
| --- | --- | --- | --- | --- | --- | --- |
| A: model alone | 26 | 4.3 (3 to 7) | 9.7 (9 to 10) | 9.7 (8 to 11) | 0.3 (0 to 1) | 0 |
| B: model with search | 33.3 (33 to 34) | 0.3 (0 to 1) | 10 | 3.3 (3 to 4) | 3 | 0 |
| C: search with check | 26.0 (25 to 27) | 0.3 (0 to 1) | 10 | 10.7 (9 to 12) | 3 | 0 |
| D: search, check and retry | 32.7 (32 to 34) | 0.3 (0 to 1) | 10 | 4.0 (3 to 5) | 3 | 0 |
