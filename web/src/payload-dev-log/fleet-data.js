let pending;
export function loadFleet() {
  if (!pending) pending = Promise.all(['fleet.json', 'fleet-tracks.bin', 'fleet-south.bin', 'coastlines.json', 'fleet-wind.json'].map(async file => {
    const response = await fetch(`/assets/payload-dev-log/${file}`);
    if (!response.ok) throw new Error('Fleet data unavailable');
    return file.endsWith('.bin') ? new Float32Array(await response.arrayBuffer()) : response.json();
  })).then(([meta, north, south, coast, wind]) => {
    const world = new Float32Array(north.length), stride = (meta.steps + 1) * 2;
    for (let k = 0; k < meta.count; k++) {
      const source = k % 2 ? south : north, start = Math.floor(k / 2) * stride;
      world.set(source.subarray(start, start + stride), k * stride);
    }
    return { meta, tracks: { north, south, world }, coast, wind };
  }).catch(error => { pending = undefined; throw error; });
  return pending;
}
