import { calculateFloat, defaults, puritySweep } from './float-model.mjs';

const form = document.querySelector('[data-float-calculator]');
if (form) {
  const error = document.querySelector('[data-calc-error]');
  const results = document.querySelector('[data-calc-results]');
  const number = (value, digits = 1) => Number.isFinite(value) ? value.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : 'Unavailable';
  function update() {
    const input = Object.fromEntries([...new FormData(form)].map(([key, value]) => [key, key === 'gas' ? value : value.trim() ? Number(value) : NaN]));
    const result = calculateFloat(input);
    error.textContent = result.error || (input.freeLift === 0 ? 'Zero free lift gives no initial ascent in this model.' : '');
    error.hidden = !error.textContent;
    results.hidden = Boolean(result.error);
    if (result.error) return;
    const outputs = { altitude: `${number(result.altitude / 1000, 2)} km`, fill: `${number(result.fillLitres)} L`, pressure: `${number(result.pressure, 0)} Pa`, ascent: `${number(result.ascent, 2)} m/s`, dry: `${number(result.dryMass)} g`, gas: `${number(result.gasMass)} g`, volume: `${number(result.volume * 1000)} L`, lift: `${number(result.liftPerLitre, 3)} g/L`, taut: result.tautAltitude === null ? 'Outside model range' : `${number(result.tautAltitude / 1000, 2)} km`, cooling: `${number(result.cooling)} K` };
    for (const [key, value] of Object.entries(outputs)) document.querySelector(`[data-result="${key}"]`).textContent = value;
    const sweep = puritySweep(input);
    document.querySelector('[data-purity-rows]').innerHTML = sweep.map(row => `<tr${row.purity === input.purity ? ' class="is-selected"' : ''}><th scope="row">${number(row.purity, row.purity % 1 ? 1 : 0)}%${row.purity === input.purity ? '<span class="sr-only">, selected</span>' : ''}</th><td>${row.error ? 'Unavailable' : number(row.fillLitres)}</td><td>${row.error ? 'Unavailable' : number(row.altitude / 1000, 2)}</td><td>${row.error ? 'Unavailable' : number(row.pressure, 0)}</td><td>${row.delta === null ? 'Unavailable' : number(row.delta, 0)}</td></tr>`).join('');
    drawPlot(sweep, input.purity);
  }
  function drawPlot(rows, selected) {
    const valid = rows.filter(row => !row.error);
    const svg = document.querySelector('[data-purity-plot]');
    svg.toggleAttribute('hidden', valid.length < 2);
    if (valid.length < 2) return;
    const minX = Math.min(...valid.map(row => row.purity));
    const low = Math.floor(Math.min(...valid.map(row => row.altitude / 1000)) * 2) / 2;
    const high = Math.max(low + .5, Math.ceil(Math.max(...valid.map(row => row.altitude / 1000)) * 2) / 2);
    const x = purity => 56 + (purity - minX) / (100 - minX || 1) * 544;
    const y = altitude => 210 - (altitude / 1000 - low) / (high - low) * 176;
    const grid = [low, (low + high) / 2, high].map(tick => `<line x1="56" x2="600" y1="${y(tick * 1000)}" y2="${y(tick * 1000)}"/><text x="44" y="${y(tick * 1000) + 4}" text-anchor="end">${number(tick, 1)}</text>`).join('');
    const current = valid.find(row => row.purity === selected);
    svg.innerHTML = `<title>Predicted float altitude versus gas purity</title><desc>Keeping the other inputs fixed, predicted float ranges from ${number(Math.min(...valid.map(row => row.altitude / 1000)), 2)} to ${number(Math.max(...valid.map(row => row.altitude / 1000)), 2)} kilometres. Exact values are in the table below.</desc><g class="calc-grid">${grid}</g><text x="56" y="18">Float altitude (km)</text><polyline class="calc-line" points="${valid.map(row => `${x(row.purity)},${y(row.altitude)}`).join(' ')}"/>${current ? `<circle class="calc-point" cx="${x(current.purity)}" cy="${y(current.altitude)}" r="5"/>` : ''}<text x="56" y="236">${number(minX, minX % 1 ? 1 : 0)}%</text><text x="600" y="236" text-anchor="end">100%</text><text x="328" y="262" text-anchor="middle">Gas purity by volume</text>`;
  }
  form.addEventListener('input', update);
  form.addEventListener('submit', event => event.preventDefault());
  form.querySelector('[type="reset"]').addEventListener('click', event => {
    event.preventDefault();
    for (const [name, value] of Object.entries(defaults)) form.elements[name].value = value;
    update();
  });
  update();
}


let openHelp;
const closeHelp = () => {
  if (!openHelp) return;
  openHelp.tip.hidden = true;
  openHelp.button.setAttribute('aria-expanded', 'false');
  openHelp = undefined;
};
document.querySelectorAll('[data-calc-help]').forEach(button => {
  const tip = document.getElementById(button.getAttribute('aria-controls'));
  const show = () => {
    closeHelp();
    tip.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    const anchor = button.getBoundingClientRect();
    const size = tip.getBoundingClientRect();
    const x = Math.max(16, Math.min(innerWidth - size.width - 16, anchor.x + anchor.width / 2 - size.width / 2));
    const y = anchor.top > size.height + 24 ? anchor.top - size.height - 10 : anchor.bottom + 10;
    tip.style.left = `${x}px`;
    tip.style.top = `${y}px`;
    openHelp = { button, tip };
  };
  button.addEventListener('mouseenter', show);
  button.addEventListener('focus', show);
  button.addEventListener('click', () => { if (openHelp?.button !== button) show(); });
  button.addEventListener('mouseleave', () => { if (document.activeElement !== button) closeHelp(); });
  button.addEventListener('blur', closeHelp);
});
addEventListener('keydown', event => { if (event.key === 'Escape') closeHelp(); });
addEventListener('pointerdown', event => { if (!event.target.closest('.calc-help')) closeHelp(); });
addEventListener('scroll', closeHelp, { passive: true });
addEventListener('resize', closeHelp);
