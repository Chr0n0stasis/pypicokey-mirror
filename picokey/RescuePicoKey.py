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

import time
import usb.core
import usb.util
import libusb_package
import usb.backend.libusb1
from .ICCD import ICCD
from .core.log import get_logger

logger = get_logger("RescuePicoKey")

class RescuePicoKey:

    def __init__(self):
        logger.debug("Initializing RescuePicoKey...")
        self.__dev = None
        self.__in = None
        self.__out = None
        self.__int = None
        self.__active = None

        class find_class(object):
            def __init__(self, class_):
                self._class = class_
            def __call__(self, device):
                if device.bDeviceClass == self._class:
                    return True
                for cfg in device:
                    intf = usb.util.find_descriptor(cfg, bInterfaceClass=self._class)
                    if intf is not None:
                        return True
                return False

        logger.debug("Searching for USB device...")
        backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
        try:
            devs = usb.core.find(find_all=True, custom_match=find_class(0x0B), backend=backend)
        except Exception as e:
            logger.error("Exception during usb.core.find: %s", e)
            devs = []
        found = False
        for dev in devs:
            if (dev.manufacturer == 'Pol Henarejos'):
                logger.debug("Found device")
                dev.set_configuration()
                logger.debug("Device configuration set")
                logger.debug("Getting active configuration...")
                cfg = dev.get_active_configuration()
                for intf in cfg:
                    if (intf.bInterfaceClass == 0xFF):
                        epin,epint = None,None
                        epo = usb.util.find_descriptor(intf, find_all=True, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
                        epi = usb.util.find_descriptor(intf, find_all=True, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
                        for ep in list(epi):
                            if (usb.util.endpoint_type(ep.bmAttributes) == usb.util.ENDPOINT_TYPE_INTR):
                                epint = ep
                            else:
                                epin = ep
                        epout = list(epo)
                        self.__dev = dev
                        self.__in = epin.bEndpointAddress
                        self.__out = epout[0].bEndpointAddress
                        self.__int = epint.bEndpointAddress if epint else None
                        logger.debug(f"Endpoints - IN: 0x{self.__in:02X}, OUT: 0x{self.__out:02X}, INT: {self.__int}")
                        self.__iccd = ICCD(self)
                        logger.debug("ICCD interface initialized")
                        self.__active = None
                        logger.debug("Powering off device")
                        self.powerOff()
                        logger.debug("Device powered off")
                        found = True
                        break
        if (not found):
            logger.error("No suitable device found")
            raise Exception('Not found any Pico Key device')

    @property
    def device(self):
        return self.__dev

    def close(self):
        logger.debug("Closing device")
        if self.__dev:
            logger.debug("Disposing USB resources")
            usb.util.dispose_resources(self.__dev)
            logger.debug("Device closed")
            self.__dev = None

    def has_card(self):
        return self.__dev is not None

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def __del__(self):
        self.close()

    def __str__(self):
        return str(self.__dev)

    def read(self, timeout=2000):
        logger.debug("Reading data from device")
        ret = self.__dev.read(self.__in, 4096, timeout)
        logger.trace(f"Data read from device: {' '.join([f'{x:02X}' for x in ret])}")
        logger.debug("Read data from device")
        return ret

    def write(self, data, timeout=2000):
        logger.debug("Writing data to device")
        logger.trace(f"Data to write to device: {' '.join([f'{x:02X}' for x in data])}")
        assert(self.__dev.write(self.__out, data, timeout) == len(data))
        logger.debug("Wrote data to device")

    def exchange(self, data, timeout=2000):
        logger.debug("Exchanging data with device")
        try:
            self.write(data=data, timeout=timeout)
        except Exception as e:
            logger.error("USB write error: " + str(e))
            raise Exception("USB write error: " + str(e))
        try:
            ret = self.read(timeout=timeout)
        except Exception as e:
            logger.error("USB read error: " + str(e))
            raise Exception("USB read error: " + str(e))
        return ret

    def powerOn(self):
        logger.debug("Powering on device")
        if (not self.__active):
            self.__active = True
            logger.debug("Device powered on")
            return self.__iccd.IccPowerOn()

    def powerOff(self):
        logger.debug("Powering off device")
        if (self.__active or self.__active is None):
            logger.debug("Device powered off")
            self.__iccd.IccPowerOff()
            logger.debug("ICCD powered off")
            self.__active = False

    def transmit(self, apdu):
        if (not self.__active):
            self.powerOn()
        rapdu = self.__iccd.SendApdu(apdu=apdu)
        return rapdu[:-2], rapdu[-2], rapdu[-1]

    def reconnect(self):
        logger.debug("Reconnecting to device")
        self.close()
        time.sleep(1)
        self.__init__()
        logger.debug("Reconnected to device")
        return self
