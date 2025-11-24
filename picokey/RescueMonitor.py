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

import usb.core
import threading
import time
from .RescuePicoKey import RescuePicoKey

class RescueMonitorObserver:
    def __init__(self):
        pass

    def notifyObservers(self, actions):
        func = getattr(self, "update", None)
        if callable(func):
            func(actions)

    def on_connect(self, device):
        self.notifyObservers((device, None))

    def on_disconnect(self, device):
        self.notifyObservers((None, device))

class RescueMonitor:
    def __init__(self, device: RescuePicoKey, cls_callback: RescueMonitorObserver, interval=0.5):
        self._dev = device
        self._cls_callback = cls_callback
        self.interval = interval
        self._running = False
        self._device_present = False
        self._thread = None
        self.start()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join()

    def _run(self):
        while self._running:
            dev = usb.core.find(idVendor=self._dev.device.idVendor, idProduct=self._dev.device.idProduct)

            if dev and not self._device_present:
                # Device connected
                self._device_present = True
                if self._cls_callback:
                    self._cls_callback.on_connect(dev)

            if not dev and self._device_present:
                # Device disconnected
                self._device_present = False
                if self._cls_callback:
                    self._cls_callback.on_disconnect(self._dev)

            time.sleep(self.interval)
