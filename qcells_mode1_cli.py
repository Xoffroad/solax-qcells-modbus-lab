#!/usr/bin/env python3
import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from pymodbus.client.sync import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder


# Solax/QCells Mode 1 Remote Control Register map
MODE1_CONTROL_MODE_REG = 0x7C
MODE1_SET_TYPE_REG = 0x7D
MODE1_ACTIVE_POWER_REG = 0x7E
MODE1_REACTIVE_POWER_REG = 0x80
MODE1_DURATION_REG = 0x82
MODE1_TARGET_SOC_REG = 0x83
MODE1_TARGET_ENERGY_REG = 0x84
MODE1_TARGET_POWER_REG = 0x86
MODE1_TIMEOUT_REG = 0x88

# Solax/QCells Mode 8 Remote Control Register map
MODE8_CONTROL_MODE_REG = 0xA0
MODE8_SET_TYPE_REG = 0xA1
MODE8_PV_POWER_LIMIT_REG = 0xA2
MODE8_PUSH_POWER_REG = 0xA4
MODE8_DURATION_REG = 0xA6
MODE8_TIMEOUT_REG = 0xA7

# Solax/QCells Mode 4 register
MODE4_PUSH_POWER_REG = 0x89

MODE_DISABLED = 0
MODE_1_ENABLED_POWER_CONTROL = 1
MODE_4_PUSH_POWER = 4
MODE_8_INDIVIDUAL_DURATION = 8
SET_TYPE_SET = 1
TIMEOUT_DISABLED = 0

MODE1_BLOCK_REG_COUNT = 13
MODE8_BLOCK_REG_COUNT = 8
MODE4_BLOCK_REG_COUNT = 15

INT32_MIN = -2147483648
INT32_MAX = 2147483647
UINT16_MAX = 65535
UINT32_MAX = 4294967295

# QCells openWB readback registers
BAT_POWER_REG = 0x0016
COUNTER_POWER_REG = 0x0046
PV_CURRENT_STRING_1_REG = 0x0003


@dataclass
class ReadbackValues:
    bat_power_w: int
    import_power_w: int
    house_load_w: int
    pv_power_w: int


@dataclass
class Mode1HoldingState:
    mode: int
    set_type: int
    active_power_w: int
    reactive_power_var: int
    duration_s: int
    target_soc_pct: int
    target_energy_wh: int
    target_power_w: int
    timeout_s: int


@dataclass
class Mode8HoldingState:
    control_mode: int
    set_type: int
    pv_power_limit_w: int
    push_power_w: int
    duration_s: int
    timeout_s: int


@dataclass
class Mode4HoldingState:
    mode: int
    set_type: int
    timeout_s: int
    push_power_w: int


CSV_HEADERS = [
    "timestamp",
    "cycle",
    "mode_cmd",
    "target_active_power_w",
    "pv_for_calc_w",
    "ap_target_w",
    "mode8_pv_power_limit_w",
    "mode8_push_power_w",
    "mode8_timeout_s",
    "mode4_push_power_w",
    "mode4_timeout_s",
    "bat_power_w",
    "import_power_w",
    "house_load_w",
    "pv_power_w",
    "reg_mode",
    "reg_set_type",
    "reg_active_power_w",
    "reg_reactive_power_var",
    "reg_duration_s",
    "reg_target_soc_pct",
    "reg_target_energy_wh",
    "reg_target_power_w",
    "reg_timeout_s",
    "reg_mode8_control_mode",
    "reg_mode8_set_type",
    "reg_mode8_pv_power_limit_w",
    "reg_mode8_push_power_w",
    "reg_mode8_duration_s",
    "reg_mode8_timeout_s",
    "reg_mode4_push_power_w",
    "status",
    "error",
]

CONSOLE_HEADER_EVERY_CYCLES = 30


def _format_console_row(
    timestamp: str,
    cycle: str,
    mode: str,
    target_active_power_w: str,
    ap_target_w: str,
    mode8_pv_power_limit_w: str,
    mode8_push_power_w: str,
    bat_power_w: str,
    import_power_w: str,
    house_load_w: str,
    pv_power_w: str,
    status: str,
) -> str:
    return (
        f"{timestamp:<19} {cycle:>6} {mode:>4} {target_active_power_w:>9} {ap_target_w:>10} "
        f"{mode8_pv_power_limit_w:>10} {mode8_push_power_w:>8} {bat_power_w:>9} "
        f"{import_power_w:>11} {house_load_w:>10} {pv_power_w:>9} {status:<6}"
    )


