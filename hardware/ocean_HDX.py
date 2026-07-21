"""USB control for an Ocean Optics/Ocean Insight HDX spectrometer, via the
vendor OceanDirect Python SDK (`oceandirect.OceanDirectAPI`) - not a
hand-rolled protocol like the other drivers in this package.

This wraps the SDK the same way OceanView's "Fluorescence" application does:
capture a dark/background spectrum once (probe capped / excitation off) and
store it on the device, then every spectrum acquired afterwards is
automatically corrected against it -

    api.find_usb_devices() -> api.get_device_ids() -> api.open_device(id)
                            -> Spectrometer, already open
    device.set_stored_dark_spectrum(spectrum)  -> stash a background spectrum
    device.get_dark_corrected_spectrum2()      -> acquire + subtract stored background

Note: `find_usb_devices()` returns a device *count*, not a list of devices -
device handles come from `get_device_ids()` + `open_device(id)`.
"""

from oceandirect.OceanDirectAPI import OceanDirectAPI

DEFAULT_INTEGRATION_TIME_US = 100_000  # 100 ms


class OceanHDX:
    def __init__(self, integration_time_us=DEFAULT_INTEGRATION_TIME_US):
        self._api = OceanDirectAPI()
        self._api.find_usb_devices()
        device_ids = self._api.get_device_ids()
        if not device_ids:
            raise RuntimeError("No Ocean HDX device found over USB.")

        self._device = self._api.open_device(device_ids[0])
        self._has_background = False
        self.set_integration_time(integration_time_us)

    def close(self):
        self._device.close_device()
        self._api.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def set_integration_time(self, microseconds):
        self._device.set_integration_time(microseconds)

    def get_wavelengths(self):
        return self._device.get_wavelengths()

    def get_raw_spectrum(self):
        """Acquire a spectrum with no background subtraction."""
        return self._device.get_formatted_spectrum()

    def capture_background(self):
        """Acquire and store a dark/background spectrum - call this once
        during calibration (probe capped / excitation off), before measuring
        any samples. Every get_spectrum() call afterwards is corrected
        against the spectrum captured here."""
        background = self._device.get_formatted_spectrum()
        self._device.set_stored_dark_spectrum(background)
        self._has_background = True
        return background

    def get_spectrum(self):
        """Acquire a spectrum with the stored background subtracted (the
        same correction OceanView's Fluorescence app applies). Requires
        capture_background() to have been called first."""
        if not self._has_background:
            raise RuntimeError("No background captured yet - call capture_background() first.")
        return self._device.get_dark_corrected_spectrum2()


if __name__ == "__main__":
    with OceanHDX() as spec:
        wavelengths = spec.get_wavelengths()
        print(f"Wavelength range: {wavelengths[0]:.1f} - {wavelengths[-1]:.1f} nm")

        input("Cap the probe / block excitation, then press Enter to capture background...")
        spec.capture_background()

        input("Uncap / start excitation, then press Enter to capture a sample spectrum...")
        spectrum = spec.get_spectrum()
        print(f"Peak intensity: {max(spectrum):.1f} at {wavelengths[spectrum.index(max(spectrum))]:.1f} nm")
