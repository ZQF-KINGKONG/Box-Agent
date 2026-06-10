# Root Cause Tracing

For multi-component issues, inspect each boundary:

- user action or input
- frontend state and request payload
- IPC/API boundary
- backend/service handler
- runtime/tool invocation
- persisted state or filesystem
- final output/rendering

At each boundary, ask:

- What entered?
- What exited?
- What transformed it?
- What invariant should hold?
- Where does actual behavior first diverge from expected behavior?

