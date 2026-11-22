# Fulham Cemetery tree map

A custom map of the trees of Fulham Cemetery, with data coming from Google Sheets.

The tree database is a Google Sheet with public viewing rights: [Fulham Cemetery trees - Google Sheets](https://docs.google.com/spreadsheets/d/16056CHjRL4-hbd4hbIb1czvrryGKcwMFYWCDeMDDAHM/edit?usp=sharing)

Tree species list: [Fulham Cemetery tree species - Google Sheets](https://docs.google.com/spreadsheets/d/1hLMmscbXL9OqI8c74IjzgJ8rfj9rqt7uL3ujtUZbJmU/edit?usp=sharing)

View it here: https://trees.fulhamcemeteryfriends.org.uk/

Drone orthophoto base layer (how it was made): [Drone orthophoto.md](Drone%20orthophoto.md)

## Credits

The map uses
[Leaflet](https://leafletjs.com/) for the map,
[Tagify](https://yaireo.github.io/tagify/) for the tag inputs,
[OpenStreetMap](https://www.openstreetmap.org/) for the street map tiles, © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, and
[Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) for the satellite tiles (Esri, Maxar, Earthstar Geographics).

`drone/os-buildings.geojson`, used to check how accurately the base layers line up, contains OS data © Crown copyright and database right 2026, from [OS OpenMap Local](https://www.ordnancesurvey.co.uk/products/os-open-map-local), licensed under the [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

The drone layer's accuracy was checked against Environment Agency LiDAR: contains Environment Agency information © Environment Agency and/or database right 2023, from the [National LIDAR Programme](https://environment.data.gov.uk/survey) 2023 First Return DSM, licensed under the [Open Government Licence](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
