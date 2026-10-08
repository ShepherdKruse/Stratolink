import { TerminatorRenderer, nightShadePixels, type TerminatorOptions, type TerminatorBasemap } from './terminatorRenderer';

type Request =
    | { type: 'init'; options: TerminatorOptions }
    | { type: 'date'; date: Date }
    | { type: 'basemap'; basemap: TerminatorBasemap }
    | { type: 'tile'; id: number; tile: { z: number; x: number; y: number } };

let options: TerminatorOptions;
let renderer: TerminatorRenderer | undefined;
self.onmessage = async ({ data }: MessageEvent<Request>) => {
    try {
        if (data.type === 'init') {
            options = { ...data.options, date: data.options.date ?? new Date() };
            if (options.kind === 'lights') renderer = new TerminatorRenderer(options);
        } else if (data.type === 'date') {
            options.date = data.date;
            renderer?.setDate(data.date);
        } else if (data.type === 'basemap') {
            options.basemap = data.basemap;
            renderer?.setBasemap(data.basemap);
        } else {
            const size = options.tileSize ?? 256;
            const image = renderer ? await renderer.loadTile(data.tile)
                : new ImageData(nightShadePixels(data.tile, size, options.date!, options.basemap ?? 'light'), size, size);
            self.postMessage({ id: data.id, pixels: image.data.buffer }, { transfer: [image.data.buffer] });
        }
    } catch (error) {
        self.postMessage({ id: data.type === 'tile' ? data.id : 0, error: error instanceof Error ? error.message : String(error) });
    }
};
