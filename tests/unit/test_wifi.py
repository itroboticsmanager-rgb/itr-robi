"""Wi-Fi sharing stays local and rejects profiles phones cannot join by QR."""

from __future__ import annotations

import pytest

from robi.wifi import (
    WifiAccess,
    WifiShareError,
    WindowsWifiProvider,
    _profile_access,
    wifi_qr_payload,
)


def profile(*, authentication="WPA2PSK", key="secret", protected="false", one_x="false"):
    shared = "" if authentication == "open" else f"""
      <sharedKey><keyType>passPhrase</keyType><protected>{protected}</protected><keyMaterial>{key}</keyMaterial></sharedKey>
    """
    return f"""<?xml version="1.0"?>
    <WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
      <SSIDConfig><SSID><name>ITRobotics Guest</name></SSID><nonBroadcast>false</nonBroadcast></SSIDConfig>
      <MSM><security><authEncryption><authentication>{authentication}</authentication><encryption>AES</encryption><useOneX>{one_x}</useOneX></authEncryption>{shared}</security></MSM>
    </WLANProfile>"""


def test_personal_profile_becomes_a_camera_wifi_payload():
    access = _profile_access(profile(key="robot;pass\\word"))
    assert access.ssid == "ITRobotics Guest"
    assert access.password == "robot;pass\\word"
    assert access.qr_payload == r"WIFI:T:WPA;S:ITRobotics Guest;P:robot\;pass\\word;;"


def test_open_profile_has_no_password_field():
    access = _profile_access(profile(authentication="open"))
    assert wifi_qr_payload(access) == "WIFI:T:nopass;S:ITRobotics Guest;;"


def test_spaces_at_the_edges_of_ssid_and_password_are_not_lost():
    xml = profile(key=" pass word ").replace(
        "ITRobotics Guest", " Guest network "
    )
    access = _profile_access(xml)
    assert access.ssid == " Guest network "
    assert access.password == " pass word "


def test_hidden_network_is_marked_in_the_payload():
    payload = wifi_qr_payload(WifiAccess("Guest", "pass", "WPA3SAE", hidden=True))
    assert payload == "WIFI:T:WPA;S:Guest;P:pass;H:true;;"


@pytest.mark.parametrize(
    ("xml", "reason"),
    [
        (profile(authentication="WPA2", one_x="true", key=""), "unsupported_security"),
        (profile(protected="true", key="encrypted-blob"), "permission_denied"),
        (profile(key=""), "password_unavailable"),
    ],
)
def test_unshareable_profiles_are_rejected(xml, reason):
    with pytest.raises(WifiShareError) as error:
        _profile_access(xml)
    assert error.value.reason == reason


def test_configured_guest_profile_is_used_only_for_a_windows_permission_error(monkeypatch):
    fallback = WifiAccess("Guest", "secret", "WPA2PSK")
    provider = WindowsWifiProvider(fallback)
    monkeypatch.setattr(provider, "_current", lambda: (_ for _ in ()).throw(
        WifiShareError("permission_denied")
    ))
    assert provider.current() == fallback

    monkeypatch.setattr(provider, "_current", lambda: (_ for _ in ()).throw(
        WifiShareError("not_connected")
    ))
    with pytest.raises(WifiShareError, match="not_connected"):
        provider.current()
