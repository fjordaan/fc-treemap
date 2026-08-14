# Ticket: Refine nearby park markers — dot-only at first, label on zoom-out and hover

## Summary

The nearby parks feature currently shows a dot + label at all zoom levels
where markers are visible. This ticket refines that: the label is hidden by
default and only shown when zoomed further out, or on desktop hover.

This change is already implemented in the sibling `park-treemap` project
(commit `2669d59`). Replicate it in fc-treemap.

---

## Behaviour

- **Zoom 18** (one step out from normal): dot only, no label
- **Zoom 17 and below**: dot + label
- **Desktop hover** (any zoom where dot is visible): label appears on hover

---

## Implementation

### Two JS constants (already present — add the second)

```js
const PARK_ZOOM_THRESHOLD = 19;  // dot visible below this zoom level
const PARK_LABEL_THRESHOLD = 18; // label visible below this zoom level (zoom 17 and below)
```

### Update `updateParkMarkersVisibility`

```js
function updateParkMarkersVisibility() {
  const zoom = map.getZoom();
  if (zoom < PARK_ZOOM_THRESHOLD) {
    if (!map.hasLayer(parkMarkerLayer)) parkMarkerLayer.addTo(map);
  } else {
    if (map.hasLayer(parkMarkerLayer)) parkMarkerLayer.remove();
  }
  map.getContainer().classList.toggle('park-labels-visible', zoom < PARK_LABEL_THRESHOLD);
}
```

### CSS changes

Add `display: none` as the default for `.park-marker-label`, then reveal it
via a map container class and a hover rule:

```css
.park-marker-label {
  display: none;
  /* ...existing styles unchanged... */
}
#map.park-labels-visible .park-marker-label { display: block; }
@media (hover: hover) {
  .park-marker-wrap:hover .park-marker-label { display: block; }
}
```

The `@media (hover: hover)` ensures the hover rule only applies on devices
with a pointer that supports hover (mouse/trackpad), not touch screens.
