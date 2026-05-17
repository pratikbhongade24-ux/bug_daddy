# AXIS Bank Refund API — Integration Documentation

**Version:** 1.2.0
**Last Updated:** 2026-05-17
**Owner:** Payments Platform Team
**Service:** PaymentService → AXIS Bank Gateway

---

## ⚠️ Critical Limitation

> **AXIS Bank Refund API does NOT support partial refunds.**
>
> If `refundType: "PARTIAL"` is sent with a `refundAmount` less than the original transaction amount, the AXIS gateway **ignores the requested amount** and processes a **full refund** equal to the original payment amount.
>
> **No error is returned.** The response status will be `REFUND_INITIATED` with HTTP 200, making this silent data corruption that is only detectable via reconciliation.
>
> **Use `refundType: "FULL"` only when routing refunds through AXIS.**
> For partial refunds, route through HDFC or ICICI.

---

## Endpoint

```
POST /payments
requestId: processRefund
```

This is a Lambda-style invocation. The `requestId` field in the request body acts as the operation router.

---

## Request Payload

| Field | Type | Required | Description |
|---|---|---|---|
| `requestId` | string | ✅ | Must be `"processRefund"` |
| `originalPaymentId` | string | ✅ | ID of the original payment being refunded |
| `bankCode` | string | ✅ | Bank to process the refund through. One of: `HDFC`, `ICICI`, `AXIS` |
| `refundType` | string | ✅ | `"FULL"` or `"PARTIAL"`. **AXIS only supports `"FULL"`** |
| `reason` | string | ✅ | Free-text reason for the refund (stored in `ms_refunds.reason`) |
| `customerId` | string | ✅ | Customer initiating the refund |
| `refundAmount` | number | ⚠️ Conditional | Required when `refundType = "PARTIAL"`. Ignored by AXIS — see warning above |
| `originalAmount` | number | Optional | Original payment amount. Used by AXIS to determine the full refund value |
| `remarks` | string | Optional | Internal ops notes (stored in `ms_refunds.remarks`) |
| `notifyCustomer` | boolean | Optional | Whether to send refund notification to the customer. Default: `true` |

---

## Sample Requests

### Full Refund via AXIS (Supported ✅)

```json
{
  "requestId": "processRefund",
  "originalPaymentId": "PAY-SEED-0007",
  "bankCode": "AXIS",
  "refundType": "FULL",
  "originalAmount": 120000,
  "reason": "Order cancelled by customer",
  "customerId": "CUST-0007",
  "remarks": "Cancellation ref #ORD-8821",
  "notifyCustomer": true
}
```

### Partial Refund via AXIS (NOT Supported ⛔)

```json
{
  "requestId": "processRefund",
  "originalPaymentId": "PAY-SEED-0007",
  "bankCode": "AXIS",
  "refundType": "PARTIAL",
  "refundAmount": 35000,
  "originalAmount": 120000,
  "reason": "Partial cancellation — 1 of 3 items returned",
  "customerId": "CUST-0007",
  "notifyCustomer": true
}
```

> ⛔ **What actually happens:** AXIS ignores `refundAmount: 35000` and credits `120000` (the full original amount) to the customer. Our `ms_refunds` table records `35000` as requested. The discrepancy surfaces only in `ms_reconciliation_items` with `match_status = AMOUNT_MISMATCH`.

### Partial Refund via HDFC (Supported ✅)

```json
{
  "requestId": "processRefund",
  "originalPaymentId": "PAY-SEED-0001",
  "bankCode": "HDFC",
  "refundType": "PARTIAL",
  "refundAmount": 40000,
  "originalAmount": 150000,
  "reason": "Partial cancellation — processing fee retained",
  "customerId": "CUST-0001",
  "remarks": "Approved by ops team",
  "notifyCustomer": true
}
```

---

## Success Response