def _print_console_header() -> None:
    print(
        _format_console_row(
            "timestamp",
            "cycle",
            "mode",
            "target_w",
            "ap_tgt_w",
            "pv_lim_w",
            "push_w",
            "bat_w",
            "import_w",
            "house_w",
            "pv_w",
            "status",
        )
    )


def _default_csv_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.cwd() / f"qcells_mode1_{stamp}.csv"


def _read_input_registers(client: ModbusTcpClient, address: int, count: int, unit: int):
    response = client.read_input_registers(address, count, unit=unit)
    if response.isError():
        raise RuntimeError(f"Modbus read error at 0x{address:04X}: {response}")
    return response.registers


def _read_holding_registers(client: ModbusTcpClient, address: int, count: int, unit: int):
    response = client.read_holding_registers(address, count, unit=unit)
    if response.isError():
        raise RuntimeError(f"Modbus read error at 0x{address:04X}: {response}")
    return response.registers


def _write_u16(client: ModbusTcpClient, address: int, value: int, unit: int) -> None:
    response = client.write_registers(address, [value], unit=unit)
    if response.isError():
        raise RuntimeError(f"Modbus write error at 0x{address:04X}: {response}")


def _decode_int16(registers) -> int:
    decoder = BinaryPayloadDecoder.fromRegisters(registers, byteorder=Endian.Big, wordorder=Endian.Big)
    return int(decoder.decode_16bit_int())


def _decode_uint16(registers) -> int:
    decoder = BinaryPayloadDecoder.fromRegisters(registers, byteorder=Endian.Big, wordorder=Endian.Big)
    return int(decoder.decode_16bit_uint())


def _decode_int32_little_word(registers) -> int:
    decoder = BinaryPayloadDecoder.fromRegisters(registers, byteorder=Endian.Big, wordorder=Endian.Little)
    return int(decoder.decode_32bit_int())


def _decode_uint32_little_word(registers) -> int:
    decoder = BinaryPayloadDecoder.fromRegisters(registers, byteorder=Endian.Big, wordorder=Endian.Little)
    return int(decoder.decode_32bit_uint())


def read_mode1_holding_state(client: ModbusTcpClient, unit: int) -> Mode1HoldingState:
    regs = _read_holding_registers(client, MODE1_CONTROL_MODE_REG, MODE1_BLOCK_REG_COUNT, unit)
    return Mode1HoldingState(
        mode=_decode_uint16(regs[0:1]),
        set_type=_decode_uint16(regs[1:2]),
        active_power_w=_decode_int32_little_word(regs[2:4]),
        reactive_power_var=_decode_int32_little_word(regs[4:6]),
        duration_s=_decode_uint16(regs[6:7]),
        target_soc_pct=_decode_uint16(regs[7:8]),
        target_energy_wh=_decode_uint32_little_word(regs[8:10]),
        target_power_w=_decode_int32_little_word(regs[10:12]),
        timeout_s=_decode_uint16(regs[12:13]),
    )


def read_mode8_holding_state(client: ModbusTcpClient, unit: int) -> Mode8HoldingState:
    regs = _read_holding_registers(client, MODE8_CONTROL_MODE_REG, MODE8_BLOCK_REG_COUNT, unit)
    return Mode8HoldingState(
        control_mode=_decode_uint16(regs[0:1]),
        set_type=_decode_uint16(regs[1:2]),
        pv_power_limit_w=_decode_uint32_little_word(regs[2:4]),
        push_power_w=_decode_int32_little_word(regs[4:6]),
        duration_s=_decode_uint16(regs[6:7]),
        timeout_s=_decode_uint16(regs[7:8]),
    )


def read_mode4_holding_state(client: ModbusTcpClient, unit: int) -> Mode4HoldingState:
    regs = _read_holding_registers(client, MODE1_CONTROL_MODE_REG, MODE4_BLOCK_REG_COUNT, unit)
    return Mode4HoldingState(
        mode=_decode_uint16(regs[0:1]),
        set_type=_decode_uint16(regs[1:2]),
        timeout_s=_decode_uint16(regs[12:13]),
        push_power_w=_decode_int32_little_word(regs[13:15]),
    )


