"""Build identity of a `.project`: the CodeId / DataId per device application, and the save stamp.

Observed layout (reverse-engineered; two XML entries of the project zip, both plain text):

* `devicesmetainformation.auxiliary` is `<Devices>` holding one `<Device>` per controller. A
  device has `<Data Key=... Type=...>` children (Name, DeviceType, DeviceId, DeviceVersion,
  DeviceName) and one `<Application>` per application, itself holding Name, CodeId and DataId
  as `System.Guid` data. The IDE compares CodeId and DataId with the controller to tell whether
  the project matches what is downloaded (**not verified here**: the vendor does not document it).
* `engineeringtoolsversions.auxiliary` is `<Configuration>` with a `<History>` of `<HistoryEntry>`
  elements: CoreVersion, OpenCounter, SaveCounter, FirstTimeSaved, LastTimeSaved. The newest
  LastTimeSaved is the project's last SAVE, not a compile time.

There is no compile time in the project. The IDE writes it to the `.compileinfo` / `.bootinfo`
files next to the project, which are not part of the zip.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import xml.parsers.expat
from dataclasses import dataclass, field
from typing import List, Optional

from .binary import FormatError
from .zipread import entry_name, open_archive, read_entry

DEVICES_ENTRY = "devicesmetainformation.auxiliary"
HISTORY_ENTRY = "engineeringtoolsversions.auxiliary"
_STAMP_RE = re.compile(r"^(\d{4})-(\d\d)-(\d\d)-(\d\d)-(\d\d)-(\d\d)$")
_GUID_HEAD_RE = re.compile(r"^([0-9a-fA-F]{8})-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


@dataclass
class ApplicationInfo:
    name: Optional[str]
    code_id: Optional[str]
    data_id: Optional[str]


@dataclass
class DeviceInfo:
    name: Optional[str]
    device_type: Optional[str]
    device_id: Optional[str]
    device_version: Optional[str]
    device_name: Optional[str]
    applications: List[ApplicationInfo] = field(default_factory=list)


@dataclass
class ProjectInfo:
    devices: List[DeviceInfo] = field(default_factory=list)
    product: Optional[str] = None
    project_version: Optional[str] = None
    last_saved: Optional[str] = None  # "YYYY-MM-DD HH:MM:SS", the saving machine's clock
    save_counter: Optional[int] = None
    core_version: Optional[str] = None
    notes: List[str] = field(default_factory=list)


def short_id(guid: Optional[str]) -> Optional[str]:
    """The first eight hex digits of a guid, which is what the rest of the guid (zeros) leaves."""
    match = _GUID_HEAD_RE.match(guid or "")
    return match.group(1).lower() if match else None


def swapped_id(guid: Optional[str]) -> Optional[str]:
    """The first four bytes reversed. A boot image stores the id this way; which order the IDE
    shows is not verified, so both are printed."""
    head = short_id(guid)
    return "".join(reversed([head[i:i + 2] for i in range(0, 8, 2)])) if head else None


def _parse_xml(data: bytes, entry: str, notes: List[str]) -> Optional[ET.Element]:
    """The XML root, or None with a note. DOCTYPE and ENTITY declarations are refused, not expanded,
    whatever the document's encoding: expat reports them before ElementTree sees any entity."""
    if _has_doctype(data):
        notes.append("%s: has a DOCTYPE or ENTITY declaration; not parsed" % entry)
        return None
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        notes.append("%s: not well-formed XML (%s)" % (entry, exc))
        return None


class _Doctype(Exception):
    pass


def _has_doctype(data: bytes) -> bool:
    def refuse(*_args) -> None:
        raise _Doctype()
    parser = xml.parsers.expat.ParserCreate()
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    try:
        parser.Parse(data, True)
    except _Doctype:
        return True
    except xml.parsers.expat.ExpatError:
        return False  # not well-formed: ElementTree reports it
    return False


def _data_values(node: ET.Element) -> dict:
    return {d.get("Key"): (d.text or "").strip() for d in node.findall("Data")}


def _devices(root: ET.Element) -> List[DeviceInfo]:
    devices: List[DeviceInfo] = []
    for node in root.findall("Device"):
        v = _data_values(node)
        device = DeviceInfo(v.get("Name"), v.get("DeviceType"), v.get("DeviceId"), v.get("DeviceVersion"),
                            v.get("DeviceName"))
        for app in node.findall("Application"):
            a = _data_values(app)
            device.applications.append(ApplicationInfo(a.get("Name"), a.get("CodeId"), a.get("DataId")))
        devices.append(device)
    return devices


