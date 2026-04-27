from pathlib import Path

import solax_qcells_modbus_cli as cli


def test_resolve_csv_path_default_uses_csv_folder() -> None:
    path = cli.resolve_csv_path(None)

    assert path.parent == Path.cwd() / cli.CSV_OUTPUT_DIR_NAME
    assert path.name.startswith("qcells_mode1_")
    assert path.suffix == ".csv"


def test_resolve_csv_path_filename_only_goes_to_csv_folder() -> None:
    path = cli.resolve_csv_path("run.csv")

    assert path == Path.cwd() / cli.CSV_OUTPUT_DIR_NAME / "run.csv"


def test_resolve_csv_path_explicit_relative_path_is_kept() -> None:
    path = cli.resolve_csv_path("out/run.csv")

    assert path == Path("out/run.csv")
