# bug_daddy

## Simulated Bug Mechanism

Several services in **bug_daddy** include a `simulateBug` flag in the request payload to deliberately trigger error scenarios for testing and resilience verification.

Supported `simulateBug` values for **BankStatementService**:
- `negative_pages` – attempts to access an out‑of‑range page index, causing an `IndexError`.
- `amount_cast` – forces an invalid integer conversion, now caught and returned as a controlled error response (HTTP 400) with a descriptive message.
- `missing_bucket` – accesses a missing dictionary key, resulting in a `KeyError` which is also now handled gracefully.

### Error Handling
When a simulated bug is triggered, the service will no longer raise an uncaught exception. Instead, the Lambda handler catches the exception and returns a JSON payload with:
```json
{
  "service": "BankStatementService",
  "requestId": "<operation>",
  "operation": "<operation>",
  "error": "<error description>"
}
```
with an HTTP status code of **400**.

### Input Validation
- `pages` is now parsed using a safe conversion helper; non‑numeric values default to `3` and emit a warning.
- The `simulateBug` flag is validated against the allowed set; unsupported values raise a `ValueError`.

These changes improve observability, prevent Lambda crashes, and provide clear feedback to callers during testing.
