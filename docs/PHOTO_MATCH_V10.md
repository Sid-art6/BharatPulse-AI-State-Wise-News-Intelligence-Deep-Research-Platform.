# v1.0 interface: three-image design reference

The three reference images supplied by the project owner define the intended visual design of:

1. News Intelligence (state selector, topics, article cards, evidence inventory)
2. Deep Research (multi-agent execution steps, evidence-sourced report, source panel)
3. Weather Intelligence (city summary, seven-day forecast, map and weather-related news)

The live application implements **separate navigable screens** with the same design language: light surfaces, navy primary actions, rounded cards, top BharatPulse header and fixed-width navigation.

## Accuracy boundaries

- News is pulled from live RSS metadata. Not all feeds include article photographs; unverified stock photos are **not** presented as event photos. Decorative thumbnails appear only with explicitly labelled demo stories.
- Deep Research displays actual indexed RSS evidence and source links only **after a successful research run**. It does not manufacture the reference image's exact article, evidence score, citations or timeline.
- Weather uses Open-Meteo city forecasts and a Leaflet **city-point map**, not an India-wide raster temperature analysis. A full geographic heatmap would require verified raster/gridded data and an appropriate backend. The city photograph is decorative and labelled as such.
- Public screenshots stored in `docs/screenshots` are controlled fixture previews of the implemented frontend; the README labels them accordingly.
- The image references were supplied by the project owner. Do not publish the reference screenshots as actual evidence of app features.
