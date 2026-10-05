# P4.3.4 Automated Pre-QA Gate (Part 2)

- Gate A (image structural): frozen `ImageValidator`
- Gate B (annotation): P4.2.2 `validate_annotations`
- All Gate A passed: **True**
- All Gate B passed: **True**

| Class | Gate A | Gate B | image issues | annotation issues | dup hashes |
| --- | --- | --- | --- | --- | --- |
| smartphone | True | True | 0 | 0 | 0 |
| tablet | True | True | 0 | 0 | 0 |
| monitor | True | True | 0 | 0 | 0 |
| printer | True | True | 0 | 0 | 0 |

A gate PASS is structural only and is **not** a human QA sign-off.
