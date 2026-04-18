# Converting tree map CSV to KML file

We use this to convert a CSV exported from Google Sheets to a KML that can be imported into Google Maps.

Google Sheet: [Fulham Cemetery trees - Google Sheets](https://docs.google.com/spreadsheets/d/16056CHjRL4-hbd4hbIb1czvrryGKcwMFYWCDeMDDAHM/edit?usp=sharing)

Google Map: https://www.google.com/maps/d/u/0/edit?mid=1nBD_JwoFhm5SnR1JN7_vZsDtL_6CBAY&usp=sharing

This will become obsolete when we create a custom Leaflet map.

## Fields to convert

Description is a single field, consisting of multiple lines, in the form Property: **Value** (Value in bold).

Only include the CSV field if it has content, otherwise leave out that line.

| KML property | CSV field                                                                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Title        | Scientific name                                                                                                                            |
| Description  | Common name: Value                                                                                                                         |
|              | Other names: Value                                                                                                                         |
|              | Year planted: Value                                                                                                                        |
|              | Est. year planted: Value                                                                                                                   |
|              | Year died: Value                                                                                                                           |
|              | Form: Value                                                                                                                                |
|              | Condition: Value                                                                                                                           |
|              | Height: Value                                                                                                                              |
|              | Notes: Value                                                                                                                               |
|              | Tree tag: Value                                                                                                                            |
|              | Described: Value                                                                                                                           |
|              | Tags: Value                                                                                                                                |
|              | Ref: Value                                                                                                                                 |
|              | FCF number: Value                                                                                                                          |
| Icon         | Default icon: Circle                                                                                                                       |
|              | If tag includes Highlight, Star                                                                                                            |
|              | If tag includes "New", Pin                                                                                                                 |
|              | If condition is "Dead", Cross (supersedes other tags)                                                                                      |
|              | If tag includes "TBC", Question mark (supersedes other tags)                                                                               |
| Colour       | Unique colour for every scientific name<br/>Base the hue on the first part of the name, and use different tints of that hue for variations |

## Colours

- Lime: light green

- Cherry Kanzan and Beni-yutaka: pink

- All other cherry: light pink

- Cedars: tints of brown

- Malus: tints of light blue

- Maples: tints of orange

- Sycamores: tints of red

- Cypresses: tints of dark green

- Plane: tints of yellow

- Hornbeam: tints of mid green

- All others: random colours that are different from the above, again basing the hue on the first part of the name and different tints for variations

## To do

Links to URLs, photos
