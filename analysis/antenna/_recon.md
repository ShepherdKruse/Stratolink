# Stratolink telemetry recon
_generated 2026-06-01T01:17:56.429838Z_

- URL host: `None`
- creds present: URL=False KEY=False

ERROR: TypeError unsupported operand type(s) for +: 'NoneType' and 'str'
```
Traceback (most recent call last):
  File "/Users/twarn/Repositories/Stratolink/analysis/antenna/00_recon.py", line 32, in <module>
    rows, cr = get("telemetry?select=*&limit=1")
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/twarn/Repositories/Stratolink/analysis/antenna/00_recon.py", line 20, in get
    URL + "/rest/v1/" + path,
    ~~~~^~~~~~~~~~~~~
TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'

```