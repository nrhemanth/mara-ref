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

import getpass
import time
from dataclasses import dataclass

from oceandirect.OceanDirectAPI import OceanDirectAPI

DEFAULT_INTEGRATION_TIME_US = 100_000  # 100 ms


@dataclass
class OceanHDXMetadata:
    """Snapshot of the device's acquisition settings, in the same terms
    OceanView's own .txt export reports them - see format_oceanview_txt()."""

    model: str
    serial_number: str
    trigger_mode: int
    integration_time_us: int
    scans_to_average: int
    nonlinearity_correction_enabled: bool
    boxcar_width: int
    storing_dark_spectrum: bool
    num_pixels: int


def _format_scientific(value: float) -> str:
    """Java/OceanView-style scientific notation - no leading zero in the
    exponent (e.g. "5.000000E-1"), unlike Python's own "%E" ("5.000000E-01")."""
    mantissa, _, exponent = f"{value:.6E}".partition("E")
    sign, digits = exponent[0], exponent[1:].lstrip("0") or "0"
    return f"{mantissa}E{sign}{digits}"


def format_oceanview_txt(
    filename: str,
    metadata: OceanHDXMetadata,
    wavelengths: list[float],
    intensities: list[float],
) -> str:
    """Render a spectrum as text in OceanView's own export format (header
    metadata block + ">>>>>Begin Spectral Data<<<<<" + space-separated
    wavelength/intensity rows, no column-heading row), so files saved by
    this codebase's acquisition scripts are readable by DataLab the same
    way files exported directly from OceanView are."""
    lines = [
        f"Data from {filename} Node",
        "",
        f"Date: {time.strftime('%a %b %d %H:%M:%S %Z %Y')}",
        f"User: {getpass.getuser()}",
        f"Spectrometer: {metadata.serial_number}",
        f"Trigger mode: {metadata.trigger_mode}",
        f"Integration Time (sec): {_format_scientific(metadata.integration_time_us / 1_000_000)}",
        f"Scans to average: {metadata.scans_to_average}",
        f"Nonlinearity correction enabled: {str(metadata.nonlinearity_correction_enabled).lower()}",
        f"Boxcar width: {metadata.boxcar_width}",
        f"Storing dark spectrum: {str(metadata.storing_dark_spectrum).lower()}",
        "XAxis mode: Wavelengths",
        f"Number of Pixels in Spectrum: {metadata.num_pixels}",
        ">>>>>Begin Spectral Data<<<<<",
    ]
    lines.extend(f"{w} {i}" for w, i in zip(wavelengths, intensities))
    return "\n".join(lines) + "\n"


class OceanHDX:
    def __init__(self, integration_time_us=DEFAULT_INTEGRATION_TIME_US):
        self._api = OceanDirectAPI()
        self._api.find_usb_devices()
        device_ids = self._api.get_device_ids()
        if not device_ids:
            raise RuntimeError("No Ocean HDX device found over USB.")

        self._device = self._api.open_device(device_ids[0])
        # get_dark_corrected_spectrum2() does its own dark correction against
        # the stored background - the device's built-in ("legacy") electric
        # dark/nonlinearity correction must be off or the SDK raises
        # ERROR_DARK_NONLINEARITY_CORRECTION_CONFLICT.
        self._device.set_electric_dark_correction_usage(False)
        self._device.set_nonlinearity_correction_usage(False)
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

    def get_metadata(self) -> OceanHDXMetadata:
        """Read the device's current acquisition settings - pass this to
        format_oceanview_txt() alongside a spectrum to write it out in
        OceanView's own .txt export format."""
        return OceanHDXMetadata(
            model=self._device.get_model(),
            serial_number=self._device.get_serial_number(),
            trigger_mode=self._device.get_trigger_mode(),
            integration_time_us=self._device.get_integration_time(),
            scans_to_average=self._device.get_scans_to_average(),
            nonlinearity_correction_enabled=self._device.get_nonlinearity_correction_usage(),
            boxcar_width=self._device.get_boxcar_width(),
            storing_dark_spectrum=self._has_background,
            num_pixels=self._device.get_spectrum_length(),
        )


if __name__ == "__main__":
    with OceanHDX() as spec:
        wavelengths = spec.get_wavelengths()
        print(f"Wavelength range: {wavelengths[0]:.1f} - {wavelengths[-1]:.1f} nm")

        input("Cap the probe / block excitation, then press Enter to capture background...")
        spec.capture_background()

        input("Uncap / start excitation, then press Enter to capture a sample spectrum...")
        spectrum = spec.get_spectrum()
        print(f"Peak intensity: {max(spectrum):.1f} at {wavelengths[spectrum.index(max(spectrum))]:.1f} nm")
