# First combined candidate — rejected

Frozen PCB SHA `804094fbd6ba36ff1dce9fbbe0d9976d04e665df2e5612f2b2ada4805dcaae7e`, preserved in external scratch `stratolink-edges-20261012/combined`. It was never promoted to canonical hardware.

Independent integration review found two trace-to-header clearances below the retained 0.20 mm net-class rule after the pads grew: J4.1 to the VSTOR diagonal was 0.1954 mm, and J3.4 to the long +SOLAR side run was 0.1968 mm. The original standalone route trial had checked the smaller pads. Root requested additional local bends with unchanged trace widths and holes, retaining at least the sourced 0.20 mm edge gap. The intentionally 0.12 mm header-to-header gaps are a separate, documented fabrication choice.
