import solax_qcells_modbus_cli as cli


class Response:
    @staticmethod
    def isError() -> bool:
        return False


class RecordingClient:
    def __init__(self):
        self.calls = []

    def write_registers(self, address, payload, unit):
        self.calls.append((address, list(payload), unit))
        return Response()


def test_write_mode1_command_payload_size() -> None:
    client = RecordingClient()

    cli.write_mode1_command(client, unit=1, ap_target_w=-2500, duration_s=20)

    address, payload, unit = client.calls[0]
    assert address == cli.MODE1_CONTROL_MODE_REG
    assert len(payload) == cli.MODE1_BLOCK_REG_COUNT
    assert unit == 1


def test_write_mode8_command_payload_size() -> None:
    client = RecordingClient()

    cli.write_mode8_command(
        client,
        unit=1,
        pv_power_limit_w=30000,
        push_power_w=0,
        duration_s=20,
        timeout_s=0,
    )

    address, payload, unit = client.calls[0]
    assert address == cli.MODE8_CONTROL_MODE_REG
    assert len(payload) == cli.MODE8_BLOCK_REG_COUNT
    assert unit == 1


def test_write_mode4_command_payload_size() -> None:
    client = RecordingClient()

    cli.write_mode4_command(client, unit=1, push_power_w=1200, timeout_s=0)

    address, payload, unit = client.calls[0]
    assert address == cli.MODE1_CONTROL_MODE_REG
    assert len(payload) == cli.MODE4_BLOCK_REG_COUNT
    assert unit == 1
