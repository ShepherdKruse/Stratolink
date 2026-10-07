import { TerminatorRenderer, type TerminatorOptions, type TerminatorBasemap } from './terminatorRenderer';

type Request =
    | { type: 'init'; options: TerminatorOptions }
    | { type: 'date'; date: Date }
    | { type: 'basemap'; basemap: TerminatorBasemap }
    | { type: 'tile'; id: number; tile: { z: number; x: number; y: number } };

let renderer: TerminatorRenderer;
self.onmessage = async ({ data }: MessageEvent<Request>) => {
    try {
        if (data.type === 'init') renderer = new TerminatorRenderer(data.options);
        else if (data.type === 'date') renderer.setDate(data.date);
        else if (data.type === 'basemap') renderer.setBasemap(data.basemap);
        else {
            const image = await renderer.loadTile(data.tile);
            self.postMessage({ id: data.id, pixels: image.data.buffer }, { transfer: [image.data.buffer] });
        }
    } catch (error) {
        self.postMessage({ id: data.type === 'tile' ? data.id : 0, error: error instanceof Error ? error.message : String(error) });
    }
};
