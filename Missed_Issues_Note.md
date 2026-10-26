# Task 3 — Data Quality Checks: Missed-Issues Note

## Summary

The PulseIQ warehouse contains 14 recorded data-quality checks: 1 PASS, 11 FAIL, 1 BLOCKED, and 1 PARTIAL. The results indicate that data-quality exceptions remain and that two checks cannot yet provide complete validation.

## Issues requiring further validation

1. **Attrition-risk band consistency:** The score 0.127 appeared in both Low and Medium bands across 13 records in the earlier feed validation. Confirm the score-to-band thresholds and classification logic.
2. **Historical employee-key consistency:** Review employee references against the appropriate effective dates in the employee dimension, not just whether an employee identifier exists.
3. **Anomaly-feed reason codes:** A complete approved reason-code list was not available in the earlier review, so valid-looking but unsupported codes may not be detected.
4. **Timestamp semantics:** The anomaly feed contained timezone-naive `scored_at` values. Confirm the expected timezone and timestamp convention.
5. **Forecast department identifiers:** Company-wide forecast rows use department ID `ALL`. Confirm that downstream reports interpret these records correctly rather than treating `ALL` as an ordinary department.
6. **Check implementation gaps:** DQ-C13 (Pipeline freshness) is BLOCKED because no successful pipeline run is recorded. DQ-C14 (Minimum group size) is PARTIAL, so complete validation has not been demonstrated.

## Conclusion

Passing a data-quality check does not prove that every business rule is satisfied. Review the known exceptions, document unresolved assumptions, and complete the blocked or partial checks before treating the warehouse as fully validated.