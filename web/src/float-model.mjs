// Constants and layer inversion from stratolink_float_calculator_v2.
export const defaults = { payload: 10.3, envelope: 47, extra: 0, diameter: 36, utilization: 98, gas: 'He', purity: 80, freeLift: 7 };
const R = 8.314462;
const AIR_MOLAR = .0289647;
const R_AIR = R / AIR_MOLAR;
const G = 9.80665;
const RHO_AIR = 1.225;
const EARTH_RADIUS = 6356766;
const layers = [
  { height: 0, temperature: 288.15, pressure: 101325, lapse: -.0065 },
  { height: 11000, temperature: 216.65, pressure: 22632.06, lapse: 0 },
  { height: 20000, temperature: 216.65, pressure: 5474.889, lapse: .001 },
  { height: 32000, temperature: 228.65, pressure: 868.019, lapse: .0028 },
].map(layer => ({ ...layer, density: layer.pressure / (R_AIR * layer.temperature) }));

export function atmosphereAtDensity(density) {
  if (!Number.isFinite(density) || density > layers[0].density || density < .0014275) return null;
  const layer = layers.find((_, i) => i === layers.length - 1 || density >= layers[i + 1].density);
  const temperature = layer.lapse === 0 ? layer.temperature : layer.temperature * (density / layer.density) ** (1 / (-G / (R_AIR * layer.lapse) - 1));
  const height = layer.lapse === 0
    ? layer.height - R_AIR * temperature / G * Math.log(density / layer.density)
    : layer.height + (temperature - layer.temperature) / layer.lapse;
  return { height, altitude: EARTH_RADIUS * height / (EARTH_RADIUS - height), temperature, pressure: density * R_AIR * temperature };
}

export function calculateFloat(input) {
  const { payload, envelope, extra, diameter, utilization, gas, purity, freeLift } = input;
  if (![payload, envelope, extra, diameter, utilization, purity, freeLift].every(Number.isFinite)) return { error: 'Enter a number in every field.' };
  if ([payload, envelope, extra, freeLift].some(value => value < 0) || payload + envelope + extra <= 0) return { error: 'Masses must be zero or greater, with a total dry mass above zero.' };
  if (diameter <= 0) return { error: 'Envelope diameter must be greater than zero.' };
  if (utilization <= 0 || utilization > 100 || purity <= 0 || purity > 100) return { error: 'Volume utilization and gas purity must be greater than 0% and no more than 100%.' };
  if (!['He', 'H2'].includes(gas)) return { error: 'Select a supported gas.' };
  const fraction = purity / 100;
  const molarMass = fraction * (gas === 'He' ? .0040026 : .00201588) + (1 - fraction) * AIR_MOLAR;
  const gasConstant = R / molarMass;
  const gasDensity = RHO_AIR * molarMass / AIR_MOLAR;
  const liftPerLitre = RHO_AIR - gasDensity;
  const volume = 4 / 3 * Math.PI * (diameter * .0254 / 2) ** 3 * utilization / 100;
  const dryMass = payload + envelope + extra;
  const fillLitres = (dryMass + freeLift) / liftPerLitre;
  const gasMass = fillLitres * gasDensity;
  const totalMass = dryMass + gasMass;
  const density = totalMass / 1000 / volume;
  const common = { volume, dryMass, liftPerLitre, fillLitres, gasMass, totalMass, density };
  if (![volume, fillLitres, gasMass, totalMass, density].every(Number.isFinite)) return { error: 'These values are outside the numerical range of the model.' };
  if (fillLitres > volume * 1000) return { ...common, error: 'The required fill exceeds the usable envelope volume. Change the mass, purity, envelope size, or free lift.' };
  const atmosphere = atmosphereAtDensity(density);
  if (!atmosphere) return { ...common, error: 'The predicted float is outside the model range of 0 to 47 km geopotential altitude.' };
  const internalPressure = gasMass / 1000 / volume * gasConstant * atmosphere.temperature;
  const pressure = internalPressure - atmosphere.pressure;
  const cooling = atmosphere.pressure / (gasMass / 1000 / volume * gasConstant) - atmosphere.temperature;
  const radiusAtFill = (3 * fillLitres / 1000 / (4 * Math.PI)) ** (1 / 3);
  const ascent = Math.sqrt(2 * freeLift / 1000 * G / (RHO_AIR * .47 * Math.PI * radiusAtFill ** 2));
  const taut = atmosphereAtDensity(gasMass / 1000 * gasConstant / volume / R_AIR);
  return { ...common, altitude: atmosphere.altitude, height: atmosphere.height, temperature: atmosphere.temperature, pressure, internalPressure, ambientPressure: atmosphere.pressure, cooling, ascent, tautAltitude: taut?.altitude ?? null };
}

export function puritySweep(input) {
  const pure = calculateFloat({ ...input, purity: 100 });
  return [...new Set([100, 99.8, 99.5, 99, 98.5, 98, 97.5, 97, 96.5, 96, 95.5, 95, 94, 93, 92, 91, 90, input.purity])]
    .filter(purity => purity > 0 && purity <= 100).sort((a, b) => b - a)
    .map(purity => {
      const result = calculateFloat({ ...input, purity });
      return { purity, ...result, delta: !result.error && !pure.error ? result.altitude - pure.altitude : null };
    });
}
