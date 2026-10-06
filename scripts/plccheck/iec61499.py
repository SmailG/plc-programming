"""IEC 61499-2 XML library elements (.fbt, .adp, .sub, …) as written by Eclipse 4diac."""

from __future__ import annotations

from .findings import Finding, error, warning, with_context
from .st import lint_st
from .xmlutil import Node

ROOTS = {"FBType", "AdapterType", "SubAppType", "ResourceType", "DeviceType", "System", "SegmentType"}


def _names(parent: Node | None, list_tag: str, item_tag: str) -> dict[str, Node]:
    lst = parent.find(list_tag) if parent is not None else None
    return {n.get("Name", ""): n for n in lst.findall(item_tag)} if lst is not None else {}


def check_iec61499(root: Node) -> list[Finding]:
    out: list[Finding] = []
    if root.tag not in ROOTS:
        return [error("FB001", f"root element <{root.tag}> is not an IEC 61499 library element", root.line)]
    if not root.get("Name"):
        out.append(error("FB002", f"<{root.tag}> has no Name", root.line))
    if root.tag not in ("FBType", "AdapterType"):
        return out  # SubAppType uses SubAppInterfaceList; systems/devices: name check only
    ctx = f"{root.tag} {root.get('Name')}"
    il = root.find("InterfaceList")
    if il is None:
        return out + [error("FB003", "missing <InterfaceList>", root.line, ctx)]

    ev_in = _names(il, "EventInputs", "Event")
    ev_out = _names(il, "EventOutputs", "Event")
    d_in = _names(il, "InputVars", "VarDeclaration")
    d_out = _names(il, "OutputVars", "VarDeclaration")
    adapters = {**_names(il, "Sockets", "AdapterDeclaration"), **_names(il, "Plugs", "AdapterDeclaration")}
    all_ports: dict[str, int] = {}
    for group in (ev_in, ev_out, d_in, d_out, adapters):
        for name, node in group.items():
            if name in all_ports:
                out.append(error("FB004", f"interface name '{name}' used twice (first at line {all_ports[name]})", node.line, ctx))
            all_ports[name] = node.line
    for events, data, direction in ((ev_in, d_in, "input"), (ev_out, d_out, "output")):
        for ev in events.values():
            for w in ev.findall("With"):
                if w.get("Var") not in data:
                    out.append(error("FB005", f"event '{ev.get('Name')}' WITH '{w.get('Var')}' is not a data {direction}", w.line, ctx))

    basic = root.find("BasicFB")
    if basic is not None:
        out.extend(_check_basic(basic, ev_in, ev_out, d_in, d_out, ctx))
    composite = root.find("FBNetwork")
    if composite is not None:
        out.extend(_check_network(composite, all_ports, set(adapters), ctx))
    return out


def _check_basic(basic: Node, ev_in, ev_out, d_in, d_out, ctx: str) -> list[Finding]:
    out: list[Finding] = []
    algorithms = {a.get("Name", ""): a for a in basic.findall("Algorithm")}
    ecc = basic.find("ECC")
    if ecc is None:
        return [error("FB010", "BasicFB has no <ECC>", basic.line, ctx)]
    states = {}
    for s in ecc.findall("ECState"):
        if s.get("Name") in states:
            out.append(error("FB011", f"EC state '{s.get('Name')}' defined twice", s.line, ctx))
        states[s.get("Name")] = s
        for act in s.findall("ECAction"):
            alg, ev = act.get("Algorithm"), act.get("Output")
            if alg and alg not in algorithms:
                out.append(error("FB012", f"state '{s.get('Name')}' runs unknown algorithm '{alg}'", act.line, ctx))
            if ev and ev not in ev_out:
                out.append(error("FB013", f"state '{s.get('Name')}' fires unknown output event '{ev}'", act.line, ctx))
    if not states:
        out.append(error("FB011", "ECC has no states (the first state is the initial state)", ecc.line, ctx))
    incoming = {name: 0 for name in states}
    for t in ecc.findall("ECTransition"):
        src, dst = t.get("Source"), t.get("Destination")
        for end, label in ((src, "Source"), (dst, "Destination")):
            if end not in states:
                out.append(error("FB014", f"ECTransition {label} '{end}' is not a state", t.line, ctx))
        if dst in incoming:
            incoming[dst] += 1
        cond = (t.get("Condition") or "").strip()
        head = cond.split("[")[0].strip()
        if head and head not in ("1", "TRUE") and head not in ev_in and "." not in head:
            out.append(warning("FB015", f"transition condition '{cond}' does not start with an input event", t.line, ctx))
    names = list(states)
    for name in names[1:]:
        if incoming.get(name) == 0:
            out.append(warning("FB016", f"EC state '{name}' is unreachable (no incoming transition)", states[name].line, ctx))
    for alg in algorithms.values():
        st = alg.find("ST")
        if st is None:
            continue
        # FBDK style: <ST Text="..."/>; 4diac 3.x style: <ST><![CDATA[...]]></ST>
        if st.get("Text") is not None:
            text, first = st.get("Text"), st.line
        else:
            text, first = st.text, st.text_line or st.line
        f, _ = lint_st(text, "body")
        out.extend(with_context(f, f"{ctx} algorithm {alg.get('Name')}", first - 1))
    return out


def _check_network(net: Node, ports: dict[str, int], adapters: set[str], ctx: str) -> list[Finding]:
    out: list[Finding] = []
    fbs = {fb.get("Name", "") for fb in net.findall("FB")} | {s.get("Name", "") for s in net.findall("SubApp")} | adapters
    for conns in net.children:
        if conns.tag not in ("EventConnections", "DataConnections", "AdapterConnections"):
            continue
        for c in conns.findall("Connection"):
            for end in ("Source", "Destination"):
                ref = c.get(end) or ""
                inst = ref.split(".", 1)[0] if "." in ref else None
                if inst is not None and inst not in fbs:
                    out.append(error("FB020", f"connection {end} '{ref}' names unknown instance '{inst}'", c.line, ctx))
                elif inst is None and ref not in ports:
                    out.append(error("FB020", f"connection {end} '{ref}' is not an interface port", c.line, ctx))
    return out
