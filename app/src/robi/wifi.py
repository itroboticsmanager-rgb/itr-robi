"""Read the active Windows Wi-Fi profile for the local sharing screen.

The browser cannot inspect the tablet's wireless connection.  This adapter
uses the Windows Native Wifi API directly, avoiding localized ``netsh`` output
and avoiding temporary files that would contain the network key.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from xml.etree import ElementTree


class WifiShareError(RuntimeError):
    """The current connection cannot safely be represented as a share QR."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class WifiAccess:
    ssid: str
    password: str
    authentication: str
    hidden: bool = False

    @property
    def qr_payload(self) -> str:
        return wifi_qr_payload(self)


def _escape_qr(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for character in (';', ',', ':', '"'):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


def wifi_qr_payload(access: WifiAccess) -> str:
    """Build the de-facto ZXing Wi-Fi QR payload used by phone cameras."""
    auth = access.authentication.upper()
    if auth in {"OPEN", "NONE"}:
        kind = "nopass"
    elif "WEP" in auth:
        kind = "WEP"
    elif any(name in auth for name in ("PSK", "SAE", "WPA")):
        kind = "WPA"
    else:
        raise WifiShareError("unsupported_security")
    fields = [f"T:{kind}", f"S:{_escape_qr(access.ssid)}"]
    if kind != "nopass":
        if not access.password:
            raise WifiShareError("password_unavailable")
        fields.append(f"P:{_escape_qr(access.password)}")
    if access.hidden:
        fields.append("H:true")
    return f"WIFI:{';'.join(fields)};;"


def _text(root: ElementTree.Element, path: str, *, strip: bool = True) -> str:
    node = root.find(path)
    value = node.text or "" if node is not None else ""
    return value.strip() if strip else value


def _profile_access(xml: str) -> WifiAccess:
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise WifiShareError("profile_invalid") from exc

    ssid = _text(root, ".//{*}SSIDConfig/{*}SSID/{*}name", strip=False)
    authentication = _text(root, ".//{*}authEncryption/{*}authentication")
    use_one_x = _text(root, ".//{*}authEncryption/{*}useOneX").lower() == "true"
    hidden = _text(root, ".//{*}SSIDConfig/{*}nonBroadcast").lower() == "true"
    password = _text(root, ".//{*}sharedKey/{*}keyMaterial", strip=False)
    protected = _text(root, ".//{*}sharedKey/{*}protected").lower() == "true"

    if not ssid:
        raise WifiShareError("profile_invalid")
    if use_one_x or ("WPA" in authentication.upper() and not any(
        name in authentication.upper() for name in ("PSK", "SAE")
    )):
        raise WifiShareError("unsupported_security")
    if authentication.upper() not in {"OPEN", "NONE"} and protected:
        # Windows returned an encrypted blob because this account lacks the
        # wlan_secure_get_plaintext_key permission. Never mistake it for the
        # actual password and put it into a QR code.
        raise WifiShareError("permission_denied")
    access = WifiAccess(ssid, password, authentication, hidden)
    wifi_qr_payload(access)  # Validate support before exposing any field.
    return access


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [
        ("InterfaceGuid", _GUID),
        ("strInterfaceDescription", wintypes.WCHAR * 256),
        ("isState", wintypes.DWORD),
    ]


class _WLAN_CONNECTION_PREFIX(ctypes.Structure):
    _fields_ = [
        ("isState", wintypes.DWORD),
        ("wlanConnectionMode", wintypes.DWORD),
        ("strProfileName", wintypes.WCHAR * 256),
    ]


class WindowsWifiProvider:
    """Return the profile used by the currently connected Wi-Fi interface."""

    WLAN_INTERFACE_STATE_CONNECTED = 1
    WLAN_INTF_OPCODE_CURRENT_CONNECTION = 7
    WLAN_PROFILE_GET_PLAINTEXT_KEY = 4

    def __init__(self, fallback: WifiAccess | None = None) -> None:
        self.fallback = fallback

    def current(self) -> WifiAccess:
        try:
            return self._current()
        except WifiShareError as exc:
            # The standard kiosk account can be denied plaintext-key or
            # current-connection access. A device-only guest profile is the
            # deliberate fallback for that one case.
            if exc.reason == "permission_denied" and self.fallback is not None:
                return self.fallback
            raise

    def _current(self) -> WifiAccess:
        if os.name != "nt":
            raise WifiShareError("unsupported_platform")

        wlan = ctypes.WinDLL("wlanapi")
        wlan.WlanOpenHandle.argtypes = [
            wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.HANDLE),
        ]
        wlan.WlanOpenHandle.restype = wintypes.DWORD
        wlan.WlanEnumInterfaces.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        wlan.WlanEnumInterfaces.restype = wintypes.DWORD
        wlan.WlanQueryInterface.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_GUID), wintypes.DWORD,
            ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p,
        ]
        wlan.WlanQueryInterface.restype = wintypes.DWORD
        wlan.WlanGetProfile.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_GUID), wintypes.LPCWSTR,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ]
        wlan.WlanGetProfile.restype = wintypes.DWORD
        wlan.WlanFreeMemory.argtypes = [ctypes.c_void_p]
        wlan.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        handle = wintypes.HANDLE()
        version = wintypes.DWORD()
        interfaces = ctypes.c_void_p()
        result = wlan.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle))
        if result:
            raise WifiShareError("service_unavailable")
        try:
            result = wlan.WlanEnumInterfaces(handle, None, ctypes.byref(interfaces))
            if result or not interfaces.value:
                raise WifiShareError("not_connected")
            try:
                count = ctypes.cast(interfaces, ctypes.POINTER(wintypes.DWORD)).contents.value
                start = interfaces.value + ctypes.sizeof(wintypes.DWORD) * 2
                for index in range(count):
                    info = _WLAN_INTERFACE_INFO.from_address(
                        start + index * ctypes.sizeof(_WLAN_INTERFACE_INFO)
                    )
                    if info.isState != self.WLAN_INTERFACE_STATE_CONNECTED:
                        continue
                    return self._from_interface(wlan, handle, info.InterfaceGuid)
            finally:
                wlan.WlanFreeMemory(interfaces)
        finally:
            wlan.WlanCloseHandle(handle, None)
        raise WifiShareError("not_connected")

    def _from_interface(self, wlan, handle, guid: _GUID) -> WifiAccess:
        size = wintypes.DWORD()
        connection = ctypes.c_void_p()
        result = wlan.WlanQueryInterface(
            handle,
            ctypes.byref(guid),
            self.WLAN_INTF_OPCODE_CURRENT_CONNECTION,
            None,
            ctypes.byref(size),
            ctypes.byref(connection),
            None,
        )
        if result or not connection.value:
            raise WifiShareError("permission_denied" if result == 5 else "not_connected")
        try:
            profile = _WLAN_CONNECTION_PREFIX.from_address(connection.value).strProfileName
        finally:
            wlan.WlanFreeMemory(connection)
        if not profile:
            raise WifiShareError("profile_invalid")

        flags = wintypes.DWORD(self.WLAN_PROFILE_GET_PLAINTEXT_KEY)
        access = wintypes.DWORD()
        profile_xml = ctypes.c_void_p()
        result = wlan.WlanGetProfile(
            handle,
            ctypes.byref(guid),
            profile,
            None,
            ctypes.byref(profile_xml),
            ctypes.byref(flags),
            ctypes.byref(access),
        )
        if result or not profile_xml.value:
            raise WifiShareError("permission_denied" if result == 5 else "profile_unavailable")
        try:
            xml = ctypes.wstring_at(profile_xml.value)
        finally:
            wlan.WlanFreeMemory(profile_xml)
        return _profile_access(xml)
