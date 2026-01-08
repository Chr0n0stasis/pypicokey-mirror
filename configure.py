#!/usr/bin/env python3
"""Interactive commissioning helper for PicoKey

This script collects commissioning options (VID:PID, LED, options,
product name, curves, etc.) and applies them to a connected PicoKey device
using the pypicokey library.

Usage:
  python configure.py              # interactive mode, apply to device
  python configure.py --save       # save config to JSON file
  python configure.py --load cfg.json --apply  # load and apply config
  python configure.py --show       # show current device configuration

"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Import picokey modules
try:
    from picokey import (
        PicoKey, PhyData, PhyOpt, PhyCurve, PhyLedDriver, KnownVendor,
        PicoKeyNotFoundError, PicoKeyInvalidStateError
    )
    PICOKEY_AVAILABLE = True
except ImportError as e:
    PICOKEY_AVAILABLE = False
    PICOKEY_IMPORT_ERROR = str(e)


CFG_OUT = "commission_config.json"
VIDPID_RE = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{4}$")

# LED Driver name mapping
LED_DRIVER_MAP = {
    "PICO": PhyLedDriver.PICO if PICOKEY_AVAILABLE else 0x1,
    "PIMORONI": PhyLedDriver.PIMORONI if PICOKEY_AVAILABLE else 0x2,
    "WS2812": PhyLedDriver.WS2812 if PICOKEY_AVAILABLE else 0x3,
    "CYW43": PhyLedDriver.CYW43 if PICOKEY_AVAILABLE else 0x4,
    "NEOPIXEL": PhyLedDriver.NEOPIXEL if PICOKEY_AVAILABLE else 0x5,
    "NONE": PhyLedDriver.NONE if PICOKEY_AVAILABLE else 0xFF,
}
LED_DRIVER_NAMES = list(LED_DRIVER_MAP.keys())


def prompt(text: str, default: Optional[str] = None) -> Optional[str]:
    if default is None:
        val = input(f"{text} ")
    else:
        val = input(f"{text} [Default: {default}] ")
    if val.strip() == "":
        return None
    return val.strip()


def prompt_int(text: str, default: Optional[int] = None, allow_empty=True) -> Optional[int]:
    while True:
        s = prompt(text, str(default) if default is not None else None)
        if s is None:
            return None if allow_empty else default
        try:
            return int(s)
        except ValueError:
            print("Please enter an integer or leave empty. / 请输入整数或留空。")


def prompt_bool(text: str, default: Optional[bool] = None) -> Optional[bool]:
    while True:
        defstr = None if default is None else ("y" if default else "n")
        s = prompt(text + " (y/n)", defstr)
        if s is None:
            return None
        if s.lower() in ("y", "yes", "t", "1"):
            return True
        if s.lower() in ("n", "no", "f", "0"):
            return False
        print("Please enter y or n, or leave empty to keep current value. / 请输入 y 或 n，或留空以保持当前值。")


def choose(text: str, choices: list[str], default: Optional[int] = None) -> Optional[str]:
    print(text)
    for i, c in enumerate(choices, start=1):
        print(f"  {i}. {c}")
    sel = prompt_int("Select number (leave empty to keep current) / 选择编号 (留空保持当前):", default=None)
    if sel is None:
        return None
    if 1 <= sel <= len(choices):
        return choices[sel - 1]
    print("Invalid selection, leave empty to keep current. / 无效选择，留空以保持当前。")
    return None


def validate_vidpid(v: str) -> bool:
    return bool(VIDPID_RE.match(v))


# ==================== System Helpers ====================

def check_linux_usb_permissions() -> tuple[bool, str]:
    """Check Linux USB device permissions and provide solutions."""
    if platform.system() != "Linux":
        return True, ""
    
    if os.geteuid() == 0:
        return True, "Running as root"
    
    try:
        groups = subprocess.check_output(["groups"], text=True).strip()
        has_plugdev = "plugdev" in groups
        has_dialout = "dialout" in groups
    except Exception:
        has_plugdev = False
        has_dialout = False
    
    if not (has_plugdev or has_dialout):
        msg = (
            "\n⚠️  USB Permission Warning / USB权限警告:\n"
            "Accessing USB devices on Linux requires special permissions.\n"
            "在Linux上访问USB设备需要特殊权限。\n\n"
            "Solution / 解决方案：sudo python3 configure.py\n"
        )
        return False, msg
    
    return True, ""


def list_usb_devices() -> None:
    """List USB devices for diagnostics."""
    if platform.system() == "Linux":
        try:
            output = subprocess.check_output(["lsusb"], text=True)
            print("\nDetected USB devices / 检测到的USB设备：")
            for line in output.split("\n"):
                if any(vid in line.lower() for vid in ["20a0", "1050", "feff", "234b", "1209"]):
                    print(f"  ✓ {line}")
        except Exception:
            pass
    elif platform.system() == "Darwin":
        try:
            subprocess.check_output(["system_profiler", "SPUSBDataType"], text=True, timeout=5)
            print("\nUSB devices detected (excerpt) / 检测到的USB设备（摘要）")
        except Exception:
            pass


# ==================== Interactive Configuration ====================

def interactive_build(current_phy: Optional[PhyData] = None) -> PhyData:
    """Build PhyData interactively, optionally starting from current device config."""
    print("\n" + "="*60)
    print("PicoKey Interactive Configuration / PicoKey 交互式配置")
    print("="*60)
    print("Leave empty to keep current values. / 留空以保留当前值。\n")

    # Start with current config or empty
    phy = current_phy.copy() if current_phy else PhyData()

    # Show current VID:PID if available
    if phy.vid is not None and phy.pid is not None:
        print(f"Current VID:PID / 当前 VID:PID: {phy.vid:04x}:{phy.pid:04x}")

    # Vendor / VID:PID selection - use KnownVendor from picokey
    vendor_names = list(KnownVendor.get_all().keys()) + ["Custom VID:PID"]
    vendor_choice = choose("\nSelect a known vendor / 选择已知厂商:", vendor_names, None)
    
    if vendor_choice == "Custom VID:PID":
        while True:
            v = prompt("Type VID:PID in hex form (e.g. 20a0:42b1):")
            if v is None:
                break
            if validate_vidpid(v):
                vid_str, pid_str = v.split(":")
                phy.set_vidpid(int(vid_str, 16), int(pid_str, 16))
                break
            print("Invalid format. Use: 0123:abcd (hex) / 格式错误，形如 0123:abcd")
    elif vendor_choice and vendor_choice in KnownVendor.get_all():
        vendor_tuple = KnownVendor.get_all()[vendor_choice]
        phy.set_vidpid_from_vendor(vendor_tuple)
        print(f"  → VID:PID set to {vendor_tuple[0]:04x}:{vendor_tuple[1]:04x}")

    # LED Configuration
    print("\n--- LED Configuration / LED 配置 ---")
    if phy.led_gpio is not None:
        print(f"Current LED GPIO: {phy.led_gpio}")
    led_gpio = prompt_int("LED GPIO pin (number):", default=phy.led_gpio)
    if led_gpio is not None:
        phy.led_gpio = led_gpio

    if phy.led_brightness is not None:
        print(f"Current LED brightness: {phy.led_brightness}")
    led_brightness = prompt_int("LED brightness (0-255, 0=off):", default=phy.led_brightness)
    if led_brightness is not None:
        phy.led_brightness = led_brightness

    # LED Driver
    current_driver_name = None
    if phy.led_driver is not None:
        for name, val in LED_DRIVER_MAP.items():
            if val == phy.led_driver:
                current_driver_name = name
                break
        if current_driver_name:
            print(f"Current LED driver: {current_driver_name}")
    
    led_driver_choice = choose("Select LED driver / 选择 LED 驱动:", LED_DRIVER_NAMES, None)
    if led_driver_choice:
        phy.led_driver = LED_DRIVER_MAP[led_driver_choice]

    # Options
    print("\n--- Options / 选项 ---")
    
    led_dimmable = prompt_bool(f"LED dimmable? (current: {phy.is_led_dimmable})", default=None)
    if led_dimmable is not None:
        phy.is_led_dimmable = led_dimmable

    power_cycle = prompt_bool(f"Enable power-cycle reset? (current: {not phy.is_power_reset_disabled})", default=None)
    if power_cycle is not None:
        phy.is_power_reset_disabled = not power_cycle

    led_steady = prompt_bool(f"LED steady (always on)? (current: {phy.is_led_steady})", default=None)
    if led_steady is not None:
        phy.is_led_steady = led_steady

    # Presence timeout
    print("\n--- User Presence / 用户存在检测 ---")
    if phy.up_btn is not None:
        print(f"Current presence timeout: {phy.up_btn}s")
    presence = prompt_int("Presence button timeout (seconds, 0=disabled):", default=phy.up_btn)
    if presence is not None:
        phy.up_btn = presence

    # Curves
    print("\n--- Cryptographic Curves / 加密曲线 ---")
    current_secp256k1 = bool(phy.enabled_curves and (phy.enabled_curves & PhyCurve.SECP256K1))
    secp256k1 = prompt_bool(f"Enable secp256k1? (current: {current_secp256k1}, note: Android may not support)", default=None)
    if secp256k1 is not None:
        phy.set_curve(PhyCurve.SECP256K1, secp256k1)

    # USB Product Name
    print("\n--- USB Product Name / USB 产品名称 ---")
    if phy.usb_product:
        print(f"Current product name: {phy.usb_product}")
    product_name = prompt("Product name (max 14 chars):")
    if product_name is not None:
        if len(product_name) > 14:
            print("Truncating to 14 characters. / 截断至14字符。")
            product_name = product_name[:14]
        phy.usb_product = product_name

    return phy


def phy_to_dict(phy: PhyData) -> dict:
    """Convert PhyData to a JSON-serializable dict."""
    cfg = {}
    if phy.vid is not None and phy.pid is not None:
        cfg["vidpid"] = f"{phy.vid:04x}:{phy.pid:04x}"
    if phy.led_gpio is not None:
        cfg["led_gpio"] = phy.led_gpio
    if phy.led_brightness is not None:
        cfg["led_brightness"] = phy.led_brightness
    if phy.led_driver is not None:
        for name, val in LED_DRIVER_MAP.items():
            if val == phy.led_driver:
                cfg["led_driver"] = name
                break
    cfg["options"] = {
        "led_dimmable": phy.is_led_dimmable,
        "power_cycle_on_reset": not phy.is_power_reset_disabled,
        "led_steady": phy.is_led_steady,
    }
    if phy.up_btn is not None:
        cfg["presence_timeout"] = phy.up_btn
    if phy.enabled_curves is not None:
        cfg["secp256k1"] = bool(phy.enabled_curves & PhyCurve.SECP256K1)
    if phy.usb_product:
        cfg["product_name"] = phy.usb_product
    return cfg


def dict_to_phy(cfg: dict) -> PhyData:
    """Convert a config dict to PhyData."""
    phy = PhyData()
    
    vidpid = cfg.get("vidpid")
    if vidpid and validate_vidpid(vidpid):
        vid_str, pid_str = vidpid.split(":")
        phy.set_vidpid(int(vid_str, 16), int(pid_str, 16))
    
    if cfg.get("led_gpio") is not None:
        phy.led_gpio = cfg["led_gpio"]
    if cfg.get("led_brightness") is not None:
        phy.led_brightness = cfg["led_brightness"]
    
    led_driver = cfg.get("led_driver")
    if led_driver and led_driver in LED_DRIVER_MAP:
        phy.led_driver = LED_DRIVER_MAP[led_driver]
    
    opts = cfg.get("options", {})
    if opts.get("led_dimmable"):
        phy.set_option(PhyOpt.DIMM, True)
    if not opts.get("power_cycle_on_reset", True):
        phy.set_option(PhyOpt.DISABLE_POWER_RESET, True)
    if opts.get("led_steady"):
        phy.set_option(PhyOpt.LED_STEADY, True)
    
    if cfg.get("presence_timeout") is not None:
        phy.up_btn = cfg["presence_timeout"]
    
    if cfg.get("secp256k1"):
        phy.set_curve(PhyCurve.SECP256K1, True)
    
    if cfg.get("product_name"):
        phy.usb_product = cfg["product_name"]
    
    return phy


# ==================== Device Operations ====================

def connect_device() -> Optional[PicoKey]:
    """Connect to PicoKey device with error handling."""
    if not PICOKEY_AVAILABLE:
        print(f"✗ picokey library not available: {PICOKEY_IMPORT_ERROR}")
        print("\nInstall with: pip install pypicokey")
        return None
    
    # Linux permission check
    if platform.system() == "Linux":
        has_perm, perm_msg = check_linux_usb_permissions()
        if not has_perm:
            print(perm_msg)
    
    try:
        print("Connecting to PicoKey device... / 正在连接 PicoKey 设备...")
        pk = PicoKey()
        print(f"✓ Connected: {pk.platform.name} / {pk.product.name} v{pk.version[0]}.{pk.version[1]}")
        if pk.serial_number:
            print(f"  Serial: {pk.serial_number:016X}")
        return pk
    except PicoKeyNotFoundError:
        print("✗ No PicoKey device found. / 未找到 PicoKey 设备。")
        list_usb_devices()
        return None
    except PermissionError as e:
        print(f"✗ Permission error: {e}")
        if platform.system() == "Linux":
            print("Try: sudo python3 configure.py")
        return None
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return None


def show_current_config(pk: PicoKey) -> Optional[PhyData]:
    """Read and display current device configuration."""
    print("\n--- Current Device Configuration / 当前设备配置 ---")
    phy = pk.get_phy()
    if phy is None:
        print("Unable to read configuration. / 无法读取配置。")
        return None
    
    if phy.vid is not None and phy.pid is not None:
        print(f"  VID:PID: {phy.vid:04X}:{phy.pid:04X}")
    if phy.led_gpio is not None:
        print(f"  LED GPIO: {phy.led_gpio}")
    if phy.led_brightness is not None:
        print(f"  LED Brightness: {phy.led_brightness}")
    if phy.led_driver is not None:
        driver_name = "Unknown"
        for name, val in LED_DRIVER_MAP.items():
            if val == phy.led_driver:
                driver_name = name
                break
        print(f"  LED Driver: {driver_name}")
    print(f"  LED Dimmable: {phy.is_led_dimmable}")
    print(f"  Power Reset Disabled: {phy.is_power_reset_disabled}")
    print(f"  LED Steady: {phy.is_led_steady}")
    if phy.up_btn is not None:
        print(f"  Presence Timeout: {phy.up_btn}s")
    if phy.usb_product:
        print(f"  USB Product: {phy.usb_product}")
    if phy.enabled_curves:
        print(f"  Enabled Curves: {phy.enabled_curves:#x}")
        if phy.enabled_curves & PhyCurve.SECP256K1:
            print("    - secp256k1 enabled")
    
    return phy


def apply_config(pk: PicoKey, phy: PhyData, ask_confirm: bool = True) -> bool:
    """Apply configuration to device."""
    print("\n--- Configuration to Apply / 将要应用的配置 ---")
    cfg = phy_to_dict(phy)
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    
    if ask_confirm:
        confirm = input("\nApply this configuration? / 应用此配置？(y/N) ")
        if confirm.lower() != "y":
            print("Cancelled. / 已取消。")
            return False
    
    try:
        print("Writing configuration... / 正在写入配置...")
        pk.set_phy(phy)
        print("✓ Configuration applied successfully. / 配置应用成功。")
        
        reboot = input("\nReboot device for changes to take effect? / 重启设备使配置生效？(y/N) ")
        if reboot.lower() == "y":
            pk.reboot()
            print("Device is rebooting... / 设备正在重启...")
        else:
            print("Please manually reboot the device. / 请手动重启设备。")
        
        return True
    except Exception as e:
        print(f"✗ Failed to apply configuration: {e}")
        return False


# ==================== Main ====================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="PicoKey Configuration Tool / PicoKey 配置工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples / 示例:
  python configure.py              # Interactive configuration
  python configure.py --show       # Show current device config
  python configure.py --save       # Save config to JSON
  python configure.py --load cfg.json --apply  # Load and apply
"""
    )
    parser.add_argument("--show", action="store_true", 
                        help="Show current device configuration / 显示当前设备配置")
    parser.add_argument("--save", "-s", metavar="FILE", nargs="?", const=CFG_OUT,
                        help="Save configuration to JSON file / 保存配置到JSON文件")
    parser.add_argument("--load", "-l", metavar="FILE",
                        help="Load configuration from JSON file / 从JSON文件加载配置")
    parser.add_argument("--apply", "-a", action="store_true",
                        help="Apply configuration to device / 应用配置到设备")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip confirmation prompts / 跳过确认提示")
    
    args = parser.parse_args()

    # Connect to device
    pk = connect_device()
    if pk is None:
        sys.exit(1)
    
    try:
        # Show current config
        if args.show:
            show_current_config(pk)
            return
        
        # Load config from file
        if args.load:
            load_path = Path(args.load)
            if not load_path.exists():
                print(f"✗ File not found: {load_path}")
                sys.exit(1)
            cfg = json.loads(load_path.read_text())
            phy = dict_to_phy(cfg)
            print(f"✓ Loaded configuration from {load_path}")
        else:
            # Interactive configuration
            current_phy = pk.get_phy()
            phy = interactive_build(current_phy)
        
        # Save to file
        if args.save:
            save_path = Path(args.save)
            cfg = phy_to_dict(phy)
            save_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
            print(f"✓ Configuration saved to {save_path}")
        
        # Apply to device (default behavior in interactive mode)
        if args.apply or (not args.load and not args.save):
            apply_config(pk, phy, ask_confirm=not args.yes)
    
    finally:
        try:
            pk.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
