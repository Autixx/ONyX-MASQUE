from onx.drivers.awg.driver import AWGDriver


def get_driver(name: str):
    if name == "awg":
        return AWGDriver()
    raise ValueError(f"Unsupported driver '{name}'.")
