"""Base entities and device registry wiring.

Device layout in Home Assistant:

    AirTouch controller (system name)       touch pad temperature
      +-- AC unit (one per AC, max 2)       climate, error
      +-- Zone (one per zone/group)         switch, damper, zone temperature...
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import AirTouchCoordinator
from .protocol import AcUnit, Model, Zone

MODEL_NAMES = {Model.AIRTOUCH2: "AirTouch 2", Model.AIRTOUCH3: "AirTouch 3"}


class AirTouchEntity(CoordinatorEntity[AirTouchCoordinator]):
    """An entity that belongs to the AirTouch controller itself."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirTouchCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.base_id}_{key}"
        state = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.base_id)},
            manufacturer=MANUFACTURER,
            model=MODEL_NAMES[state.model],
            name=state.name,
            serial_number=state.system_id,
        )


class AirTouchAcEntity(CoordinatorEntity[AirTouchCoordinator]):
    """An entity that belongs to one AC unit."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirTouchCoordinator, index: int, key: str) -> None:
        super().__init__(coordinator)
        self.ac_index = index
        unit = coordinator.data.ac(index)
        device_id = f"{coordinator.base_id}_ac_{index}"
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model="Air conditioner",
            name=unit.name,
            via_device=(DOMAIN, coordinator.base_id),
        )

    @property
    def unit(self) -> AcUnit:
        """The latest state of this AC."""
        return self.coordinator.data.ac(self.ac_index)

    @property
    def available(self) -> bool:
        """Unavailable if the controller stops reporting this AC."""
        return super().available and any(
            u.index == self.ac_index for u in self.coordinator.data.ac_units
        )


class AirTouchZoneEntity(CoordinatorEntity[AirTouchCoordinator]):
    """An entity that belongs to one zone."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AirTouchCoordinator, index: int, key: str) -> None:
        super().__init__(coordinator)
        self.zone_index = index
        zone = coordinator.data.zone(index)
        device_id = f"{coordinator.base_id}_zone_{index}"
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model="Zone",
            name=zone.name,
            suggested_area=zone.name,
            via_device=(DOMAIN, coordinator.base_id),
        )

    @property
    def zone(self) -> Zone:
        """The latest state of this zone."""
        return self.coordinator.data.zone(self.zone_index)

    @property
    def available(self) -> bool:
        """Unavailable if the controller stops reporting this zone."""
        return super().available and self.zone_index < len(self.coordinator.data.zones)