def write_mode1_command(client: ModbusTcpClient, unit: int, ap_target_w: int, duration_s: int) -> None:
    builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
    builder.add_16bit_uint(MODE_1_ENABLED_POWER_CONTROL)  # 0x7C
    builder.add_16bit_uint(SET_TYPE_SET)  # 0x7D
    builder.add_32bit_int(ap_target_w)  # 0x7E/0x7F
    builder.add_32bit_int(0)  # 0x80/0x81 reactive power
    builder.add_16bit_uint(duration_s)  # 0x82
    builder.add_16bit_uint(0)  # 0x83 target SoC
    builder.add_32bit_uint(0)  # 0x84/0x85 target energy
    builder.add_32bit_int(0)  # 0x86/0x87 target power
    builder.add_16bit_uint(TIMEOUT_DISABLED)  # 0x88
    payload = builder.to_registers()
    if len(payload) != MODE1_BLOCK_REG_COUNT:
        raise RuntimeError(
            f"Unexpected mode1 payload size {len(payload)}, expected {MODE1_BLOCK_REG_COUNT}"
        )
    response = client.write_registers(MODE1_CONTROL_MODE_REG, payload, unit=unit)
    if response.isError():
        raise RuntimeError(f"Modbus write error at 0x{MODE1_CONTROL_MODE_REG:04X}: {response}")


def write_mode8_command(
    client: ModbusTcpClient,
    unit: int,
    pv_power_limit_w: int,
    push_power_w: int,
    duration_s: int,
    timeout_s: int,
) -> None:
    builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
    builder.add_16bit_uint(MODE_8_INDIVIDUAL_DURATION)  # 0xA0
    builder.add_16bit_uint(SET_TYPE_SET)  # 0xA1
    builder.add_32bit_uint(pv_power_limit_w)  # 0xA2/0xA3
    builder.add_32bit_int(push_power_w)  # 0xA4/0xA5
    builder.add_16bit_uint(duration_s)  # 0xA6
    builder.add_16bit_uint(timeout_s)  # 0xA7
    payload = builder.to_registers()
    if len(payload) != MODE8_BLOCK_REG_COUNT:
        raise RuntimeError(
            f"Unexpected mode8 payload size {len(payload)}, expected {MODE8_BLOCK_REG_COUNT}"
        )
    response = client.write_registers(MODE8_CONTROL_MODE_REG, payload, unit=unit)
    if response.isError():
        raise RuntimeError(f"Modbus write error at 0x{MODE8_CONTROL_MODE_REG:04X}: {response}")


def write_mode4_command(client: ModbusTcpClient, unit: int, push_power_w: int, timeout_s: int) -> None:
    builder = BinaryPayloadBuilder(byteorder=Endian.Big, wordorder=Endian.Little)
    builder.add_16bit_uint(MODE_4_PUSH_POWER)  # 0x7C
    builder.add_16bit_uint(SET_TYPE_SET)  # 0x7D
    builder.add_32bit_int(0)  # 0x7E/0x7F active power (dummy)
    builder.add_32bit_int(0)  # 0x80/0x81 reactive power (dummy)
    builder.add_16bit_uint(0)  # 0x82 duration (dummy)
    builder.add_16bit_uint(0)  # 0x83 target SoC (dummy)
    builder.add_32bit_uint(0)  # 0x84/0x85 target energy (dummy)
    builder.add_32bit_int(0)  # 0x86/0x87 target power (dummy)
    builder.add_16bit_uint(timeout_s)  # 0x88 timeout
    builder.add_32bit_int(push_power_w)  # 0x89/0x8A push power mode 4
    payload = builder.to_registers()
    if len(payload) != MODE4_BLOCK_REG_COUNT:
        raise RuntimeError(
            f"Unexpected mode4 payload size {len(payload)}, expected {MODE4_BLOCK_REG_COUNT}"
        )
    response = client.write_registers(MODE1_CONTROL_MODE_REG, payload, unit=unit)
    if response.isError():
        raise RuntimeError(f"Modbus write error at 0x{MODE1_CONTROL_MODE_REG:04X}: {response}")


