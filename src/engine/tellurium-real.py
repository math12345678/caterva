#!/usr/bin/env python3
"""
Real Tellurium Kinetics Simulation Engine

This is the actual Python engine that runs enzyme kinetics simulations
using real Tellurium (libroadrunner wrapper).

Install dependencies:
    pip install tellurium libroadrunner
"""

import json
import sys
import traceback
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional


@dataclass
class SimulationPoint:
    """Single point in simulation trajectory"""
    time: float
    substrate: float
    product: float
    velocity: float
    enzyme: float = 1.0


@dataclass
class SimulationResult:
    """Complete simulation result"""
    query: str
    model: str
    parameters: Dict[str, float]
    trajectory: List[Dict[str, float]]
    finalValue: float
    computedMetrics: Dict[str, float]
    success: bool
    error: Optional[str] = None


def create_michaelis_menten_sbml(
    substrate_initial: float,
    km: float,
    vmax: float,
    enzyme_concentration: float = 1.0
) -> str:
    """Create SBML model for Michaelis-Menten kinetics"""

    # SBML Level 3 Version 1 model
    # Rate equation: v = (vmax * [S]) / (km + [S])

    sbml = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">
  <model id="michaelis_menten">
    <listOfCompartments>
      <compartment id="cell" constant="true" spatialDimensions="3" size="1"/>
    </listOfCompartments>

    <listOfSpecies>
      <species id="S" compartment="cell" initialConcentration="{substrate_initial}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="P" compartment="cell" initialConcentration="0"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
      <species id="E" compartment="cell" initialConcentration="{enzyme_concentration}"
               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>
    </listOfSpecies>

    <listOfParameters>
      <parameter id="km" value="{km}" constant="true"/>
      <parameter id="vmax" value="{vmax}" constant="true"/>
    </listOfParameters>

    <listOfReactions>
      <reaction id="r1" reversible="false" fast="false">
        <listOfReactants>
          <speciesReference species="S" stoichiometry="1" role="substrate"/>
        </listOfReactants>
        <listOfProducts>
          <speciesReference species="P" stoichiometry="1" role="product"/>
        </listOfProducts>
        <kineticLaw>
          <math xmlns="http://www.w3.org/1998/Math/MathML">
            <apply>
              <divide/>
              <apply>
                <times/>
                <ci>vmax</ci>
                <ci>S</ci>
              </apply>
              <apply>
                <plus/>
                <ci>km</ci>
                <ci>S</ci>
              </apply>
            </apply>
          </math>
        </kineticLaw>
      </reaction>
    </listOfReactions>
  </model>
</sbml>'''

    return sbml


def run_simulation(
    substrate_initial: float,
    km: float,
    vmax: float,
    end_time: float = 10.0,
    num_points: int = 101,
    enzyme_concentration: float = 1.0
) -> SimulationResult:
    """
    Run real Michaelis-Menten kinetics simulation using Tellurium

    Returns actual simulation results with real kinetics
    """

    try:
        # Try to import tellurium
        try:
            import tellurium as te
        except ImportError:
            return SimulationResult(
                query="michaelis-menten",
                model="michaelis-menten",
                parameters={"km": km, "vmax": vmax, "s0": substrate_initial},
                trajectory=[],
                finalValue=0,
                computedMetrics={},
                success=False,
                error="Tellurium not installed. Install with: pip install tellurium"
            )

        # Create SBML model
        sbml_string = create_michaelis_menten_sbml(
            substrate_initial, km, vmax, enzyme_concentration
        )

        # Load model
        r = te.loadSBMLFromString(sbml_string)

        # Simulate
        time = r.simulate(0, end_time, num_points)

        # Extract results
        substrate_values = r['S']
        product_values = r['P']
        time_values = r['time']

        # Calculate velocities (rate of change)
        velocities = []
        for i in range(len(substrate_values)):
            if i == 0:
                v = 0
            else:
                ds_dt = (substrate_values[i] - substrate_values[i-1]) / (time_values[i] - time_values[i-1])
                v = -ds_dt  # Negative because substrate is being consumed
            velocities.append(max(0, v))  # Velocity is always non-negative

        # Build trajectory
        trajectory = []
        for i in range(len(time_values)):
            trajectory.append({
                "time": float(time_values[i]),
                "substrate": float(substrate_values[i]),
                "product": float(product_values[i]),
                "velocity": float(velocities[i])
            })

        # Calculate metrics
        final_substrate = float(substrate_values[-1])
        total_consumed = substrate_initial - final_substrate
        total_produced = float(product_values[-1])

        metrics = {
            "totalSubstrateConsumed": total_consumed,
            "totalProductFormed": total_produced,
            "conversionPercentage": (total_consumed / substrate_initial * 100) if substrate_initial > 0 else 0,
            "maxVelocity": max(velocities) if velocities else 0,
            "avgVelocity": sum(velocities) / len(velocities) if velocities else 0
        }

        return SimulationResult(
            query="michaelis-menten",
            model="michaelis-menten",
            parameters={"km": km, "vmax": vmax, "s0": substrate_initial},
            trajectory=trajectory,
            finalValue=final_substrate,
            computedMetrics=metrics,
            success=True
        )

    except Exception as e:
        return SimulationResult(
            query="michaelis-menten",
            model="michaelis-menten",
            parameters={"km": km, "vmax": vmax, "s0": substrate_initial},
            trajectory=[],
            finalValue=0,
            computedMetrics={},
            success=False,
            error=f"Simulation error: {str(e)}\n{traceback.format_exc()}"
        )


def main():
    """Entry point when called from Node.js"""

    try:
        # Read input from stdin
        input_data = json.loads(sys.stdin.read())

        # Extract parameters
        substrate_initial = input_data.get("s0", 10.0)
        km = input_data.get("km", 5.2)
        vmax = input_data.get("vmax", 12.8)
        end_time = input_data.get("endTime", 10.0)
        num_points = input_data.get("numPoints", 101)
        enzyme_concentration = input_data.get("e0", 1.0)

        # Run simulation
        result = run_simulation(
            substrate_initial=substrate_initial,
            km=km,
            vmax=vmax,
            end_time=end_time,
            num_points=num_points,
            enzyme_concentration=enzyme_concentration
        )

        # Output as JSON
        print(json.dumps(asdict(result)))
        sys.exit(0 if result.success else 1)

    except Exception as e:
        error_result = {
            "query": "michaelis-menten",
            "model": "michaelis-menten",
            "parameters": {},
            "trajectory": [],
            "finalValue": 0,
            "computedMetrics": {},
            "success": False,
            "error": f"Fatal error: {str(e)}"
        }
        print(json.dumps(error_result))
        sys.exit(1)


if __name__ == "__main__":
    main()
