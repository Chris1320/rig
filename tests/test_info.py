from rig import info


def test_info() -> None:
    assert info.NAME == "rig"

    assert isinstance(info.VERSION, str)
    assert len(info.VERSION.split(".")) >= 3

    assert isinstance(info.DESCRIPTION, str)
    assert len(info.DESCRIPTION.strip()) != 0
