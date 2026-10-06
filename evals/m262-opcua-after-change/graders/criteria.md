---
type: llm
---

PASS if the answer explains (1) that the M262 OPC UA server restarts on every download, online change and reset, so the client loses its session/subscriptions and must reconnect (recommending robust reconnect/resubscribe on the SCADA side), and (2) that Symbol Configuration changes are only transferred to the controller with a (full) download, so an online change does not publish the new symbol; it may also mention that a GVL variable must be used in code or linked (linkalways) to appear.
FAIL if it blames the network/firewall for (1) without mentioning the server restart, or claims the online change should already have published the new symbol.
