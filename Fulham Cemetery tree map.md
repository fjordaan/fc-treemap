# Fulham Cemetery tree map

A custom map of the trees of Fulham Cemetery, with data coming from Google Sheets.

## Background

This is a replacement for a custom Google Map. The Google Map works well, it has many layers, it uses icon shapes and colours, and embedded photos. 

However, I cannot dynamically populate it from my tree database in Google Sheets, and I'm limited in the information I can display for each tree.

The tree database was merged from 2 origins:

- Tree database on Notion: [Notion](https://fcfriends.notion.site/2af75ace462d43dbb0893ef93157eed0?v=830e8cc76056445d9016892277386020&source=copy_link)

- Tree map on Google Maps: https://www.google.com/maps/d/edit?mid=1Yc1_SEv1yEuCoED7dacnXkMhTHt_K68&usp=sharing

The data was improved thanks to the identified species in this spreadsheet: [Fulham Cemetery tree species - Google Sheets](https://docs.google.com/spreadsheets/d/1hLMmscbXL9OqI8c74IjzgJ8rfj9rqt7uL3ujtUZbJmU/edit?usp=sharing)

## Technology

This should be a single web page using Leaflet for mapping. 

The tree database is a Google Sheet with public viewing rights: [Fulham Cemetery trees - Google Sheets](https://docs.google.com/spreadsheets/d/16056CHjRL4-hbd4hbIb1czvrryGKcwMFYWCDeMDDAHM/edit?usp=sharing)

It will be deployed on Github Pages.

## Design

The map should be full-screen and have standard zoom controls, and pan & zoom functionality, both desktop and mobile.

Use the default Leaflet base map for starters. I may provide a custom base map.

I may provide additional layers for paths and amenities. This could be provided as KML or as SVG, depending on which works better.

## Filters

There will be a collapsible control panel at top left with filters.

- Scientific name (Dropdown, with counts)

- Common name (Dropdown, with counts)

- Tags (checkboxes, with counts)

- Condition (checkboxes, with counts)

- Info label (checkbox, for trees where this property is non-empty)

The panel will also show the total number of trees shown.

## Tree properties

The tree database has the following properties:

| Label             | Properties & purpose                     |
| ----------------- | ---------------------------------------- |
| Ref               | Unique reference in the form xxxxx.yyyyy |
| Map link          | Link to Google Map                       |
| FCF number        | Number given to new trees                |
| Scientific name   |                                          |
| Common name       |                                          |
| Short name        |                                          |
| Other names       |                                          |
| Latitude          |                                          |
| Longitude         |                                          |
| Notes             |                                          |
| Year planted      |                                          |
| Est. year planted |                                          |
| Est. age          |                                          |
| Year died         |                                          |
| Tag               | Comma-separated list                     |
| Cemetery section  |                                          |
| Form              |                                          |
| Condition         |                                          |
| Height            |                                          |
| Described         |                                          |
| Social media      |                                          |
| Info label        |                                          |
| Water point       |                                          |
| Photo             | Link to a photo                          |
| FCF URL           | Link to FCF web page                     |
| TSO               | Link to Treesandshrubsonline             |
| Wikipedia         | Link to Wikipedia                        |

## Tree markers

Tree markers will be populated using the following properties

Description is a single field, consisting of multiple lines, in the form Property: **Value** (Value in bold), in the order shown below

Only include the field if it has content, otherwise leave out that line.

| KML property | CSV field                                                                                                                                 |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Title        | Scientific name                                                                                                                           |
| Description  | Common name: Value                                                                                                                        |
|              | Other names: Value                                                                                                                        |
|              | Year planted: Value (Age: <calculate>)                                                                                                    |
|              | Est. year planted: Value (Age: <calculate>)                                                                                               |
|              | Year died: Value                                                                                                                          |
|              | Form: Value                                                                                                                               |
|              | Condition: Value                                                                                                                          |
|              | Height: Value                                                                                                                             |
|              | Notes: Value                                                                                                                              |
|              | Tree tag: Value                                                                                                                           |
|              | Described: Value                                                                                                                          |
|              | Tags: Value                                                                                                                               |
|              | Ref: Value                                                                                                                                |
|              | FCF number: Value                                                                                                                         |
|              | FCF • Wikipedia • TSOL • Google Maps (all hyperlinks)                                                                                     |
| Icon         | Default icon: Circle                                                                                                                      |
|              | If tag includes Highlight, Star                                                                                                           |
|              | If tag includes "New", Paddle                                                                                                             |
|              | If condition is "Dead", Cross (supersedes other tags)                                                                                     |
|              | If tag includes "TBC", Question mark (supersedes other tags)                                                                              |
| Colour       | Unique colour for every scientific name<br>Base the hue on the first part of the name, and use different tints of that hue for variations |

**Calculating age:** Age = (Current year OR Year died) - (Year planted OR Est. year planted)

## Marker colours

Use these colours initially. I may provide exact hex values later.

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

## Photos

This needs some exploration, so don't implement it yet.

All photos are currently stored on Google Photos. Need to figure out if our tree map can retrieve them.

Example: 47957.21702: https://photos.google.com/photo/AF1QipMq_JYtG1UDRCAUY8GFRSr8-_96eOF_1R2k7PT0

There could be more than one photo per tree. Need to figure out the best way of having this in Google Sheets.

Ideally we'd like to display thumbnails in the tree popup.
