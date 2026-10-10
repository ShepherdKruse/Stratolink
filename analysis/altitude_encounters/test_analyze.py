import math
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

from analyze import ROOT, atmosphere_geometric, encounter_expectation, probability_at_least_one, run_calculator, sphere_flow


class ModelTests(unittest.TestCase):
    def test_calculator_cases_match_independent_isa_and_mass_balance(self):
        data = run_calculator(ROOT / "web/src/float-model.mjs")
        for case in data["cases"]:
            result = case["result"]
            self.assertAlmostEqual(result["dryMass"]+result["gasMass"],result["totalMass"])
            density, _, _ = atmosphere_geometric(result["altitude"])
            self.assertAlmostEqual(density*result["volume"]*1000,result["totalMass"],delta=.01)
            self.assertGreater(result["pressure"],0)
        self.assertGreater(data["cases"][1]["result"]["altitude"],data["cases"][0]["result"]["altitude"])

    def test_cli_runs_from_a_checkout_without_a_neighbor_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            for relative in [
                "analysis/altitude_encounters/analyze.py",
                "simulation/predictor/atmosphere/isa.py",
                "web/src/float-model.mjs",
            ]:
                destination = checkout / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            result = subprocess.run(
                [sys.executable, str(checkout / "analysis/altitude_encounters/analyze.py")],
                cwd=directory, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            output = checkout / "analysis/altitude_encounters"
            data = json.loads((output / "results.json").read_text())
            self.assertEqual(data["source"]["path"], "web/src/float-model.mjs")
            self.assertEqual(len(data["cases"]), 4)
            for name in ["altitude.png", "encounters.png", "airflow.png"]:
                self.assertGreater((output / name).stat().st_size, 0)

    def test_encounter_units_and_linear_exposure(self):
        lam = encounter_expectation(1e-6,250,50,30)
        self.assertAlmostEqual(lam,3.24e-5)
        self.assertAlmostEqual(encounter_expectation(1e-6,250,50,30,1000),1000*lam)
        self.assertAlmostEqual(encounter_expectation(1e-6,250,50,60),2*lam)

    def test_probability_limits(self):
        self.assertEqual(probability_at_least_one(0),0)
        self.assertAlmostEqual(probability_at_least_one(1),1-math.exp(-1))
        self.assertEqual(probability_at_least_one(1000),1)

    def test_invalid_encounter_inputs(self):
        for bad in [-1,float("inf"),float("nan")]:
            with self.assertRaises(ValueError):
                encounter_expectation(bad,250,50,30)

    def test_density_decreases(self):
        rho = [atmosphere_geometric(z)[0] for z in [10000,12000,14000,16000]]
        self.assertTrue(all(a>b for a,b in zip(rho,rho[1:])))
        self.assertAlmostEqual(atmosphere_geometric(0)[0],1.225,places=3)

    def test_sphere_flow_boundary_and_symmetry(self):
        theta = np.linspace(0,2*np.pi,100)
        x,y = 2*np.cos(theta),2*np.sin(theta)
        u,v = sphere_flow(x,y)
        np.testing.assert_allclose(u*x+v*y,0,atol=1e-10)
        self.assertEqual(sphere_flow(-3,0)[1],0)
        self.assertAlmostEqual(sphere_flow(-2,0)[0],0)
        self.assertAlmostEqual(sphere_flow(-10000,0)[0],250,places=6)


if __name__ == "__main__":
    unittest.main()
