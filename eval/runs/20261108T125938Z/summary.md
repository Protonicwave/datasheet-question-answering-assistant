# Evaluation summary

eval/development.jsonl: 100 questions (80 answerable), 3 runs, model claude-sonnet-5-5, up to 2 revisions per rejected answer.

| Arm | correct | wrong | correct refusal | false refusal | unplaced | error |
| --- | --- | --- | --- | --- | --- | --- |
| A: model alone | 59.7 (58 to 62) | 11.0 (9 to 13) | 14.3 (13 to 15) | 15.0 (12 to 17) | 0 | 0 |
| B: model with search | 77 | 0 | 20 | 3 | 0 | 0 |
| C: search with check | 52.7 (52 to 54) | 0 | 20 | 27.3 (26 to 28) | 0 | 0 |
| D: search, check and retry | 76.7 (76 to 77) | 0 | 20 | 3 | 0.3 (0 to 1) | 0 |
