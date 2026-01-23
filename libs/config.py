import configparser
import sys


class Config:
    _config_file = "config.ini"
    _config = None

    @staticmethod
    def __init__():
        if Config._config is not None:
            return
        print("Loading configuration...")
        Config._config = configparser.ConfigParser()
        try:
            Config._config.read(Config._config_file)
        except configparser.Error as e:
            print(f"Error reading configuration file: {e}")
            sys.exit(2)

        if "KEYBOARD_USB_HID" in Config._config:
            keyboard = Config._config["KEYBOARD_USB_HID"]
            Config.usage_page = int(keyboard.get("usage_page", "0xFF60"), 16)
            Config.usage = int(keyboard.get("usage", "0x61"), 16)

        if "KEYBOARD_BLE_HID" in Config._config:
            keyboard = Config._config["KEYBOARD_BLE_HID"]
            Config.vendor_id = int(keyboard.get("vendor_id", "0xFEED"), 16)
            Config.product_id = int(keyboard.get("product_id", "0x6000"), 16)

        if (
            "KEYBOARD_USB_HID" not in Config._config
            and "KEYBOARD_BLE_HID" not in Config._config
        ):
            print(
                f"\n\n\nNeither KEYBOARD_BLE_HID or KEYBOARD_USB_HID section found in config file: {Config._config_file}\n\n\n"
            )
            sys.exit(2)

        if "LAYER_IMAGES" in Config._config:
            values = Config._config["LAYER_IMAGES"].values()
            Config.layers = [v for v in values]
        else:
            print(
                f"LAYER_IMAGES section not found in config file: {Config._config_file}"
            )
            exit(2)