```json
{
  "service": "PaymentService",
  "requestId": "processRefund",
  "operation": "processRefund",
  "traceId": "3f9a1c22-84b1-4de1-a091-fc2d88e1c4a0",
  "timestamp": "2026-05-17T07:30:00.000000+00:00",
  "refund": {
    "refundId": "REF-CF24290628CC1A",
    "originalPaymentId": "PAY-SEED-0007",
    "refundType": "FULL",
    "refundAmount": 120000.0,
    "status": "INITIATED",
    "bankCode": "AXIS",
    "reason": "Order cancelled by customer",
    "remarks": "Cancellation ref #ORD-8821",
    "notifyCustomer": true
  },
  "bankResponse": {
    "bankCode": "AXIS",
    "bankRefId": "AXISREF3F9A1C22",
    "refundId": "REF-CF24290628CC1A",
    "originalPaymentId": "PAY-SEED-0007",
    "refundAmount": 120000.0,
    "requestedRefundAmount": 120000.0,
    "status": "REFUND_INITIATED",
    "tat": "2-3 business days"
  },
  "message": "FULL refund initiated successfully"
}
```

### AXIS Partial Refund Bug — What the Response Looks Like

When `refundType: "PARTIAL"` with `refundAmount: 35000` is sent to AXIS, the response comes back as HTTP **200 with no error**:

```json
{
  "refund": {
    "refundId": "REF-CE0C1A990B07",
    "originalPaymentId": "PAY-SEED-0007",
    "refundType": "PARTIAL",
    "refundAmount": 35000.0,
    "status": "INITIATED",
    "bankCode": "AXIS"
  },
  "bankResponse": {
    "bankCode": "AXIS",
    "bankRefId": "AXISREF8B3C21FA",
    "refundAmount": 120000.0,
    "requestedRefundAmount": 35000.0,
    "status": "REFUND_INITIATED",
    "tat": "2-3 business days"
  }
}
```

Note `bankResponse.refundAmount: 120000.0` vs `bankResponse.requestedRefundAmount: 35000.0`. The delta `85000.0` is the overpayment. This is the only in-response signal of the bug — but it is not surfaced as an error.

---

## Error Responses

### 400 — Missing Required Fields

```json
{
  "error": "Missing required fields: ['originalPaymentId', 'reason']",
  "operation": "processRefund",
  "service": "PaymentService"
}
```

### 400 — Unsupported Bank

```json
{
  "error": "Unsupported bankCode 'SBI'. Supported: ['AXIS', 'HDFC', 'ICICI']",
  "operation": "processRefund",
  "service": "PaymentService"
}
```

### 400 — Invalid refundType

```json
{
  "error": "refundType must be 'FULL' or 'PARTIAL'",
  "operation": "processRefund",
  "service": "PaymentService"
}
```

### 400 — Missing refundAmount for PARTIAL

```json
{
  "error": "refundAmount is required when refundType is 'PARTIAL'",
  "operation": "processRefund",
  "service": "PaymentService"
}
```

### 400 — Invalid refundAmount

```json
{
  "error": "refundAmount must be a positive number",
  "operation": "processRefund",
  "service": "PaymentService"
}
```

---

## Bank Capability Matrix

| Bank | Full Refund | Partial Refund | TAT | Settlement |
|---|---|---|---|---|
| HDFC | ✅ Supported | ✅ Supported | 3–5 business days | T+0 |
| ICICI | ✅ Supported | ✅ Supported | 5–7 business days | T+1 |
| AXIS | ✅ Supported | ⛔ **Not supported** — silently processes FULL | 2–3 business days | T+0 |

---

## Database Impact

Every `processRefund` call writes to:

| Table | What is stored |
|---|---|
| `ms_refunds` | Our system's record — always stores the **requested** `refundAmount` and `refundType` accurately |
| `ms_reconciliation_items` | The **bank's actual processed amount** — for AXIS PARTIAL refunds this will be the full original amount, creating an `AMOUNT_MISMATCH` row |
| `ms_service_events` | Full audit trail of the request and response |

The `ms_system_monitors` table contains a CRITICAL severity check (`id=1`, service=`RefundService`) that queries `ms_refunds JOIN ms_reconciliation_items` to surface these mismatches daily.

---

## Known Issue Reference

| Field | Value |
|---|---|
| **Bug ID** | `AXIS-PARTIAL-REFUND-001` |
| **Severity** | CRITICAL |
| **Affected bank** | AXIS only |
| **Detection** | `ms_system_monitors` T-1 Refund vs Recon Discrepancy Check |
| **Workaround** | Do not send `refundType: "PARTIAL"` to AXIS. Route all partial refunds via HDFC or ICICI |
| **Status** | Open — awaiting AXIS bank API fix |
