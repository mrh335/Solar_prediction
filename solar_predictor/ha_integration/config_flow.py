"""Config flow for Solar Predictor integration."""

from __future__ import annotations
import os
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_YAML_PATH, CONF_NAME

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default="Solar Predictor"): str,
    vol.Required(CONF_YAML_PATH): str,
})


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect / load config."""
    path = data[CONF_YAML_PATH]
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    import yaml
    with open(path) as f:
        cfg = yaml.safe_load(f)

    required_keys = ["location", "array", "battery", "inverter"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        raise ValueError(f"Config missing required sections: {', '.join(missing)}")

    return {"title": data.get(CONF_NAME, "Solar Predictor")}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solar Predictor."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except FileNotFoundError:
                errors["base"] = "file_not_found"
            except ValueError:
                errors["base"] = "invalid_config"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "example_path": "/config/solar_predictor/config.yaml"
            },
        )
