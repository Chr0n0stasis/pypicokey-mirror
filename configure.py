#!/usr/bin/env python3
"""Interactive commissioning helper for PicoKey

This script collects commissioning options (VID:PID, LED, options,
product name, curves, etc.) and writes them to a JSON file
(`commission_config.json`). It can optionally attempt to apply the
configuration when `--apply` is passed; the apply action is a safe
stub and will ask for confirmation before performing any hardware
changes.

Usage:
  python configure.py        # interactive
  python configure.py --out mycfg.json
  python configure.py --yes --out mycfg.json
  python configure.py --apply  # will prompt before touching device

"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Optional


CFG_OUT = "commission_config.json"
VIDPID_RE = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{4}$")


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
            print("请输入整数或留空。")


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
        print("请输入 y 或 n，或留空以保持当前值。")


def choose(text: str, choices: list[str], default: Optional[int] = None) -> Optional[str]:
    print(text)
    for i, c in enumerate(choices, start=1):
        print(f"  {i}. {c}")
    sel = prompt_int("选择编号 (留空保持当前):", default=None)
    if sel is None:
        return None
    if 1 <= sel <= len(choices):
        return choices[sel - 1]
    print("无效选择，留空以保持当前。")
    return None


def validate_vidpid(v: str) -> bool:
    return bool(VIDPID_RE.match(v))


def interactive_build() -> dict:
    print("开始交互式 commissioning 配置。留空以保留当前值。")

    # Vendor / VID:PID
    VENDORS = {
        "Nitrokey HSM": {"vid": "20a0", "pid": "4230"},
        "Nitrokey FIDO2": {"vid": "20a0", "pid": "42b1"},
        "Nitrokey Pro": {"vid": "20a0", "pid": "4108"},
        "Nitrokey 3": {"vid": "20a0", "pid": "42b2"},
        "Nitrokey Start": {"vid": "20a0", "pid": "4211"},
        "Yubikey 4/5": {"vid": "1050", "pid": "0407"},
        "Yubikey NEO": {"vid": "1050", "pid": "0116"},
        "Yubico YubiHSM": {"vid": "1050", "pid": "0030"},
        "FSIJ Gnuk": {"vid": "234b", "pid": "0000"},
        "GnuPG e.V.": {"vid": "1209", "pid": "2440"},
    }

    vendor_choices = list(VENDORS.keys()) + ["Custom VID:PID"]
    vendor_choice = choose("Select a known vendor...", vendor_choices, None)
    vidpid = None
    if vendor_choice == "Custom VID:PID":
        while True:
            v = prompt("Type VID:PID in hex form (0123:abcd):")
            if v is None:
                vidpid = None
                break
            if validate_vidpid(v):
                vidpid = v.lower()
                break
            print("格式错误，形如 0123:abcd（十六进制）。")
    elif vendor_choice in VENDORS:
        e = VENDORS[vendor_choice]
        vidpid = f"{e['vid']}:{e['pid']}"

    presence = prompt_int("Presence Button Timeout (seconds, 0=disabled):", default=None)
    led_brightness = prompt_int("LED brightness (0=off):", default=None)

    # Options
    print("Options: 留空保持当前")
    led_dimmable = prompt_bool("LED dimmable?", default=None)
    initialize = prompt_bool("Initialize device (will reset some state)?", default=None)
    secure_boot = prompt_bool("Enable Secure Boot? (WebUSB required)", default=None)
    secure_lock = prompt_bool("Enable Secure Lock? (WebUSB required)", default=None)
    power_cycle = prompt_bool("Power Cycle on Reset? (Pico FIDO only)", default=None)
    led_steady = prompt_bool("LED steady (always on)?", default=None)
    secp256k1 = prompt_bool("Enable secp256k1 curve? (Android may not support)", default=None)

    led_gpio = prompt_int("LED GPIO pin (number):", default=None)

    drivers = ["PICO", "PIMORONI", "WS2812", "CYW43", "NEOPIXEL", "NONE"]
    led_driver = choose("Select a LED driver:", drivers, None)

    product_name = prompt("Product Name (max 14 chars):")
    if product_name is not None and len(product_name) > 14:
        print("Product name 超过 14 字符，将被截断。")
        product_name = product_name[:14]

    cfg = {
        "vendor_choice": vendor_choice,
        "vidpid": vidpid,
        "presence_timeout": presence,
        "led_brightness": led_brightness,
        "options": {
            "led_dimmable": led_dimmable,
            "initialize": initialize,
            "secure_boot": secure_boot,
            "secure_lock": secure_lock,
            "power_cycle_on_reset": power_cycle,
            "led_steady": led_steady,
            "secp256k1": secp256k1,
        },
        "led_gpio": led_gpio,
        "led_driver": led_driver,
        "product_name": product_name,
    }

    return cfg


def build_phy_bytes(cfg: dict) -> bytes:
    # mirror getPhyData() TLV construction
    PHY_VID = 0x0
    PHY_LED_GPIO = 0x4
    PHY_LED_BTNESS = 0x5
    PHY_OPTS = 0x6
    PHY_OPT_WCID = 0x1
    PHY_OPT_DIMM = 0x2
    PHY_OPT_DISABLE_POWER_RESET = 0x4
    PHY_OPT_LED_STEADY = 0x8
    PHY_UP_BUTTON = 0x8
    PHY_USB_PRODUCT = 0x9
    PHY_ENABLED_CURVES = 0xA
    PHY_LED_DRIVER = 0xC

    PHY_CURVE_SECP256K1 = 0x8

    PHY_LED_DRIVER_SINGLE = 0x1
    PHY_LED_DRIVER_WS2812 = 0x3

    b = bytearray()

    # VID/PID
    vidpid = cfg.get("vidpid")
    if vidpid:
        try:
            vid_str, pid_str = vidpid.split(":")
            vid = int(vid_str, 16)
            pid = int(pid_str, 16)
            b += bytes([PHY_VID, 4, (vid >> 8) & 0xFF, vid & 0xFF, (pid >> 8) & 0xFF, pid & 0xFF])
        except Exception:
            pass

    # LED GPIO
    lg = cfg.get("led_gpio")
    if lg is not None:
        b += bytes([PHY_LED_GPIO, 1, int(lg) & 0xFF])

    # LED brightness
    lb = cfg.get("led_brightness")
    if lb is None:
        lb = 0
    b += bytes([PHY_LED_BTNESS, 1, int(lb) & 0xFF])

    # opts
    opts = 0
    opts_map = cfg.get("options", {})
    if opts_map.get("led_dimmable"):
        opts |= PHY_OPT_DIMM
    if not opts_map.get("power_cycle_on_reset"):
        opts |= PHY_OPT_DISABLE_POWER_RESET
    if opts_map.get("led_steady"):
        opts |= PHY_OPT_LED_STEADY

    b += bytes([PHY_OPTS, 2, (opts >> 8) & 0xFF, opts & 0xFF])

    # Presence / Up button timeout
    btn = cfg.get("presence_timeout")
    if btn is None:
        btn = 0
    b += bytes([PHY_UP_BUTTON, 1, int(btn) & 0xFF])

    # curves
    curves = 0
    if opts_map.get("secp256k1"):
        curves |= PHY_CURVE_SECP256K1
    b += bytes([PHY_ENABLED_CURVES, 4, (curves >> 24) & 0xFF, (curves >> 16) & 0xFF, (curves >> 8) & 0xFF, curves & 0xFF])

    # USB product string
    pn = cfg.get("product_name")
    if pn:
        s = pn.encode("ascii", "ignore")
        b += bytes([PHY_USB_PRODUCT, len(s) + 1]) + s + b"\x00"

    # led driver
    ld = cfg.get("led_driver")
    leddrv = 0
    if ld is not None:
        if ld.upper().startswith("WS"):
            leddrv = PHY_LED_DRIVER_WS2812
        elif ld.upper().startswith("PICO"):
            leddrv = PHY_LED_DRIVER_SINGLE
        elif ld.upper() == "NONE":
            leddrv = 0xFF
    b += bytes([PHY_LED_DRIVER, 1, leddrv & 0xFF])

    return bytes(b)


def save_config(cfg: dict, out: Path):
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
    print(f"配置已保存到 {out}")


def apply_stub(cfg: dict) -> None:
    print("\n-- APPLY (STUB) --")
    print("脚本将在此处尝试应用配置到本机已连接的 PicoKey（本地方式）。")
    print("配置摘要:")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    confirm = input("确认要尝试直接应用配置到本机已连接设备吗？(y/N) ")
    if confirm.lower() != "y":
        print("取消应用。配置已保存到文件，可使用本地 picokey 库或其他工具手动应用。")
        return
    # 尝试使用本地 picokey 库把 PHY bytes 写入设备
    try:
        import picokey  # type: ignore
    except Exception as e:
        print("未检测到可用的 picokey 库：", e)
        print("请确保已安装 pypicokey 并在正确的 Python 环境下运行此脚本。")
        return

    def apply_local(cfg: dict) -> None:
        try:
            pk = picokey.PicoKey()
        except Exception as e:
            print("无法连接到 PicoKey 设备：", e)
            return
        try:
            phy = build_phy_bytes(cfg)
            if not phy:
                print("未生成任何 PHY 字节，跳过写入。")
                return
            print(f"准备写入 {len(phy)} 字节到设备...")
            try:
                # PicoKey.phy expects Optional[list[int]] for data
                pk.phy(list(phy))
                print("已成功写入 PHY 配置到设备。")
            except Exception as e:
                print("写入设备时发生错误：", e)
        finally:
            try:
                pk.close()
            except Exception:
                pass

    apply_local(cfg)


def main() -> None:
    parser = argparse.ArgumentParser(description="PicoKey commissioning configurator")
    parser.add_argument("--out", "-o", help="输出 JSON 文件路径", default=CFG_OUT)
    parser.add_argument("--apply", action="store_true", help="交互式确认后尝试应用配置到设备（stub）")
    parser.add_argument("--yes", "-y", action="store_true", help="自动确认所有提示（留空将被视为保留当前值）")
    args = parser.parse_args()

    cfg = interactive_build()

    outpath = Path(args.out)
    if outpath.exists():
        if not args.yes:
            overwrite = input(f"{outpath} 已存在，是否覆盖？(y/N) ")
            if overwrite.lower() != "y":
                print("取消，未保存文件。")
                return
    save_config(cfg, outpath)

    if args.apply:
        apply_stub(cfg)


if __name__ == "__main__":
    main()
