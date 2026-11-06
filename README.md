# Aurora Client

Fabric client mod for Minecraft Java Edition **1.21.1**, using **Java 21**.
This initial source release has not yet compiled or been tested in-game in the
cloud workspace because its network blocks Fabric's Maven repository.
GitHub Actions builds the client on every push; check its result before installing.

## Download on Windows

For source code: click **Code → Download ZIP** on this repository and extract it.
For the mod JAR: open **Actions → Build Aurora Client**, open a successful run,
and download **Aurora-Client-Minecraft-1.21.1** from Artifacts at the bottom.
You must be signed in to GitHub to download Actions artifacts. Extract the ZIP
and copy the JAR into your Fabric 1.21.1 profile's `mods` directory alongside
Fabric API. A failed build has no installable artifact; check the build log.

## Build and run

Install Java 21, then run from this directory:

```sh
./gradlew build
./gradlew runClient
```

Windows: use `gradlew.bat build` and `gradlew.bat runClient` instead.
After a successful build, install Fabric Loader for Minecraft 1.21.1 and place
`build/libs/aurora-client-0.1.0.jar` plus Fabric API 0.102.1+1.21.1 in the profile's
`mods` directory. Do not install the `-sources.jar` as a mod.

Gradle verifies its downloaded distribution against the pinned official SHA-256.
For cloud environments whose network requires a proxy, use `python3 tools/cloud-build.py`.
This preserves the supplied proxy and Java TLS trust; no verification is disabled.
Required hosts include maven.fabricmc.net, libraries.minecraft.net,
piston-meta.mojang.com, piston-data.mojang.com, resources.download.minecraft.net,
Maven Central, and Gradle's distribution hosts.

## Controls and appearance

Press **Right Shift** to open the translucent Aurora panel. It is also rebindable
in Minecraft's Controls menu. Select a category, search module names, and click
rows to toggle. Hover over any row for its description. **Disable all** switches
off every module. Escape or Done closes the panel. The game continues running
while the panel is open; combat/movement automation pauses while any screen is open.
All modules default to off. Settings persist in `config/aurora.json`.

## Implemented modules

| Category | Module | Behavior |
|---|---|---|
| Movement | Sprint | Sprint when moving forward and hunger allows |
| Movement | Speed | Scale ground horizontal velocity by 1.35 |
| Movement | Flight | Directional flight; jump up, sneak down |
| Movement | Auto jump | Jump when walking into a block |
| Movement | Safe walk | Sneak when approaching a ledge |
| Combat | Aim assist | Gently turn toward a nearby visible living target while holding attack |
| Combat | Trigger attack | Attack the crosshair target when cooldown is ready |
| Combat | Auto attack | Attack the nearest visible living entity within three blocks |
| Player | Auto tool | Select the fastest hotbar mining tool for the targeted block |
| Visual | Fullbright | Local night vision |
| Visual | Status HUD | Coordinates, speed, FPS, and enabled module list |

Combat targets include players and mobs, excluding teammates, spectators, and
occluded targets. Combat respects the vanilla attack cooldown and pauses while
using an item. Server authority may reject movement changes. Fullbright uses a
client-side effect and may conflict with server-managed night vision. Sneak
restoration currently assumes the default Left Shift sneak binding.

This is a focused initial module set, not every feature of every hacked client.
It contains no anti-cheat bypass, packet exploits, X-ray, or configurable per-module
keybinds. Movement/combat settings currently use fixed values.

## Validation checklist

Compilation and these game checks remain required once dependency access works:

- `./gradlew build` produces the remapped installable JAR.
- `./gradlew runClient` opens Minecraft with Aurora loaded.
- In a disposable single-player world or private server, open Right Shift,
  check hover descriptions, category search, and the translucent world background.
- Toggle each module individually, then Disable all. Verify movement and combat
  stop when disabled and while menus are open.
- Restart Minecraft and confirm saved toggles restore.
- Resize the window and check row layout and tooltips at different GUI scales.

The project is independent of the previously removed Flutter repository.
