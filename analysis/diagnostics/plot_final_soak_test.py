#!/usr/bin/env python3
"""The final soak visualization is create-once evidence."""

from __future__ import annotations

from pathlib import Path
import tempfile
import inspect

import plot_final_soak as soak_plot


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="stratolink-soak-plot-") as raw:
        output = Path(raw) / "soak.png"
        output.write_bytes(b"preserved")
        try:
            soak_plot.output_paths(output)
        except SystemExit as error:
            assert "refusing to overwrite" in str(error)
        else:
            raise AssertionError("soak plot accepted an existing output")
        assert output.read_bytes() == b"preserved"
    source = inspect.getsource(soak_plot.main)
    assert "float(vstor.max()) + 150" in source
    assert "nominal VBAT_OV 5363 mV" in source
    assert "cadence_temp_corr" in source
    assert "descriptive" in source
    assert 'colorbar.set_label("end temperature (°C)")' in source
    print("PASS: final soak plot refuses overwrite")


if __name__ == "__main__":
    main()