def _newest_save(root: ET.Element, info: ProjectInfo) -> None:
    best = None
    for entry in root.iter("HistoryEntry"):
        match = _STAMP_RE.match(entry.get("LastTimeSaved", ""))
        if match and (best is None or match.groups() > best[0]):
            best = (match.groups(), entry)
    info.product = root.get("InformationalProductName")
    info.project_version = root.get("EngineeringProjectVersion")
    if best is not None:
        g, entry = best
        info.last_saved = "%s-%s-%s %s:%s:%s" % g
        info.core_version = entry.get("CoreVersion")
        counter = entry.get("SaveCounter", "")
        info.save_counter = int(counter) if counter.isascii() and counter.isdigit() else None


def _read_xml(archive, zinfo, entry: str, notes: List[str]) -> Optional[ET.Element]:
    try:
        data = read_entry(archive, zinfo)
    except FormatError as exc:
        notes.append("%s: %s" % (entry, exc))
        return None
    return _parse_xml(data, entry, notes)


def read_info(path: str) -> ProjectInfo:
    """Read the build identity. A missing or unreadable entry is a note; a non-zip raises FormatError."""
    archive = open_archive(path)
    info = ProjectInfo()
    with archive:
        entries = {entry_name(i): i for i in archive.infolist()}
        if DEVICES_ENTRY not in entries:
            info.notes.append("no %s entry: no build identity in this project" % DEVICES_ENTRY)
        else:
            root = _read_xml(archive, entries[DEVICES_ENTRY], DEVICES_ENTRY, info.notes)
            if root is not None:
                info.devices = _devices(root)
                if not info.devices:
                    info.notes.append("%s: no <Device> element under <%s>" % (DEVICES_ENTRY, root.tag))
        if HISTORY_ENTRY in entries:
            root = _read_xml(archive, entries[HISTORY_ENTRY], HISTORY_ENTRY, info.notes)
            if root is not None:
                _newest_save(root, info)
    return info


def info_to_dict(info: ProjectInfo) -> dict:
    return {
        "devices": [
            {"name": d.name, "device_type": d.device_type, "device_id": d.device_id,
             "device_version": d.device_version, "device_name": d.device_name,
             "applications": [
                 {"name": a.name, "code_id": a.code_id, "code_id_short": short_id(a.code_id),
                  "code_id_byte_swapped": swapped_id(a.code_id), "data_id": a.data_id,
                  "data_id_short": short_id(a.data_id), "data_id_byte_swapped": swapped_id(a.data_id)}
                 for a in d.applications]}
            for d in info.devices],
        "product": info.product, "project_version": info.project_version, "last_saved": info.last_saved,
        "save_counter": info.save_counter, "core_version": info.core_version, "notes": info.notes,
    }


def _id_text(label: str, guid: Optional[str]) -> str:
    if not guid:
        return "%s -" % label
    swapped = swapped_id(guid)
    return "%s %s" % (label, guid) + (" (byte-swapped %s)" % swapped if swapped else "")


def render_info_text(info: ProjectInfo) -> str:
    lines = [
        "# build identity, decoded from devicesmetainformation.auxiliary. The IDE compares CodeId and DataId",
        "# with the controller (not verified here); which byte order it shows is not verified either, so both",
        "# are printed. The project holds no compile time: that is in the .compileinfo beside the project file.",
    ]
    for device in info.devices:
        lines.append("device %s  type=%s id=%s version=%s name=%s" % (
            device.name, device.device_type, device.device_id, device.device_version, device.device_name))
        if not device.applications:
            lines.append("  (no application)")
        for app in device.applications:
            lines.append("  application %s  %s  %s" % (app.name, _id_text("CodeId", app.code_id),
                                                       _id_text("DataId", app.data_id)))
    if info.last_saved:
        lines.append("last saved: %s (the save, not a compile; the saving machine's clock)  save counter %s  core %s  %s %s"
                     % (info.last_saved, info.save_counter, info.core_version, info.product or "", info.project_version or ""))
    else:
        lines.append("last saved: not available")
    return "\n".join(lines)
