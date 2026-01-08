
"""
/*
 * This file is part of the pypicokey distribution (https://github.com/polhenarejos/pypicokey).
 * Copyright (c) 2025 Pol Henarejos.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, version 3.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */
"""

from .core import NamedIntEnum
from typing import Optional, Tuple


# Predefined VID/PID for known vendors
class KnownVendor:
    """Predefined VID:PID combinations for known vendors."""
    NITROKEY_HSM = (0x20a0, 0x4230)
    NITROKEY_FIDO2 = (0x20a0, 0x42b1)
    NITROKEY_PRO = (0x20a0, 0x4108)
    NITROKEY_3 = (0x20a0, 0x42b2)
    NITROKEY_START = (0x20a0, 0x4211)
    YUBIKEY_4_5 = (0x1050, 0x0407)
    YUBIKEY_NEO = (0x1050, 0x0116)
    YUBICO_YUBIHSM = (0x1050, 0x0030)
    FSIJ_GNUK = (0x234b, 0x0000)
    GNUPG_EV = (0x1209, 0x2440)
    PICO_DEFAULT = (0xFEFF, 0xFCFD)

    @classmethod
    def get_all(cls) -> dict:
        """Return all predefined vendors as a dict."""
        return {
            "Nitrokey HSM": cls.NITROKEY_HSM,
            "Nitrokey FIDO2": cls.NITROKEY_FIDO2,
            "Nitrokey Pro": cls.NITROKEY_PRO,
            "Nitrokey 3": cls.NITROKEY_3,
            "Nitrokey Start": cls.NITROKEY_START,
            "Yubikey 4/5": cls.YUBIKEY_4_5,
            "Yubikey NEO": cls.YUBIKEY_NEO,
            "Yubico YubiHSM": cls.YUBICO_YUBIHSM,
            "FSIJ Gnuk": cls.FSIJ_GNUK,
            "GnuPG e.V.": cls.GNUPG_EV,
            "Pico Default": cls.PICO_DEFAULT,
        }


class PhyTag(NamedIntEnum):
    VIDPID = 0x0
    LED_GPIO = 0x4
    LED_BTNESS = 0x5
    OPTS = 0x6
    UP_BTN = 0x8
    USB_PRODUCT = 0x9
    ENABLED_CURVES = 0xA
    ENABLED_USB_ITF = 0xB
    LED_DRIVER = 0xC

class PhyOpt(NamedIntEnum):
    WCID = 0x1
    DIMM = 0x2
    DISABLE_POWER_RESET = 0x4
    LED_STEADY = 0x8

class PhyCurve(NamedIntEnum):
    SECP256R1 = 0x1
    SECP384R1 = 0x2
    SECP521R1 = 0x4
    SECP256K1 = 0x8
    BP256R1 = 0x10
    BP384R1 = 0x20
    BP512R1 = 0x40
    ED25519 = 0x80
    ED448 = 0x100
    CURVE25519 = 0x200
    CURVE448 = 0x400

class PhyUsbItf(NamedIntEnum):
    CCID = 0x1
    WCID = 0x2
    HID = 0x4
    KB = 0x8

class PhyLedDriver(NamedIntEnum):
    PICO = 0x1
    PIMORONI = 0x2
    WS2812 = 0x3
    CYW43 = 0x4
    NEOPIXEL = 0x5
    NONE = 0xFF

