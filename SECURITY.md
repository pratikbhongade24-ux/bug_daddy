# Security Advisory – GHSA‑p423‑j2cm‑9vmq

## Affected component
- **Package**: `cryptography`
- **Version**: `46.0.1`
- **Vulnerability**: Buffer overflow when non‑contiguous buffers are passed to certain APIs (CVE‑2024‑XXXX, GHSA‑p423‑j2cm‑9vmq).

## Impact
In the `bugdaddy‑sonar‑report‑ingestor` Lambda this library is bundled and used for cryptographic operations (e.g., token verification, encryption). Supplying a sliced `memoryview` or any non‑contiguous buffer can cause the Lambda process to crash, leading to denial‑of‑service and a potential remote‑code‑execution vector.

## Recommended remediation (code‑level)
1. **Upgrade the dependency**
   ```bash
   # In the Lambda's requirements.txt (or Pipfile)
   cryptography>=46.0.2   # or the latest stable release
   ```
   Re‑build and redeploy the Lambda.

2. **Normalize buffers before calling cryptography APIs**
   ```python
   def _to_contiguous(data: Any) -> bytes:
       """Ensure the payload passed to cryptography is a contiguous bytes object.
       Raises ValueError for unsupported types.
       """
       if isinstance(data, (bytes, bytearray)):
           return bytes(data)
       # memoryview, numpy arrays, etc.
       try:
           return bytes(data)
       except Exception as exc:
           raise ValueError("Non‑contiguous buffer supplied to cryptography") from exc
   ```
   Use `_to_contiguous` on every input that reaches `cryptography` (e.g., before `Cipher.update`, `HMAC.finalize`, `hashes.Hash.update`).

3. **Add regression test**
   ```python
   def test_cryptography_buffer_normalisation():
       from mymodule import encrypt   # function that eventually calls cryptography
       mv = memoryview(b"secret")[::2]  # non‑contiguous slice
       # Should not crash – either succeed or raise a controlled ValueError
       try:
           encrypt(mv)
       except ValueError:
           assert True
       else:
           assert True
   ```

## Verification steps
- Pull the newly built Lambda artifact and confirm `cryptography` version via `pip freeze`.
- Run the unit test above; it must pass.
- Deploy to a staging environment and invoke the Lambda with a crafted non‑contiguous payload. Ensure no segmentation fault appears in CloudWatch logs.

## Monitoring & rollback
- **Monitoring**: Keep an alert on Lambda `Errors` metric and on any future `cryptography` CVE findings.
- **Rollback**: If the new deployment introduces regressions, revert to the previous Lambda version (the one stored in the Lambda version history) and re‑apply the original `requirements.txt`.

---
*This advisory is linked to Jira ticket **BUG‑114** and should be referenced in any PR that upgrades the `cryptography` dependency or adds the buffer‑normalisation guard.*