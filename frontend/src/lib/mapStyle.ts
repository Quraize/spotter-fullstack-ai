// Basemap and route colours, kept together because the colours are chosen against the basemap
// (see mapStyle.test.ts for the contrast rules).

// OpenFreeMap "liberty": free vector tiles, no key, no request limits (https://openfreemap.org).
// A coloured basemap (blue water, green parks, orange highways on cream land) rather than the grey
// "positron" one; the risk colours and the blue selected route still stand out on it.
export const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

/** Land colour of the basemap (its `background` layer); the route colours are checked against it. */
export const BASEMAP_LAND = '#f8f4f0'

export const SELECTED_ROUTE_COLOR = '#1565c0'
/** Muted but still readable on cream land; the white casing separates it from the basemap's roads. */
export const OTHER_ROUTE_COLOR = '#607d8b'