class PhyData:
    def __init__(self, **kwargs):
        self.vidpid = kwargs.get("vidpid")
        self.led_gpio = kwargs.get("led_gpio")
        self.led_brightness = kwargs.get("led_brightness")
        self.opts = kwargs.get("opts", 0)
        self.up_btn = kwargs.get("up_btn")
        self.usb_product = kwargs.get("usb_product")
        self.enabled_curves = kwargs.get("enabled_curves")
        self.enabled_usb_itf = kwargs.get("enabled_usb_itf")
        self.led_driver = kwargs.get("led_driver")

    @property
    def vid(self):
        if not self.vidpid:
            return None
        return (self.vidpid[0] << 8) | self.vidpid[1]

    @vid.setter
    def vid(self, value):
        if not self.vidpid:
            self.vidpid = bytearray(4)
        self.vidpid[0] = (value >> 8) & 0xFF
        self.vidpid[1] = value & 0xFF

    @property
    def pid(self):
        if not self.vidpid:
            return None
        return (self.vidpid[2] << 8) | self.vidpid[3]

    @pid.setter
    def pid(self, value):
        if not self.vidpid:
            self.vidpid = bytearray(4)
        self.vidpid[2] = (value >> 8) & 0xFF
        self.vidpid[3] = value & 0xFF

    @staticmethod
    def _u16be(x): return x.to_bytes(2, "big")
    @staticmethod
    def _u32be(x): return x.to_bytes(4, "big")
    @staticmethod
    def _read_u16be(buf, off): return int.from_bytes(buf[off:off+2], "big")
    @staticmethod
    def _read_u32be(buf, off): return int.from_bytes(buf[off:off+4], "big")

    def serialize(self) -> bytes:
        b = bytearray()
        if self.vidpid:
            b += bytes([PhyTag.VIDPID, 4])
            b += bytes(self.vidpid[:4])
        if self.led_gpio is not None:
            b += bytes([PhyTag.LED_GPIO, 1, self.led_gpio & 0xFF])
        if self.led_brightness is not None:
            b += bytes([PhyTag.LED_BTNESS, 1, self.led_brightness & 0xFF])
        b += bytes([PhyTag.OPTS, 2]) + self._u16be(self.opts)
        if self.up_btn is not None:
            b += bytes([PhyTag.UP_BTN, 1, self.up_btn & 0xFF])
        if self.usb_product:
            s = self.usb_product.encode("ascii", "ignore")
            b += bytes([PhyTag.USB_PRODUCT, len(s) + 1]) + s + b"\x00"
        if self.enabled_curves is not None:
            b += bytes([PhyTag.ENABLED_CURVES, 4]) + self._u32be(self.enabled_curves)
        if self.enabled_usb_itf is not None:
            b += bytes([PhyTag.ENABLED_USB_ITF, 1, self.enabled_usb_itf & 0xFF])
        if self.led_driver is not None:
            b += bytes([PhyTag.LED_DRIVER, 1, self.led_driver & 0xFF])
        return bytes(b)

    @classmethod
    def parse(cls, data: bytes) -> "PhyData":
        o = cls()
        p = 0
        end = len(data)
        while p + 2 <= end:
            tag = data[p]
            tlen = data[p + 1]
            p += 2
            if p + tlen > end:
                break
            if tag == PhyTag.VIDPID and tlen == 4:
                o.vidpid = data[p:p+4]
                p += 4
            elif tag == PhyTag.LED_GPIO and tlen == 1:
                o.led_gpio = data[p]; p += 1
            elif tag == PhyTag.LED_BTNESS and tlen == 1:
                o.led_brightness = data[p]; p += 1
            elif tag == PhyTag.OPTS and tlen == 2:
                o.opts = cls._read_u16be(data, p); p += 2
            elif tag == PhyTag.UP_BTN and tlen == 1:
                o.up_btn = data[p]; p += 1
            elif tag == PhyTag.USB_PRODUCT and tlen > 0:
                raw = data[p:p+tlen]
                if 0 in raw: raw = raw.split(b"\x00", 1)[0]
                o.usb_product = raw.decode("ascii", "ignore")
                p += tlen
            elif tag == PhyTag.ENABLED_CURVES and tlen == 4:
                o.enabled_curves = cls._read_u32be(data, p); p += 4
            elif tag == PhyTag.ENABLED_USB_ITF and tlen == 1:
                o.enabled_usb_itf = data[p]; p += 1
            elif tag == PhyTag.LED_DRIVER and tlen == 1:
                o.led_driver = data[p]; p += 1
            else:
                p += tlen
        if o.enabled_usb_itf is None:
            o.enabled_usb_itf = (
                PhyUsbItf.CCID
                | PhyUsbItf.WCID
                | PhyUsbItf.HID
                | PhyUsbItf.KB
            )
        return o

    def __repr__(self):
        vals = [f"{k}={v!r}" for k, v in vars(self).items() if v not in (None, "")]
        return f"PhyData({', '.join(vals)})"

    def __eq__(self, other):
        if not isinstance(other, PhyData):
            return NotImplemented
        return vars(self) == vars(other)

    def copy(self) -> "PhyData":
        """Create a copy of this PhyData."""
        return PhyData(
            vidpid=bytearray(self.vidpid) if self.vidpid else None,
            led_gpio=self.led_gpio,
            led_brightness=self.led_brightness,
            opts=self.opts,
            up_btn=self.up_btn,
            usb_product=self.usb_product,
            enabled_curves=self.enabled_curves,
            enabled_usb_itf=self.enabled_usb_itf,
            led_driver=self.led_driver,
        )

    def set_vidpid(self, vid: int, pid: int) -> "PhyData":
        """Set VID and PID. Returns self for chaining."""
        self.vidpid = bytearray(4)
        self.vid = vid
        self.pid = pid
        return self

    def set_vidpid_from_vendor(self, vendor: Tuple[int, int]) -> "PhyData":
        """Set VID/PID from a KnownVendor tuple. Returns self for chaining."""
        return self.set_vidpid(vendor[0], vendor[1])

    def set_led(self, gpio: Optional[int] = None, brightness: Optional[int] = None, 
                driver: Optional[int] = None) -> "PhyData":
        """Set LED configuration. Returns self for chaining."""
        if gpio is not None:
            self.led_gpio = gpio
        if brightness is not None:
            self.led_brightness = brightness
        if driver is not None:
            self.led_driver = driver
        return self

    def set_option(self, opt: int, enabled: bool = True) -> "PhyData":
        """Set or clear a physical option flag. Returns self for chaining."""
        if enabled:
            self.opts |= opt
        else:
            self.opts &= ~opt
        return self

    def set_curve(self, curve: int, enabled: bool = True) -> "PhyData":
        """Enable or disable a cryptographic curve. Returns self for chaining."""
        if self.enabled_curves is None:
            self.enabled_curves = 0
        if enabled:
            self.enabled_curves |= curve
        else:
            self.enabled_curves &= ~curve
        return self

    @property
    def is_led_dimmable(self) -> bool:
        return bool(self.opts & PhyOpt.DIMM)

    @is_led_dimmable.setter
    def is_led_dimmable(self, value: bool):
        self.set_option(PhyOpt.DIMM, value)

    @property
    def is_power_reset_disabled(self) -> bool:
        return bool(self.opts & PhyOpt.DISABLE_POWER_RESET)

    @is_power_reset_disabled.setter
    def is_power_reset_disabled(self, value: bool):
        self.set_option(PhyOpt.DISABLE_POWER_RESET, value)

    @property
    def is_led_steady(self) -> bool:
        return bool(self.opts & PhyOpt.LED_STEADY)

    @is_led_steady.setter
    def is_led_steady(self, value: bool):
        self.set_option(PhyOpt.LED_STEADY, value)
