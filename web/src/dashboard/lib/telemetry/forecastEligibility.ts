/** Registry statuses whose balloon is no longer flying. The stored forecast for
 *  such a device is a dead-reckon from its last fix that keeps ageing in Blob,
 *  not a prediction, so the dashboard neither requests it for the fleet map nor
 *  draws the forecast layers (future path, ensemble, cone, stale-GPS connector,
 *  divergence marker) for the selected balloon. Its reconstructed path is
 *  history and is still requested through the forecast API's `history` view. */
const NO_FORECAST_STATUSES = new Set(['landed', 'recovered', 'retired', 'lost', 'missing']);

export function forecastEligible(status: string | null | undefined): boolean {
    return !NO_FORECAST_STATUSES.has((status ?? '').trim().toLowerCase());
}

/** Which forecast view the detail map should load for a registry status. */
export function forecastViewFor(status: string | null | undefined): 'full' | 'history' {
    return forecastEligible(status) ? 'full' : 'history';
}
