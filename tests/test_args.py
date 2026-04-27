import pytest

import qcells_mode1_cli as cli


def test_parse_args_defaults() -> None:
    args = cli.parse_args(["--host", "192.168.2.50"])

    assert args.host == "192.168.2.50"
    assert args.port == 502
    assert args.unit == 1
    assert args.mode == 1
    assert args.formula == "ha"
    assert args.duration == 20
    assert args.interval == 10.0
    assert args.repeat_for == 0.0
    assert args.disable_on_exit is True


def test_parse_args_rejects_active_power_above_int32() -> None:
    with pytest.raises(SystemExit):
        cli.parse_args([
            "--host",
            "192.168.2.50",
            "--active-power",
            str(cli.INT32_MAX + 1),
        ])


def test_parse_args_rejects_non_positive_interval() -> None:
    with pytest.raises(SystemExit):
        cli.parse_args(["--host", "192.168.2.50", "--interval", "0"])
