# Z3 Audit Report — Real Results on Actual Translations

**Generated:** 2026-04-10T22:14:33Z
**SAS file:** `C:\Users\labou\Desktop\Stage\backend\tests\fixtures\torture_test.sas`
**Translations:** `C:\Users\labou\Desktop\Stage\backend\output\translate_test`
**Blocks audited:** 10

---

## What this shows

Each block below was already translated and **marked SUCCESS** by the
syntax + exec validation. Z3 then inspects the Python semantics against
the original SAS — this is the layer that catches bugs validation misses.

| Symbol | Meaning |
|--------|---------|
| `[PROVED]` | Z3 formally proved the translation is semantically equivalent |
| `[COUNTEREXAMPLE]` | Z3 found a concrete input where SAS and Python differ |
| `[UNKNOWN]` | Pattern outside Z3 scope (RETAIN, hash, macros) |

---

## Aggregate

| Metric | Value |
|--------|-------|
| Blocks audited | 10 |
| Formally proved | **3** (30%) |
| Counterexamples found | **0** (0%) |
| Outside Z3 scope | 7 (70%) |
| Mean Z3 latency | 4.6 ms |
| Pipeline overhead | negligible (vs >5000ms LLM latency) |

---

## Block-by-Block Results

### Block 1: 1. RETAIN + BY-group FIRST./LAST.

- **Translation file:** `torture_test_block01_1_RETAIN_BY_group_FIRST_LAST.py`
- **SAS lines:** 12  |  **Python lines:** 24
- **Z3 latency:** 16.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[UNKNOWN]** |
| Z3 pattern matched | `conditional_assignment` |

> Pattern `1. RETAIN + BY-group FIRST./LAST.` uses SAS idioms (RETAIN, hash objects,
> macros) that are outside Z3's decidable fragment — result is UNKNOWN.
> This is expected; Z3 only covers patterns it can encode symbolically.

### Block 2: 2. Missing value logic (SAS . < any number)

- **Translation file:** `torture_test_block02_2_Missing_value_logic_SAS_any_number.py`
- **SAS lines:** 7  |  **Python lines:** 13
- **Z3 latency:** 0.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[UNKNOWN]** |
| Z3 pattern matched | `boolean_filter` |

> Pattern `2. Missing value logic (SAS . < any number)` uses SAS idioms (RETAIN, hash objects,
> macros) that are outside Z3's decidable fragment — result is UNKNOWN.
> This is expected; Z3 only covers patterns it can encode symbolically.

### Block 3: 3. PROC SQL with correlated subquery

- **Translation file:** `torture_test_block03_3_PROC_SQL_with_correlated_subquery.py`
- **SAS lines:** 14  |  **Python lines:** 28
- **Z3 latency:** 0.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[UNKNOWN]** |
| Z3 pattern matched | `boolean_filter` |

> Pattern `3. PROC SQL with correlated subquery` uses SAS idioms (RETAIN, hash objects,
> macros) that are outside Z3's decidable fragment — result is UNKNOWN.
> This is expected; Z3 only covers patterns it can encode symbolically.

### Block 4: 4. Macro with parameters + %DO loop

- **Translation file:** `torture_test_block04_4_Macro_with_parameters_DO_loop.py`
- **SAS lines:** 14  |  **Python lines:** 58
- **Z3 latency:** 0.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[UNKNOWN]** |
| Z3 pattern matched | `conditional_assignment` |

> Pattern `4. Macro with parameters + %DO loop` uses SAS idioms (RETAIN, hash objects,
> macros) that are outside Z3's decidable fragment — result is UNKNOWN.
> This is expected; Z3 only covers patterns it can encode symbolically.

### Block 5: 5. PROC MEANS with CLASS and OUTPUT

- **Translation file:** `torture_test_block05_5_PROC_MEANS_with_CLASS_and_OUTPUT.py`
- **SAS lines:** 8  |  **Python lines:** 22
- **Z3 latency:** 15.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[PROVED]** |
| Z3 pattern matched | `proc_means_groupby` |

> Z3 formally proved this translation preserves the semantics
> of the `proc_means_groupby` pattern.

### Block 6: 6. PROC SORT NODUPKEY

- **Translation file:** `torture_test_block06_6_PROC_SORT_NODUPKEY.py`
- **SAS lines:** 3  |  **Python lines:** 9
- **Z3 latency:** 0.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[PROVED]** |
| Z3 pattern matched | `sort_nodupkey` |

> Z3 formally proved this translation preserves the semantics
> of the `sort_nodupkey` pattern.

### Block 7: 7. Hash object for lookup

- **Translation file:** `torture_test_block07_7_Hash_object_for_lookup.py`
- **SAS lines:** 11  |  **Python lines:** 76
- **Z3 latency:** 0.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[UNKNOWN]** |
| Z3 pattern matched | `conditional_assignment` |

> Pattern `7. Hash object for lookup` uses SAS idioms (RETAIN, hash objects,
> macros) that are outside Z3's decidable fragment — result is UNKNOWN.
> This is expected; Z3 only covers patterns it can encode symbolically.

### Block 8: 8. Multi-level nested macro

- **Translation file:** `torture_test_block08_8_Multi_level_nested_macro.py`
- **SAS lines:** 11  |  **Python lines:** 89
- **Z3 latency:** 0.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[UNKNOWN]** |
| Z3 pattern matched | `proc_means_groupby` |

> Pattern `8. Multi-level nested macro` uses SAS idioms (RETAIN, hash objects,
> macros) that are outside Z3's decidable fragment — result is UNKNOWN.
> This is expected; Z3 only covers patterns it can encode symbolically.

### Block 9: 9. PROC TRANSPOSE

- **Translation file:** `torture_test_block09_9_PROC_TRANSPOSE.py`
- **SAS lines:** 5  |  **Python lines:** 20
- **Z3 latency:** 0.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[UNKNOWN]** |

> Pattern `9. PROC TRANSPOSE` uses SAS idioms (RETAIN, hash objects,
> macros) that are outside Z3's decidable fragment — result is UNKNOWN.
> This is expected; Z3 only covers patterns it can encode symbolically.

### Block 10: 10. Complex WHERE + FORMAT + LABEL

- **Translation file:** `torture_test_block10_10_Complex_WHERE_FORMAT_LABEL.py`
- **SAS lines:** 11  |  **Python lines:** 27
- **Z3 latency:** 15.0 ms

| Stage | Result |
|-------|--------|
| Syntax check | PASS |
| Exec validation | PASS (no exception) |
| **Z3 formal check** | **[PROVED]** |
| Z3 pattern matched | `boolean_filter` |

> Z3 formally proved this translation preserves the semantics
> of the `boolean_filter` pattern.

---

## Conclusion

Z3 formally proved **3/10** translations correct and detected
**0** semantic bug(s) that syntax + exec validation did not catch.
The remaining 7 blocks use patterns outside Z3's scope (RETAIN,
hash objects, macro expansion) — these fall back to human review.

**Z3 overhead:** 4.6 ms mean per block — negligible against LLM latency.