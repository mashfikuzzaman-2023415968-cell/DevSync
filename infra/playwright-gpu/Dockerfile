# Playwright with Mesa GPU drivers, for the 3D frame-rate check (spec §13.12: "steady 60 fps on
# the demo laptop, measured with the Playwright performance trace"). The stock image only has
# software WebGL (SwiftShader); with /dev/dri passed in, Chromium renders through Vulkan on the
# laptop's real GPU. Used only by gate step 16.
FROM mcr.microsoft.com/playwright:v1.63.0-noble
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      mesa-vulkan-drivers libgl1-mesa-dri libegl-mesa0 \
 && rm -rf /var/lib/apt/lists/*
