##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2019, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
Condenser model for distillation
"""

__author__ = "Jaffer Ghouse"

import logging
from enum import Enum

# Import Pyomo libraries
from pyomo.common.config import ConfigBlock, ConfigValue, In
from pyomo.network import Port
from pyomo.environ import Reference, Expression, Var

# Import IDAES cores
from idaes.core import (ControlVolume0DBlock,
                        declare_process_block_class,
                        EnergyBalanceType,
                        MomentumBalanceType,
                        MaterialBalanceType,
                        UnitModelBlockData,
                        useDefault)
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.misc import add_object_reference

_log = logging.getLogger(__name__)


class CondenserType(Enum):
    totalCondenser = 0
    partialCondenser = 1


@declare_process_block_class("Condenser")
class CondenserData(UnitModelBlockData):
    """
    Condenser unit for distillation model.
    Unit model to condense (total/partial) the vapor from the top tray of
    the distillation column.
    """
    CONFIG = UnitModelBlockData.CONFIG()
    CONFIG.declare("condenser_type", ConfigValue(
        default=CondenserType.totalCondenser,
        domain=In(CondenserType),
        description="Type of condenser flag",
        doc="""Indicates what type of condenser should be constructed,
**default** - CondenserType.totalCondenser.
**Valid values:** {
**CondenserType.totalCondenser** - Incoming vapor from top tray is condensed
to all liquid,
**CondenserType.partialCondenser** - Incoming vapor from top tray is
partially condensed to a vapor and liquid stream.}"""))
    CONFIG.declare("material_balance_type", ConfigValue(
        default=MaterialBalanceType.componentPhase,
        domain=In(MaterialBalanceType),
        description="Material balance construction flag",
        doc="""Indicates what type of mass balance should be constructed,
**default** - MaterialBalanceType.componentPhase.
**Valid values:** {
**MaterialBalanceType.none** - exclude material balances,
**MaterialBalanceType.componentPhase** - use phase component balances,
**MaterialBalanceType.componentTotal** - use total component balances,
**MaterialBalanceType.elementTotal** - use total element balances,
**MaterialBalanceType.total** - use total material balance.}"""))
    CONFIG.declare("energy_balance_type", ConfigValue(
        default=EnergyBalanceType.enthalpyTotal,
        domain=In(EnergyBalanceType),
        description="Energy balance construction flag",
        doc="""Indicates what type of energy balance should be constructed,
**default** - EnergyBalanceType.enthalpyTotal.
**Valid values:** {
**EnergyBalanceType.none** - exclude energy balances,
**EnergyBalanceType.enthalpyTotal** - single enthalpy balance for material,
**EnergyBalanceType.enthalpyPhase** - enthalpy balances for each phase,
**EnergyBalanceType.energyTotal** - single energy balance for material,
**EnergyBalanceType.energyPhase** - energy balances for each phase.}"""))
    CONFIG.declare("momentum_balance_type", ConfigValue(
        default=MomentumBalanceType.pressureTotal,
        domain=In(MomentumBalanceType),
        description="Momentum balance construction flag",
        doc="""Indicates what type of momentum balance should be constructed,
**default** - MomentumBalanceType.pressureTotal.
**Valid values:** {
**MomentumBalanceType.none** - exclude momentum balances,
**MomentumBalanceType.pressureTotal** - single pressure balance for material,
**MomentumBalanceType.pressurePhase** - pressure balances for each phase,
**MomentumBalanceType.momentumTotal** - single momentum balance for material,
**MomentumBalanceType.momentumPhase** - momentum balances for each phase.}"""))
    CONFIG.declare("has_pressure_change", ConfigValue(
        default=True,
        domain=In([True, False]),
        description="Pressure change term construction flag",
        doc="""Indicates whether terms for pressure change should be
constructed,
**default** - False.
**Valid values:** {
**True** - include pressure change terms,
**False** - exclude pressure change terms.}"""))
    CONFIG.declare("property_package", ConfigValue(
        default=useDefault,
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="""Property parameter object used to define property calculations,
**default** - useDefault.
**Valid values:** {
**useDefault** - use default package from parent model or flowsheet,
**PropertyParameterObject** - a PropertyParameterBlock object.}"""))
    CONFIG.declare("property_package_args", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="""A ConfigBlock with arguments to be passed to a property block(s)
and used when constructing these,
**default** - None.
**Valid values:** {
see property package for documentation.}"""))

    def build(self):
        """Build the model.

        Args:
            None
        Returns:
            None
        """
        # Call UnitModel.build to setup dynamics
        super(CondenserData, self).build()

        # Add Control Volume for the condenser
        self.control_volume = ControlVolume0DBlock(default={
            "dynamic": self.config.dynamic,
            "has_holdup": self.config.has_holdup,
            "property_package": self.config.property_package,
            "property_package_args": self.config.property_package_args})

        self.control_volume.add_state_blocks(
            has_phase_equilibrium=True)

        self.control_volume.add_material_balances(
            balance_type=self.config.material_balance_type,
            has_phase_equilibrium=True)

        self.control_volume.add_energy_balances(
            balance_type=self.config.energy_balance_type,
            has_heat_transfer=True)

        self.control_volume.add_momentum_balances(
            balance_type=self.config.momentum_balance_type,
            has_pressure_change=self.config.has_pressure_change)

        self._add_condenser_ports()

    def _add_condenser_ports(self):

        # Add Ports for the condenser
        # Inlet port (the vapor from the top tray)
        self.add_inlet_port()

        # Outlet ports that always exist irrespective of condenser type
        self.reflux = Port(noruleinit=True, doc="Reflux stream that is"
                           " returned to the top tray.")
        self.distillate = Port(noruleinit=True, doc="Reflux stream that is"
                               " returned to the top tray.")

        # Add codnenser specific variables
        self.reflux_ratio = Var(initialize=0.5, doc="reflux ratio for "
                                "the condenser")

        # Get dict of Port members and names
        member_list = self.control_volume.\
            properties_out[0].define_port_members()

        for k in member_list:
            if "flow" not in k:
                if not member_list[k].is_indexed():
                    var = self.control_volume.properties_out[:].\
                        component(member_list[k].local_name)
                else:
                    var = self.control_volume.properties_out[:].\
                        component(member_list[k].local_name)[...]

                # add the reference and variable name to the reflux port
                self.reflux.add(Reference(var), k)
                # add the reference and variable name to the distillate port
                self.distillate.add(Reference(var), k)
            else:
                if not member_list[k].is_indexed():
                    def rule_reflux_flow(self, t):
                        return self.control_volume.properties_out[t].\
                            component(member_list[k].local_name) * \
                            (self.reflux_ratio / (1 + self.reflux_ratio))
                    self.e_reflux_flow = Expression(self.flowsheet().time,
                                                    rule=rule_reflux_flow)
                    self.reflux.add(self.e_reflux_flow, k)

                    def rule_distillate_flow(self, t):
                        return self.control_volume.properties_out[t].\
                            component(member_list[k].local_name) / \
                            (1 + self.reflux_ratio)
                    self.e_distillate_flow = Expression(
                        self.flowsheet().time, rule=rule_distillate_flow)
                    self.distillate.add(self.e_distillate_flow, k)
                else:
                    index_set = member_list[k].index_set()

                    def rule_flow(self, t, *args):
                        return self.control_volume.properties_out[t, ...].\
                            component(member_list[k].local_name)[...] / \
                            (1 + self.reflux_ratio)
                    self.e_flow = Expression((self.flowsheet().time, index_set),
                                             rule=rule_flow)
                    self.reflux.add(self.e_flow, k)
