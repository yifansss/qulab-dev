"""Curated Ramsey family with two digital pi/2 gates; analog phase is intentionally unsupported."""
from __future__ import annotations
from typing import Any, Mapping
from ...models import SequenceFamilySpec, SequenceParameterSpec
from .common import CuratedFamilyProvider, validate_time

class RamseyFamilyProvider(CuratedFamilyProvider):
    family_id="ramsey"; version="1"
    def describe(self):
        p=SequenceParameterSpec
        return SequenceFamilySpec("ramsey",self.version,"Ramsey","pycontrol_asg_json",(
            p("laser_init_s","Laser initialization","float","s",3e-6,1e-9),p("laser_to_mw_s","Laser to MW delay","float","s",1e-6,0.0),
            p("pi2_1_s","First π/2 duration","float","s",50e-9,1e-9),p("free_evolution_s","Free evolution","float","s",1e-6,1e-9),
            p("pi2_2_s","Second π/2 duration","float","s",50e-9,1e-9),p("mw_to_readout_s","MW to readout delay","float","s",1e-6,0.0),
            p("readout_s","Readout window","float","s",2e-6,1e-9),p("trigger_offset_s","DAQ trigger offset","float","s",0.0,0.0),
            p("sequence_period_s","Sequence period","float","s",25e-6,1e-9,sweepable=False),
        ),supports_preview=True,description="Second π/2 starts after the declared free-evolution interval; phase control is not provided by ASG JSON.")
    def timing(self,x:Mapping[str,Any]):
        init=validate_time("laser_init_s",x["laser_init_s"]); lg=validate_time("laser_to_mw_s",x["laser_to_mw_s"],allow_zero=True)
        p1=validate_time("pi2_1_s",x["pi2_1_s"]); free=validate_time("free_evolution_s",x["free_evolution_s"]); p2=validate_time("pi2_2_s",x["pi2_2_s"])
        rg=validate_time("mw_to_readout_s",x["mw_to_readout_s"],allow_zero=True); read=validate_time("readout_s",x["readout_s"]); off=validate_time("trigger_offset_s",x["trigger_offset_s"],allow_zero=True)
        s1=init+lg;s2=s1+p1+free;ro=s2+p2+rg;tr=ro+off
        return [("laser_channel",0,init,"laser_init"),("mw_gate_channel",s1,p1,"pi2_1"),("mw_gate_channel",s2,p2,"pi2_2"),("readout_gate_channel",ro,read,"readout"),("daq_trigger_channel",tr,min(read,1e-6),"daq_trigger")],{"pi2_1_start_s":s1,"free_evolution_s":free,"pi2_2_start_s":s2,"readout_start_s":ro,"trigger_start_s":tr}
PROVIDER=RamseyFamilyProvider()
def get_provider(): return RamseyFamilyProvider()