def disable_remote_modes(client: ModbusTcpClient, unit: int) -> None:
    errors = []
    for address in (MODE1_CONTROL_MODE_REG, MODE8_CONTROL_MODE_REG):
        try:
            _write_u16(client, address, MODE_DISABLED, unit)
        except Exception as exc:  # pragma: no cover - defensive on hardware communication
            errors.append(f"0x{address:04X}: {exc}")
    if errors:
        raise RuntimeError("; ".join(errors))


def readback_values(client: ModbusTcpClient, unit: int) -> ReadbackValues:
    bat_power_w = _decode_int16(_read_input_registers(client, BAT_POWER_REG, 1, unit))

    counter_power_raw = _decode_int32_little_word(_read_input_registers(client, COUNTER_POWER_REG, 2, unit))
    import_power_w = counter_power_raw * -1

    pv_registers = _read_input_registers(client, PV_CURRENT_STRING_1_REG, 4, unit)
    current_string_1 = _decode_int16([pv_registers[0]]) / 10.0
    current_string_2 = _decode_int16([pv_registers[1]]) / 10.0
    voltage_string_1 = _decode_uint16([pv_registers[2]]) / 10.0
    voltage_string_2 = _decode_uint16([pv_registers[3]]) / 10.0
    pv_power_w = int(round((current_string_1 * voltage_string_1 + current_string_2 * voltage_string_2) * -1))

    house_load_w = int(round(import_power_w - pv_power_w - bat_power_w))

    return ReadbackValues(
        bat_power_w=bat_power_w,
        import_power_w=import_power_w,
        house_load_w=house_load_w,
        pv_power_w=pv_power_w,
    )


def compute_mode1_ap_target(active_power_w: int, pv_power_w: int, formula: str) -> tuple[int, int]:
    pv_for_calc_w = max(0, pv_power_w * -1)
    if formula == "ha":
        return pv_for_calc_w, active_power_w - pv_for_calc_w
    if formula == "direct":
        return pv_for_calc_w, active_power_w
    raise ValueError(f"Unsupported formula: {formula}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write QCells/SolaX Modbus power control commands (mode 1/4/8) in a cyclic loop."
    )
    parser.add_argument("--host", required=True, help="QCells/SolaX Modbus TCP host")
    parser.add_argument("--port", type=int, default=502, help="Modbus TCP port (default: 502)")
    parser.add_argument("--unit", type=int, default=1, help="Modbus unit/slave id (default: 1)")
    parser.add_argument("--mode", type=int, choices=[1, 4, 8], default=1, help="Power control mode (default: 1)")

    parser.add_argument("--active-power", type=int, default=0, help="Mode 1 target active power in W (default: 0)")
    parser.add_argument(
        "--formula",
        choices=["ha", "direct"],
        default="ha",
        help="Mode 1 formula: ha => active_power - pv_generation, direct => active_power",
    )

    parser.add_argument(
        "--pv-power-limit",
        type=int,
        default=30000,
        help="Mode 8 PV power limit in W for 0xA2 (default: 30000)",
    )
    parser.add_argument(
        "--push-power",
        type=int,
        default=0,
        help="Mode 4/8 push power in W, +discharge/-charge (default: 0)",
    )
    parser.add_argument(
        "--mode4-timeout",
        type=int,
        default=0,
        help="Mode 4 timeout in seconds for 0x88 (default: 0)",
    )
    parser.add_argument(
        "--mode8-timeout",
        type=int,
        default=0,
        help="Mode 8 timeout in seconds for 0xA7 (default: 0)",
    )

    parser.add_argument("--duration", type=int, default=20, help="Duration in seconds (default: 20)")
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Cyclic write/read interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--repeat-for",
        type=float,
        default=0.0,
        help="Total runtime in seconds (default: 0 = run until Ctrl+C)",
    )
    parser.add_argument(
        "--disable-on-exit",
        dest="disable_on_exit",
        action="store_true",
        help="Disable remote control mode(s) on exit (default)",
    )
    parser.add_argument(
        "--no-disable-on-exit",
        dest="disable_on_exit",
        action="store_false",
        help="Keep remote control mode active on exit",
    )
    parser.add_argument(
        "--csv-file",
        default=None,
        help="CSV output file path (default: auto-generated in current directory)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Modbus TCP socket timeout in seconds (default: 2)",
    )
    parser.add_argument(
        "--holding-readback",
        action="store_true",
        help="Enable holding register readback each cycle (mode1: 0x7C..0x88, mode4: 0x7C..0x8A, mode8: 0xA0..0xA7)",
    )

    parser.set_defaults(disable_on_exit=True)
    args = parser.parse_args(argv)

    if args.interval <= 0:
        parser.error("--interval must be > 0")
    if args.repeat_for < 0:
        parser.error("--repeat-for must be >= 0")
    if args.duration < 0 or args.duration > UINT16_MAX:
        parser.error("--duration must be between 0 and 65535")
    if args.mode4_timeout < 0 or args.mode4_timeout > UINT16_MAX:
        parser.error("--mode4-timeout must be between 0 and 65535")
    if args.mode8_timeout < 0 or args.mode8_timeout > UINT16_MAX:
        parser.error("--mode8-timeout must be between 0 and 65535")
    if args.pv_power_limit < 0 or args.pv_power_limit > UINT32_MAX:
        parser.error("--pv-power-limit must be between 0 and 4294967295")
    if args.active_power < INT32_MIN or args.active_power > INT32_MAX:
        parser.error("--active-power must be between -2147483648 and 2147483647")
    if args.push_power < INT32_MIN or args.push_power > INT32_MAX:
        parser.error("--push-power must be between -2147483648 and 2147483647")

    return args


