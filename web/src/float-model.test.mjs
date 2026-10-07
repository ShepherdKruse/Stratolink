import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { calculateFloat, defaults, atmosphereAtDensity, puritySweep } from './float-model.mjs';

const source = JSON.parse(readFileSync(new URL('./fixtures/float-reference.json', import.meta.url)));
const close = (a, b, tolerance = 1e-7) => assert.ok(Math.abs(a - b) < tolerance, `${a} differs from ${b}`);
test('reproduces the source spreadsheet outputs', () => {
  const output = calculateFloat(defaults);
  const values = Object.fromEntries(source.sheets[0].rows.flatMap(row => row.cells.map(cell => [cell.address, cell.value])));
  for (const [property, cell] of Object.entries({ volume:'B35', dryMass:'B36', liftPerLitre:'B37', fillLitres:'B39', gasMass:'B41', totalMass:'B43', density:'B44', height:'B47', altitude:'B48', temperature:'B50', tautAltitude:'B51', ascent:'B54', internalPressure:'B55', ambientPressure:'B56', pressure:'B57', cooling:'B58' })) close(output[property], values[cell]);
});
test('reproduces every source purity row', () => {
  for (const row of source.sheets[1].rows.filter(row => row.row >= 5 && row.row <= 21)) {
    const values = row.cells.map(cell => cell.value);
    const output = calculateFloat({ ...defaults, purity: values[0] * 100 });
    close(output.fillLitres, values[5]);
    close(output.altitude / 1000, values[10]);
    close(output.pressure, values[11]);
  }
});
test('rejects incomplete, nonphysical and overfilled inputs', () => {
  for (const change of [{payload:NaN}, {purity:0}, {purity:101}, {diameter:0}, {payload:-1}, {utilization:0}, {gas:'unknown'}, {diameter:1}, {purity:1}, {payload:Infinity}]) assert.ok(calculateFloat({...defaults,...change}).error, JSON.stringify(change));
});
test('handles atmosphere layer boundaries and out-of-range density', () => {
  for (const [pressure, temperature, height] of [[101325,288.15,0],[22632.06,216.65,11000],[5474.889,216.65,20000],[868.019,228.65,32000]]) close(atmosphereAtDensity(pressure / ((8.314462/.0289647)*temperature)).height, height, .2);
  assert.equal(atmosphereAtDensity(2), null);
  assert.equal(atmosphereAtDensity(.0001), null);
});
test('zero free lift stays finite; sweep includes current purity once', () => {
  const result = calculateFloat({...defaults,freeLift:0});
  assert.equal(result.ascent, 0);
  close(result.pressure, 0);
  const rows = puritySweep({...defaults,purity:97});
  assert.equal(rows.filter(row=>row.purity===97).length, 1);
  assert.equal(rows[0].delta, 0);
  assert.ok(calculateFloat({...defaults,gas:'H2'}).altitude > calculateFloat(defaults).altitude);
});
