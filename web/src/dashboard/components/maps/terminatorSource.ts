import type { CustomSourceInterface } from 'mapbox-gl';
import { TerminatorRenderer, type TerminatorBasemap, type TerminatorOptions } from './terminatorRenderer';

export type { TerminatorBasemap } from './terminatorRenderer';
type Tile = { z: number; x: number; y: number };
type Pending = { resolve: (value: ImageData) => void; reject: (reason: Error) => void };

/** Keep shader compilation and synchronous pixel readbacks off the UI thread. */
export class TerminatorSource implements CustomSourceInterface<ImageData> {
    readonly id: string;
    readonly type = 'custom' as const;
    readonly dataType = 'raster' as const;
    readonly tileSize: number;
    readonly maxzoom?: number;
    update?: () => void;
    clearTiles?: () => void;

    private options: TerminatorOptions;
    private worker?: Worker;
    private fallback?: TerminatorRenderer;
    private pending = new Map<number, Pending>();
    private sequence = 0;
    private disposed = false;

    constructor(options: TerminatorOptions = {}) {
        this.options = { ...options };
        this.id = options.id ?? 'sl-terminator';
        this.tileSize = options.tileSize ?? 256;
        this.maxzoom = options.maxzoom;
        if (typeof Worker !== 'undefined' && typeof OffscreenCanvas !== 'undefined') {
            this.worker = new Worker(new URL('./terminator.worker.ts', import.meta.url), { type: 'module' });
            this.worker.onmessage = ({ data }) => {
                if (data.id === 0 && data.error) {
                    this.stopWorker(new Error(data.error));
                    return;
                }
                const pending = this.pending.get(data.id);
                if (!pending) return;
                this.pending.delete(data.id);
                if (data.error) pending.reject(new Error(data.error));
                else pending.resolve(new ImageData(new Uint8ClampedArray(data.pixels), this.tileSize, this.tileSize));
            };
            this.worker.onerror = () => this.stopWorker(new Error('Day/night worker unavailable'));
            this.worker.postMessage({ type: 'init', options });
        }
    }

    private stopWorker(error: Error) {
        this.worker?.terminate();
        this.worker = undefined;
        for (const pending of this.pending.values()) pending.reject(error);
        this.pending.clear();
    }

    setBasemap(basemap: TerminatorBasemap) {
        if (this.options.basemap === basemap) return;
        this.options.basemap = basemap;
        this.worker?.postMessage({ type: 'basemap', basemap });
        this.fallback?.setBasemap(basemap);
        this.clearTiles?.();
        this.update?.();
    }

    setDate(date: Date) {
        if (this.options.date?.valueOf() === date.valueOf()) return;
        this.options.date = date;
        this.worker?.postMessage({ type: 'date', date });
        this.fallback?.setDate(date);
        this.clearTiles?.();
        this.update?.();
    }

    async loadTile(tile: Tile, { signal }: { signal?: AbortSignal } = {}): Promise<ImageData> {
        if (this.disposed || signal?.aborted) throw new DOMException('Tile cancelled', 'AbortError');
        if (this.worker) {
            const id = ++this.sequence;
            const abort = () => {
                this.pending.get(id)?.reject(new DOMException('Tile cancelled', 'AbortError'));
                this.pending.delete(id);
            };
            try {
                return await new Promise<ImageData>((resolve, reject) => {
                    this.pending.set(id, { resolve, reject });
                    signal?.addEventListener('abort', abort, { once: true });
                    this.worker!.postMessage({ type: 'tile', id, tile });
                });
            } catch (error) {
                if (this.worker || this.disposed || signal?.aborted) throw error;
                // Older browsers can expose OffscreenCanvas without worker WebGL.
            } finally {
                signal?.removeEventListener('abort', abort);
            }
        }
        this.fallback ??= new TerminatorRenderer(this.options);
        return this.fallback.loadTile(tile);
    }

    onRemove() {
        this.disposed = true;
        this.stopWorker(new DOMException('Source removed', 'AbortError'));
        this.fallback?.dispose();
    }
}