def _new_csv_row() -> dict[str, Any]:
    return {key: "" for key in CSV_HEADERS}


def main() -> int:
    args = parse_args()

    csv_path = Path(args.csv_file) if args.csv_file else _default_csv_path()
    csv_file = csv_path.open("w", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(csv_file, fieldnames=CSV_HEADERS)
    csv_writer.writeheader()
    csv_file.flush()

    client = ModbusTcpClient(args.host, port=args.port, timeout=args.timeout)
    if not client.connect():
        print(f"Could not connect to Modbus TCP device at {args.host}:{args.port}", file=sys.stderr)
        csv_file.close()
        return 2

    print(
        f"Connected. mode={args.mode}, duration={args.duration}s, interval={args.interval}s, "
        f"repeat_for={args.repeat_for}s"
    )
    if args.mode == 1:
        print(
            f"Mode 1 config: formula={args.formula}, target_active_power={args.active_power}W, "
            f"timeout={TIMEOUT_DISABLED}s"
        )
    elif args.mode == 4:
        print(
            f"Mode 4 config: push_power={args.push_power}W, timeout={args.mode4_timeout}s"
        )
    else:
        print(
            f"Mode 8 config: pv_power_limit={args.pv_power_limit}W, push_power={args.push_power}W, "
            f"timeout={args.mode8_timeout}s"
        )
    print(
        "Sign convention: import_power +import/-export, pv_power -generation/+consumption, "
        "bat_power -discharge/+charge, mode4/8 push +discharge/-charge"
    )
    print(f"CSV logging enabled: {csv_path}")
    if args.holding_readback:
        if args.mode == 1:
            print("Holding readback enabled: 0x7C..0x88")
        elif args.mode == 4:
            print("Holding readback enabled: 0x7C..0x8A")
        else:
            print("Holding readback enabled: 0xA0..0xA7")
    else:
        print("Holding readback disabled (default)")

    _print_console_header()

    start_time = time.monotonic()
    cycle = 0

    try:
        while True:
            cycle_start = time.monotonic()
            cycle += 1

            if cycle > 1 and (cycle - 1) % CONSOLE_HEADER_EVERY_CYCLES == 0:
                _print_console_header()

            row = _new_csv_row()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row["timestamp"] = timestamp
            row["cycle"] = cycle
            row["mode_cmd"] = args.mode

            target_display = "-"
            ap_target_display = "-"
            pv_limit_display = "-"
            push_display = "-"

            try:
                pre_values = readback_values(client, args.unit)

                if args.mode == 1:
                    pv_for_calc_w, ap_target_w = compute_mode1_ap_target(
                        args.active_power,
                        pre_values.pv_power_w,
                        args.formula,
                    )

                    write_mode1_command(client, args.unit, ap_target_w, args.duration)

                    row["target_active_power_w"] = args.active_power
                    row["pv_for_calc_w"] = pv_for_calc_w
                    row["ap_target_w"] = ap_target_w

                    target_display = str(args.active_power)
                    ap_target_display = str(ap_target_w)

                    if args.holding_readback:
                        state = read_mode1_holding_state(client, args.unit)
                        row["reg_mode"] = state.mode
                        row["reg_set_type"] = state.set_type
                        row["reg_active_power_w"] = state.active_power_w
                        row["reg_reactive_power_var"] = state.reactive_power_var
                        row["reg_duration_s"] = state.duration_s
                        row["reg_target_soc_pct"] = state.target_soc_pct
                        row["reg_target_energy_wh"] = state.target_energy_wh
                        row["reg_target_power_w"] = state.target_power_w
                        row["reg_timeout_s"] = state.timeout_s
                elif args.mode == 4:
                    write_mode4_command(client, args.unit, args.push_power, args.mode4_timeout)

                    row["mode4_push_power_w"] = args.push_power
                    row["mode4_timeout_s"] = args.mode4_timeout

                    push_display = str(args.push_power)

                    if args.holding_readback:
                        state = read_mode4_holding_state(client, args.unit)
                        row["reg_mode"] = state.mode
                        row["reg_set_type"] = state.set_type
                        row["reg_timeout_s"] = state.timeout_s
                        row["reg_mode4_push_power_w"] = state.push_power_w
                else:
                    write_mode8_command(
                        client,
                        args.unit,
                        args.pv_power_limit,
                        args.push_power,
                        args.duration,
                        args.mode8_timeout,
                    )

                    row["mode8_pv_power_limit_w"] = args.pv_power_limit
                    row["mode8_push_power_w"] = args.push_power
                    row["mode8_timeout_s"] = args.mode8_timeout

                    pv_limit_display = str(args.pv_power_limit)
                    push_display = str(args.push_power)

                    if args.holding_readback:
                        state = read_mode8_holding_state(client, args.unit)
                        row["reg_mode"] = state.control_mode
                        row["reg_set_type"] = state.set_type
                        row["reg_duration_s"] = state.duration_s
                        row["reg_timeout_s"] = state.timeout_s
                        row["reg_mode8_control_mode"] = state.control_mode
                        row["reg_mode8_set_type"] = state.set_type
                        row["reg_mode8_pv_power_limit_w"] = state.pv_power_limit_w
                        row["reg_mode8_push_power_w"] = state.push_power_w
                        row["reg_mode8_duration_s"] = state.duration_s
                        row["reg_mode8_timeout_s"] = state.timeout_s

                post_values = readback_values(client, args.unit)
                row["bat_power_w"] = post_values.bat_power_w
                row["import_power_w"] = post_values.import_power_w
                row["house_load_w"] = post_values.house_load_w
                row["pv_power_w"] = post_values.pv_power_w
                row["status"] = "ok"
                row["error"] = ""
                csv_writer.writerow(row)
                csv_file.flush()

                print(
                    _format_console_row(
                        timestamp,
                        str(cycle),
                        str(args.mode),
                        target_display,
                        ap_target_display,
                        pv_limit_display,
                        push_display,
                        str(post_values.bat_power_w),
                        str(post_values.import_power_w),
                        str(post_values.house_load_w),
                        str(post_values.pv_power_w),
                        "ok",
                    )
                )

            except Exception as exc:
                row["status"] = "error"
                row["error"] = str(exc)
                csv_writer.writerow(row)
                csv_file.flush()

                print(
                    _format_console_row(
                        timestamp,
                        str(cycle),
                        str(args.mode),
                        target_display,
                        ap_target_display,
                        pv_limit_display,
                        push_display,
                        "-",
                        "-",
                        "-",
                        "-",
                        "error",
                    )
                    + f" {exc}",
                    file=sys.stderr,
                )

            if args.repeat_for > 0 and (time.monotonic() - start_time) >= args.repeat_for:
                print("Finished repeat window.")
                break

            sleep_time = max(0.0, cycle_start + args.interval - time.monotonic())
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("Stopped by user (Ctrl+C).")
    finally:
        if args.disable_on_exit:
            try:
                disable_remote_modes(client, args.unit)
                print("Remote control modes disabled (0x7C=0, 0xA0=0).")
            except Exception as exc:
                print(f"Failed to disable remote control modes: {exc}", file=sys.stderr)
        client.close()
        csv_file.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
