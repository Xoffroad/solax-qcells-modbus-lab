# solax-qcells-modbus-lab

Standalone CLI to test SolaX/QCells Modbus power-control loops independently from openWB/Home Assistant.

## Safety Notice

This tool writes control registers on a live inverter/battery system. Use it only if you understand the impact.

- test in a controlled environment first
- avoid parallel writers to the same Modbus device
- keep physical safety and grid rules in mind
- use at your own risk

## Supported Modes

- Mode `1` (`0x7C` block, Enabled Power Control)
- Mode `4` (`0x7C` block, Push Power-Positive/Negative)
- Mode `8` (`0xA0` block, Individual Setting - Duration)

Mode `12` is intentionally not part of this tool.

## Compatibility

| Vendor | Family | Status |
| --- | --- | --- |
| QCells/SolaX | Hybrid inverter over Modbus TCP | Tested in local lab setup |

If your firmware/model behaves differently, open an issue with command, firmware version, and a short CSV sample.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quickstart

Run mode 1 with defaults and keep running until `Ctrl+C`:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 1 --active-power 0
```

Run mode 8 for 30 minutes and stop discharge:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 8 \
  --push-power 0 --pv-power-limit 30000 --duration 20 --repeat-for 1800
```

Run mode 4 for 30 minutes and stop discharge:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 4 \
  --push-power 0 --mode4-timeout 0 --repeat-for 1800
```

## Defaults

- `--mode 1`
- `--formula ha` (`ap_target = active_power - pv_generation`)
- `--duration 20`
- `--interval 10`
- `--repeat-for 0` (run until `Ctrl+C`)
- CSV output path defaults to `./csv/qcells_mode1_<timestamp>.csv`
- `--disable-on-exit` enabled (`0x7C=0`, `0xA0=0` on exit)
- `--holding-readback` disabled

## Useful Commands

Force fixed discharge command (`+W`) in mode 4:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 4 --push-power 2000 --mode4-timeout 0
```

Force fixed charge command (`-W`) in mode 4:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 4 --push-power -2000 --mode4-timeout 0
```

Force fixed discharge command (`+W`) in mode 8:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 8 --push-power 2000 --pv-power-limit 30000 --duration 20
```

Force fixed charge command (`-W`) in mode 8:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 8 --push-power -2000 --pv-power-limit 30000 --duration 20
```

Enable holding-register readback (debug):

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 8 --push-power 0 --holding-readback
```

Use a fixed CSV path:

```bash
python solax_qcells_modbus_cli.py --host 192.168.2.50 --unit 1 --mode 8 --push-power 0 --csv-file mode8_run.csv
```

`mode8_run.csv` (filename only) is written to `./csv/mode8_run.csv`.
Explicit paths like `out/mode8_run.csv` or `/tmp/mode8_run.csv` are used as provided.

## Console Output

Console output uses fixed-width columns and repeats the header every 30 cycles.

Columns include:

- `mode`
- `target_w` / `ap_tgt_w` (mode 1)
- `push_w` (mode 4)
- `pv_lim_w` / `push_w` (mode 8)
- `bat_w`, `import_w`, `house_w`, `pv_w`
- `status`

Sign conventions:

- `import_w`: positive = import, negative = export
- `pv_w`: negative = generation, positive = consumption
- `bat_w`: negative = discharge, positive = charge
- `push_w` (mode 4/8): positive = discharge, negative = charge

## CSV Output

One row is written per cycle and flushed immediately.

- mixed schema with mode-1/mode-4/mode-8 fields
- unused mode fields stay empty
- `status` is `ok` or `error`
- `error` contains the exception message for failed cycles

## Parameters

- `--host` (required)
- `--port` (default `502`)
- `--unit` (default `1`)
- `--mode` (`1`, `4`, `8`; default `1`)

Mode 1:

- `--active-power` (default `0`)
- `--formula` (`ha` or `direct`, default `ha`)

Mode 8:

- `--pv-power-limit` (default `30000`)
- `--push-power` (default `0`)
- `--mode8-timeout` (default `0`)

Mode 4:

- `--push-power` (default `0`)
- `--mode4-timeout` (default `0`)

General:

- `--duration` (default `20`)
- `--interval` (default `10`)
- `--repeat-for` (default `0`, infinite)
- `--csv-file` (optional output path; filename-only values go to `./csv`)
- `--disable-on-exit` / `--no-disable-on-exit` (default: disable on exit)
- `--timeout` (default `2.0`)
- `--holding-readback` (optional debug readback)

## Recovery (Manual Disable)

If mode disable on exit fails, you can manually set control-mode registers to `0`:

```python
from pymodbus.client.sync import ModbusTcpClient

client = ModbusTcpClient("192.168.2.50", port=502, timeout=2)
client.connect()
client.write_registers(0x7C, [0], unit=1)
client.write_registers(0xA0, [0], unit=1)
client.close()
```

## Troubleshooting

- `Could not connect ...`: verify host/port/firewall and that Modbus TCP is enabled.
- `Exception Response(... SlaveFailure)`: firmware rejected the command; verify mode/register support.
- inconsistent values: ensure there is only one active writer.
- no PV numbers: check unit id and register mapping for your model.

## Development

Install dev dependencies:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Run lint and tests:

```bash
flake8 solax_qcells_modbus_cli.py tests
pytest
```

## Known Limitations

- no mode 12 support
- no firmware auto-detection
- no built-in lock against multiple concurrent writers

## License

Apache-2.0, see `LICENSE`.

Redistributions should retain attribution and include both `LICENSE` and `NOTICE`.
