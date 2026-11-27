"""Run every loader in turn; one failing loader does not stop the others."""
import traceback

from loaders import load_oslo, load_toulouse, load_weather
from loaders.common import log

failed = []
for module in (load_toulouse, load_oslo, load_weather):
    try:
        module.run()
        if module is load_weather:
            module.run_basin()
    except Exception:  # noqa: BLE001
        failed.append(module.__name__)
        traceback.print_exc()

log("All loaders finished" if not failed else f"Finished with failures: {', '.join(failed)}")
