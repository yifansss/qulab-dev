"""Curated Rabi digital-gate family; tau_s is the single MW gate duration."""

from __future__ import annotations
from typing import Any, Mapping
from ...models import SequenceFamilySpec, SequenceParameterSpec
from .common import CuratedFamilyProvider, validate_time


class RabiFamilyProvider(CuratedFamilyProvider):
    family_id = "rabi"; version = "2"
    def describe(self):
        p = SequenceParameterSpec
        return SequenceFamilySpec("rabi", self.version, "Rabi", "pycontrol_asg_json", (
            p("laser_init_s", "Laser initialization", "float", "s", 3e-6, 1e-9),
            p("laser_to_mw_s", "Laser to MW delay", "float", "s", 1e-6, 0.0),
            p("tau_s", "MW pulse duration τ", "float", "s", 100e-9, 1e-9),
            p("mw_to_readout_s", "MW to readout delay", "float", "s", 1e-6, 0.0),
            p("readout_s", "Readout window", "float", "s", 2e-6, 1e-9),
            p("trigger_offset_s", "DAQ trigger offset from readout", "float", "s", 0.0, 0.0),
            p("sequence_period_s", "Sequence period", "float", "s", 20e-6, 1e-9, sweepable=False),
        ), supports_preview=True, description="One variable-duration MW gate; readout and trigger are recomputed from τ.")
    def timing(self, x: Mapping[str, Any]):
        init=validate_time("laser_init_s",x["laser_init_s"]); gap1=validate_time("laser_to_mw_s",x["laser_to_mw_s"],allow_zero=True)
        tau=validate_time("tau_s",x["tau_s"]); gap2=validate_time("mw_to_readout_s",x["mw_to_readout_s"],allow_zero=True)
        read=validate_time("readout_s",x["readout_s"]); trig=validate_time("trigger_offset_s",x["trigger_offset_s"],allow_zero=True)
        mw=init+gap1; ro=mw+tau+gap2; trigger=ro+trig; trigger_width=min(read,1e-6)
        return [("laser_channel",0,init,"laser_init"),("mw_gate_channel",mw,tau,"mw_gate"),
                ("readout_gate_channel",ro,read,"readout"),("daq_trigger_channel",trigger,trigger_width,"daq_trigger")], {"mw_start_s":mw,"readout_start_s":ro,"trigger_start_s":trigger}

PROVIDER=RabiFamilyProvider()
def get_provider(): return RabiFamilyProvider()
