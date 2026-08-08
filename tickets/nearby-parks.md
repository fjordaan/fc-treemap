# Ticket: Nearby parks discovery

## Summary

When a user zooms out on the map, show markers for other nearby tree maps
(park-treemap forks and fc-treemap itself) so they can navigate to them. Each
marker shows the park name and opens a popup with a link to that map.

This feature is already implemented in the sibling project `park-treemap`
(see `../park-treemap/index.html`). This ticket replicates it in fc-treemap,
adapting to fc-treemap's code conventions.

---

## Behaviour

- A shared `registry.json` lives in the upstream `fjordaan/park-treemap` repo
  and lists all known parks with name, coordinates, and URL.
- At map load, fc-treemap fetches this file from:
  `https://raw.githubusercontent.com/fjordaan/park-treemap/main/registry.json`
- When the map zoom drops below **19**, park markers appear. At zoom 19+
  (normal street-level view), they are hidden.
- Each park is shown as a clickable marker: a green dot with the park name
  as an inline label to its right. Clicking either opens a popup with a
  "Open map ↗" link.
- The current site (`https://trees.fulhamcemeteryfriends.org.uk/`) is
  excluded from its own marker list.

---

## registry.json format

```json
[
  {
    "name": "Bayonne Trees",
    "lat": 51.485142,
    "lng": -0.215255,
    "url": "https://twynholmtra.github.io/bayonne-trees/"
  },
  {
    "name": "Lillie Road Recreation Ground",
    "lat": 51.4827750,
    "lng": -0.2176881,
    "url": "https://boonoit.github.io/Reposi-tree/"
  },
  {
    "name": "Fulham Cemetery",
    "lat": 51.4804700,
    "lng": -0.2165562,
    "url": "https://trees.fulhamcemeteryfriends.org.uk/"
  }
]
```

A 404 or network error on the fetch should be silently ignored.

---

## Implementation (adapt from park-treemap)

Read the working implementation in `../park-treemap/index.html` — search for
`NEARBY PARKS` to find the relevant block. The key pieces are:

### JS constants (after `map` is initialised)
```js
const parkMarkerLayer = L.layerGroup();
const PARK_ZOOM_THRESHOLD = 19;
```

### Three functions
- `updateParkMarkersVisibility()` — adds/removes `parkMarkerLayer` from map
  based on `map.getZoom() < PARK_ZOOM_THRESHOLD`
- `buildParkMarkers(parks)` — creates a `L.marker` with a `divIcon` for each
  park (excluding self), binds a popup with "Open map ↗" link
- `loadParkRegistry()` — fetches the registry JSON, calls the two above

### Hook and call
```js
map.on('zoomend', updateParkMarkersVisibility);
loadParkRegistry();
```

### CSS (marker dot + label)
```css
.park-marker-wrap { display: flex; align-items: center; cursor: pointer; white-space: nowrap; }
.park-marker-dot  { width: 18px; height: 18px; border-radius: 50%; background: #2d6a2d; border: 2px solid white; box-shadow: 0 1px 4px rgba(0,0,0,0.3); flex-shrink: 0; }
.park-marker-label { background: #2d6a2d; color: white; font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 3px; box-shadow: 0 1px 4px rgba(0,0,0,0.3); margin-left: 4px; }
```

### Self-exclusion
```js
const currentUrl = (window.location.origin + window.location.pathname).replace(/\/+$/, '/');
// skip entry if park.url.replace(/\/+$/, '/') === currentUrl
```

---

## Notes

- No changes needed to `add-tree-script.gs`.
- fc-treemap uses its own HTML/JS conventions — adapt rather than copy verbatim.
- The `esc()` HTML-escaping helper is already present in fc-treemap's
  `index.html`; use it for park name and URL in the popup HTML.
