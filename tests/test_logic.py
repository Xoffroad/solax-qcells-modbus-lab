import pytest

import solax_qcells_modbus_cli as cli


def test_compute_mode1_ap_target_ha() -> None:
    pv_for_calc_w, ap_target_w = cli.compute_mode1_ap_target(
        active_power_w=0,
        pv_power_w=-3500,
        formula="ha",
    )

    assert pv_for_calc_w == 3500
    assert ap_target_w == -3500


def test_compute_mode1_ap_target_direct() -> None:
    pv_for_calc_w, ap_target_w = cli.compute_mode1_ap_target(
        active_power_w=1200,
        pv_power_w=-3500,
        formula="direct",
    )

    assert pv_for_calc_w == 3500
    assert ap_target_w == 1200


def test_compute_mode1_ap_target_rejects_unknown_formula() -> None:
    with pytest.raises(ValueError):
        cli.compute_mode1_ap_target(active_power_w=0, pv_power_w=0, formula="unknown")


def test_disable_remote_modes_writes_mode_registers() -> None:
    writes = []

    class Response:
        @staticmethod
        def isError() -> bool:
            return False

    class Client:
        def write_registers(self, address, values, unit):
            writes.append((address, tuple(values), unit))
            return Response()

    cli.disable_remote_modes(Client(), unit=7)

    assert writes == [
        (cli.MODE1_CONTROL_MODE_REG, (0,), 7),
        (cli.MODE8_CONTROL_MODE_REG, (0,), 7),
    ]
