# CharChat feature pack notes

This update is based on the supplied CharChat project. Several requested systems were already present in the supplied source: persisted relationship scores, inspectable/pinnable memories, story continuity extraction, per-character appearance settings, persona profiles, character JSON import/export, chat rewind snapshots, and response regeneration snapshots.

## Changes in this update

- Added an explicit **Story timeline** action in the chat app bar. It displays the current scene, character state, relationship dynamic, continuity notes, key events, and unresolved threads.
- Added per-message actions to **Edit message** and **Branch from here**.
- Editing a user message preserves the previous full conversation as a history snapshot, truncates the active timeline after the edited message, and regenerates the character reply.
- Editing an assistant reply updates that reply while keeping the original conversation snapshot in history.
- Branching from any message preserves the original conversation as a history snapshot and continues from the selected point.
- Story-state extraction and relationship/memory updates now use the character-specific model override when configured, falling back to the global Ollama model otherwise.

## Validation

The source was reviewed and packaged, but Flutter/Dart SDK tools were unavailable in the execution environment. Run `flutter pub get`, `flutter analyze`, `flutter test`, and `flutter run` locally before release.
