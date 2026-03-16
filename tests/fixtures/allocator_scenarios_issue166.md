# Issue #166 allocator scenarios

Deterministic allocator scenarios covered here:

- weakest held below floor -> SGOV
- weakest held below floor -> GLTR
- precious to SGOV
- SGOV to metal
- second precious holding blocked
- candidate fails delta

Each scenario fixture defines:
- positions
- compact score rows (`pts` plus metadata)
- constraints
- expected recommendation output
- optional expected rejection reasons by symbol
